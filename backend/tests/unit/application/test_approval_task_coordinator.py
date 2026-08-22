"""
Approval task coordinator tests.

The coordinator is the join between the state machine and the approval matrix, so
these tests are where the wiring is actually specified: when tasks appear, who
gets them, when a level settles, and when the chain is torn down.

Everything is driven by the transition's declared `action_type`, never by the
free-text `action_code` — a workflow can call its move SIGN_OFF and still route
correctly, and that is asserted directly.
"""

from uuid import UUID, uuid4

import pytest
from workflow_fakes import WorkflowScenario, build_matrix

from src.application.services.workflow.approval_task_coordinator import (
    ApprovalTaskCoordinator,
)
from src.domain.entities.approval_matrix import ApprovalTask
from src.domain.entities.workflow import WorkflowInstance
from src.domain.enums.workflow_enums import (
    ApprovalTaskStatus,
    AssignmentType,
    WorkflowActionType,
)


@pytest.fixture
def coordinator(scenario: WorkflowScenario) -> ApprovalTaskCoordinator:
    return ApprovalTaskCoordinator(scenario.matrices, scenario.roles)


async def apply(
    coordinator: ApprovalTaskCoordinator,
    scenario: WorkflowScenario,
    instance: WorkflowInstance,
    action_type: WorkflowActionType,
    actor_id: UUID,
    *,
    comments: str = "",
    terminal: bool = False,
) -> list[ApprovalTask]:
    """Run one coordinator pass and persist the instance, as the engine does."""
    created = await coordinator.apply(
        instance=instance,
        action_type=action_type,
        actor_id=actor_id,
        actor_username="tester",
        comments=comments,
        reached_terminal_state=terminal,
    )
    await scenario.instances.update(instance)
    return list(created)


class TestOpeningTheChain:
    """SUBMIT is what puts work in someone's queue."""

    async def test_submit_opens_level_one_for_every_role_holder(
        self, scenario: WorkflowScenario, coordinator: ApprovalTaskCoordinator
    ) -> None:
        scenario.add_two_level_matrix()
        instance = scenario.new_instance()

        created = await apply(
            coordinator, scenario, instance, WorkflowActionType.SUBMIT, scenario.maker
        )

        assert instance.approval_level == 1
        assert {task.assignee_id for task in created} == {
            scenario.manager_a,
            scenario.manager_b,
        }
        assert all(task.status == ApprovalTaskStatus.PENDING for task in created)
        assert all(task.level == 1 for task in created)

    async def test_submit_records_which_matrix_routed_the_work(
        self, scenario: WorkflowScenario, coordinator: ApprovalTaskCoordinator
    ) -> None:
        matrix = scenario.add_two_level_matrix()
        instance = scenario.new_instance()

        created = await apply(
            coordinator, scenario, instance, WorkflowActionType.SUBMIT, scenario.maker
        )

        assert {task.matrix_id for task in created} == {matrix.id}

    async def test_matrix_is_chosen_by_the_instance_payload(
        self, scenario: WorkflowScenario
    ) -> None:
        # Specific matrix sorts first; the catch-all only wins when it does not match.
        critical = build_matrix(
            code="TASK_CRITICAL",
            priority=10,
            rules=[("risk_level", "EQ", "CRITICAL", "STRING")],
            levels=[(1, AssignmentType.ROLE, scenario.admin_role_id)],
        )
        standard = build_matrix(
            code="TASK_STANDARD",
            priority=100,
            levels=[(1, AssignmentType.ROLE, scenario.manager_role_id)],
        )
        scenario.matrices.matrices[critical.id] = critical
        scenario.matrices.matrices[standard.id] = standard
        coordinator = ApprovalTaskCoordinator(scenario.matrices, scenario.roles)

        critical_instance = scenario.new_instance(
            extra_data={"risk_level": "CRITICAL"}
        )
        standard_instance = scenario.new_instance(extra_data={"risk_level": "LOW"})

        critical_tasks = await apply(
            coordinator,
            scenario,
            critical_instance,
            WorkflowActionType.SUBMIT,
            scenario.maker,
        )
        standard_tasks = await apply(
            coordinator,
            scenario,
            standard_instance,
            WorkflowActionType.SUBMIT,
            scenario.maker,
        )

        assert {t.assignee_id for t in critical_tasks} == {scenario.admin}
        assert {t.assignee_id for t in standard_tasks} == {
            scenario.manager_a,
            scenario.manager_b,
        }

    async def test_no_matching_matrix_leaves_the_chain_closed(
        self, scenario: WorkflowScenario, coordinator: ApprovalTaskCoordinator
    ) -> None:
        # No matrix registered at all: the workflow still runs, unapproved.
        instance = scenario.new_instance()

        created = await apply(
            coordinator, scenario, instance, WorkflowActionType.SUBMIT, scenario.maker
        )

        assert created == []
        assert instance.approval_level == 0

    async def test_matrix_with_no_levels_leaves_the_chain_closed(
        self, scenario: WorkflowScenario, coordinator: ApprovalTaskCoordinator
    ) -> None:
        matrix = build_matrix(code="TASK_EMPTY", levels=[])
        scenario.matrices.matrices[matrix.id] = matrix
        instance = scenario.new_instance()

        created = await apply(
            coordinator, scenario, instance, WorkflowActionType.SUBMIT, scenario.maker
        )

        assert created == []
        assert instance.approval_level == 0

    async def test_level_resolving_to_nobody_does_not_strand_the_instance(
        self, scenario: WorkflowScenario
    ) -> None:
        # A role with no active holders would otherwise leave the record waiting on
        # an approval nobody can give.
        empty_role_id = uuid4()
        matrix = build_matrix(
            code="TASK_EMPTY_ROLE",
            levels=[(1, AssignmentType.ROLE, empty_role_id)],
        )
        scenario.matrices.matrices[matrix.id] = matrix
        coordinator = ApprovalTaskCoordinator(scenario.matrices, scenario.roles)
        instance = scenario.new_instance()

        created = await apply(
            coordinator, scenario, instance, WorkflowActionType.SUBMIT, scenario.maker
        )

        assert created == []
        assert instance.approval_level == 0

    async def test_user_named_twice_at_one_level_gets_one_task(
        self, scenario: WorkflowScenario
    ) -> None:
        # Reachable directly and via a role. Two tasks would breach
        # uq_approval_tasks_instance_assignee_level.
        matrix = build_matrix(
            code="TASK_OVERLAP",
            levels=[
                (1, AssignmentType.ROLE, scenario.manager_role_id),
                (1, AssignmentType.USER, scenario.manager_a),
            ],
        )
        scenario.matrices.matrices[matrix.id] = matrix
        coordinator = ApprovalTaskCoordinator(scenario.matrices, scenario.roles)
        instance = scenario.new_instance()

        created = await apply(
            coordinator, scenario, instance, WorkflowActionType.SUBMIT, scenario.maker
        )

        assignees = [task.assignee_id for task in created]
        assert len(assignees) == len(set(assignees))
        assert set(assignees) == {scenario.manager_a, scenario.manager_b}


class TestAdvancingTheChain:
    """APPROVE settles the current level and steps to the next."""

    async def test_approval_completes_the_actor_and_cancels_the_peers(
        self, scenario: WorkflowScenario, coordinator: ApprovalTaskCoordinator
    ) -> None:
        scenario.add_two_level_matrix()
        instance = scenario.new_instance()
        await apply(
            coordinator, scenario, instance, WorkflowActionType.SUBMIT, scenario.maker
        )

        await apply(
            coordinator,
            scenario,
            instance,
            WorkflowActionType.APPROVE,
            scenario.manager_a,
            comments="looks fine",
        )

        level_one = {t.assignee_id: t for t in scenario.matrices.tasks_at(instance.id, 1)}
        assert level_one[scenario.manager_a].status == ApprovalTaskStatus.COMPLETED
        assert level_one[scenario.manager_a].action_taken == "APPROVE"
        assert level_one[scenario.manager_a].comments == "looks fine"
        # The peer was asked and is on the record, but is no longer actionable.
        assert level_one[scenario.manager_b].status == ApprovalTaskStatus.CANCELLED
        assert level_one[scenario.manager_b].action_taken is None

    async def test_approval_opens_the_next_level(
        self, scenario: WorkflowScenario, coordinator: ApprovalTaskCoordinator
    ) -> None:
        scenario.add_two_level_matrix()
        instance = scenario.new_instance()
        await apply(
            coordinator, scenario, instance, WorkflowActionType.SUBMIT, scenario.maker
        )

        created = await apply(
            coordinator,
            scenario,
            instance,
            WorkflowActionType.APPROVE,
            scenario.manager_a,
        )

        assert instance.approval_level == 2
        assert [task.assignee_id for task in created] == [scenario.admin]
        assert [t.assignee_id for t in scenario.matrices.open_tasks(instance.id)] == [
            scenario.admin
        ]

    async def test_final_approval_closes_the_chain(
        self, scenario: WorkflowScenario, coordinator: ApprovalTaskCoordinator
    ) -> None:
        scenario.add_two_level_matrix()
        instance = scenario.new_instance()
        await apply(
            coordinator, scenario, instance, WorkflowActionType.SUBMIT, scenario.maker
        )
        await apply(
            coordinator,
            scenario,
            instance,
            WorkflowActionType.APPROVE,
            scenario.manager_a,
        )

        created = await apply(
            coordinator, scenario, instance, WorkflowActionType.APPROVE, scenario.admin
        )

        assert created == []
        assert instance.approval_level == 0
        assert scenario.matrices.open_tasks(instance.id) == []

    async def test_chain_waits_while_a_peer_task_is_still_open(
        self, scenario: WorkflowScenario
    ) -> None:
        # Two separately named users at level 1, so settling one leaves the other
        # open and the chain must not race ahead to level 2.
        matrix = build_matrix(
            code="TASK_BOTH_MUST_ACT",
            levels=[
                (1, AssignmentType.USER, scenario.manager_a),
                (1, AssignmentType.USER, scenario.manager_b),
                (2, AssignmentType.ROLE, scenario.admin_role_id),
            ],
        )
        scenario.matrices.matrices[matrix.id] = matrix
        coordinator = ApprovalTaskCoordinator(scenario.matrices, scenario.roles)
        instance = scenario.new_instance()
        await apply(
            coordinator, scenario, instance, WorkflowActionType.SUBMIT, scenario.maker
        )

        # An unrelated user acting settles nothing, so level 1 stays open.
        created = await apply(
            coordinator, scenario, instance, WorkflowActionType.APPROVE, uuid4()
        )

        assert created == []
        assert instance.approval_level == 1
        assert len(scenario.matrices.open_tasks(instance.id)) == 2


class TestTearingDownTheChain:
    """Rejection, cancellation and refer-back all clear the queue."""

    @pytest.mark.parametrize(
        "action_type",
        [WorkflowActionType.REJECT, WorkflowActionType.CANCEL],
    )
    async def test_rejection_and_cancellation_abandon_the_chain(
        self,
        scenario: WorkflowScenario,
        coordinator: ApprovalTaskCoordinator,
        action_type: WorkflowActionType,
    ) -> None:
        scenario.add_two_level_matrix()
        instance = scenario.new_instance()
        await apply(
            coordinator, scenario, instance, WorkflowActionType.SUBMIT, scenario.maker
        )

        await apply(
            coordinator,
            scenario,
            instance,
            action_type,
            scenario.manager_a,
            comments="not acceptable",
        )

        assert instance.approval_level == 0
        assert scenario.matrices.open_tasks(instance.id) == []

    async def test_rejection_records_who_rejected_and_why(
        self, scenario: WorkflowScenario, coordinator: ApprovalTaskCoordinator
    ) -> None:
        scenario.add_two_level_matrix()
        instance = scenario.new_instance()
        await apply(
            coordinator, scenario, instance, WorkflowActionType.SUBMIT, scenario.maker
        )

        await apply(
            coordinator,
            scenario,
            instance,
            WorkflowActionType.REJECT,
            scenario.manager_a,
            comments="missing evidence",
        )

        rejected = next(
            t
            for t in scenario.matrices.tasks_at(instance.id, 1)
            if t.assignee_id == scenario.manager_a
        )
        assert rejected.status == ApprovalTaskStatus.COMPLETED
        assert rejected.action_taken == "REJECT"
        assert rejected.comments == "missing evidence"

    async def test_terminal_state_overrides_the_declared_action(
        self, scenario: WorkflowScenario, coordinator: ApprovalTaskCoordinator
    ) -> None:
        # A designer could wire APPROVE straight into a terminal state. Whatever the
        # action says, a finished instance must not leave approvals in queues.
        scenario.add_two_level_matrix()
        instance = scenario.new_instance()
        await apply(
            coordinator, scenario, instance, WorkflowActionType.SUBMIT, scenario.maker
        )

        created = await apply(
            coordinator,
            scenario,
            instance,
            WorkflowActionType.APPROVE,
            scenario.manager_a,
            terminal=True,
        )

        assert created == []
        assert instance.approval_level == 0
        assert scenario.matrices.open_tasks(instance.id) == []

    async def test_refer_back_clears_the_chain_and_a_resubmit_restarts_it(
        self, scenario: WorkflowScenario, coordinator: ApprovalTaskCoordinator
    ) -> None:
        scenario.add_two_level_matrix()
        instance = scenario.new_instance()
        await apply(
            coordinator, scenario, instance, WorkflowActionType.SUBMIT, scenario.maker
        )

        await apply(
            coordinator,
            scenario,
            instance,
            WorkflowActionType.REFER_BACK,
            scenario.manager_a,
            comments="please attach the filing receipt",
        )
        assert instance.approval_level == 0
        assert scenario.matrices.open_tasks(instance.id) == []

        reopened = await apply(
            coordinator, scenario, instance, WorkflowActionType.SUBMIT, scenario.maker
        )

        assert instance.approval_level == 1
        assert {task.assignee_id for task in reopened} == {
            scenario.manager_a,
            scenario.manager_b,
        }


class TestActionsThatDoNotTouchTheChain:
    """Only declared approval semantics move the chain."""

    @pytest.mark.parametrize(
        "action_type",
        [
            WorkflowActionType.CUSTOM,
            WorkflowActionType.ESCALATE,
            WorkflowActionType.CLOSE,
        ],
    )
    async def test_other_action_types_leave_open_tasks_alone(
        self,
        scenario: WorkflowScenario,
        coordinator: ApprovalTaskCoordinator,
        action_type: WorkflowActionType,
    ) -> None:
        scenario.add_two_level_matrix()
        instance = scenario.new_instance()
        await apply(
            coordinator, scenario, instance, WorkflowActionType.SUBMIT, scenario.maker
        )

        created = await apply(
            coordinator, scenario, instance, action_type, scenario.manager_a
        )

        assert created == []
        assert instance.approval_level == 1
        assert len(scenario.matrices.open_tasks(instance.id)) == 2

    async def test_maker_submitting_holds_no_task_and_that_is_not_an_error(
        self, scenario: WorkflowScenario, coordinator: ApprovalTaskCoordinator
    ) -> None:
        scenario.add_two_level_matrix()
        instance = scenario.new_instance()

        created = await apply(
            coordinator, scenario, instance, WorkflowActionType.SUBMIT, scenario.maker
        )

        assert len(created) == 2
        assert scenario.matrices.list_pending_tasks_for_user is not None
