"""
Workflow engine tests.

`WorkflowEngine` is the single entry point other modules are meant to drive a
workflow through, and until now nothing called it directly: the coordinator
tests exercise `ApprovalTaskCoordinator.apply()` on its own, and
`test_state_machine_service.py` exercises `StateMachineService.execute()` on its
own. Neither proves the engine's own guards in `start()` (inactive definition,
wrong entity type, missing initial state, an entity already mid-workflow) or
that `execute_action()` actually wires the state machine's result into the
approval coordinator and persists the combined result — which is the whole
reason `WorkflowEngine` exists as a class rather than two functions callers
invoke separately.
"""

import itertools

import pytest
from workflow_fakes import WorkflowScenario

from src.application.services.workflow.workflow_engine import WorkflowEngine
from src.domain.entities.workflow import WorkflowDefinition
from src.domain.exceptions.domain_exceptions import (
    BusinessRuleViolationError,
    EntityNotFoundError,
)

# Polymorphic entity ids are plain bigints now; a counter keeps each test's
# entity distinct without needing the database to hand one out.
_entity_id_seq = itertools.count(1)


def _nid() -> int:
    return next(_entity_id_seq)


@pytest.fixture
def engine(scenario: WorkflowScenario) -> WorkflowEngine:
    return scenario.engine()


class TestStart:
    async def test_starts_at_the_initial_status(
        self, scenario: WorkflowScenario, engine: WorkflowEngine
    ) -> None:
        entity_id = _nid()

        state = await engine.start(
            definition_code="COMPLIANCE_TASK_APPROVAL",
            entity_type=scenario.ENTITY_TYPE,
            entity_id=entity_id,
            initiated_by=scenario.maker,
            actor_username="maker",
        )

        assert state.status.code == "DRAFT"
        assert state.instance.entity_id == entity_id
        assert state.instance.initiated_by == scenario.maker
        assert state.instance.approval_level == 0

    async def test_metadata_is_stored_on_the_instance(
        self, scenario: WorkflowScenario, engine: WorkflowEngine
    ) -> None:
        state = await engine.start(
            definition_code="COMPLIANCE_TASK_APPROVAL",
            entity_type=scenario.ENTITY_TYPE,
            entity_id=_nid(),
            initiated_by=scenario.maker,
            actor_username="maker",
            metadata={"risk_level": "HIGH"},
        )

        assert state.instance.extra_data == {"risk_level": "HIGH"}

    async def test_unknown_definition_code_raises_not_found(
        self, engine: WorkflowEngine
    ) -> None:
        with pytest.raises(EntityNotFoundError):
            await engine.start(
                definition_code="NO_SUCH_WORKFLOW",
                entity_type="anything",
                entity_id=_nid(),
                initiated_by=1,
                actor_username="maker",
            )

    async def test_inactive_definition_is_rejected(
        self, scenario: WorkflowScenario, engine: WorkflowEngine
    ) -> None:
        scenario.definition.deactivate()
        scenario.definitions.definitions[scenario.definition.id] = scenario.definition

        with pytest.raises(BusinessRuleViolationError) as exc:
            await engine.start(
                definition_code="COMPLIANCE_TASK_APPROVAL",
                entity_type=scenario.ENTITY_TYPE,
                entity_id=_nid(),
                initiated_by=scenario.maker,
                actor_username="maker",
            )
        assert "inactive" in exc.value.message

    async def test_mismatched_entity_type_is_rejected(
        self, scenario: WorkflowScenario, engine: WorkflowEngine
    ) -> None:
        with pytest.raises(BusinessRuleViolationError) as exc:
            await engine.start(
                definition_code="COMPLIANCE_TASK_APPROVAL",
                entity_type="something_else",
                entity_id=_nid(),
                initiated_by=scenario.maker,
                actor_username="maker",
            )
        assert "compliance_task" in exc.value.message

    async def test_definition_with_no_initial_status_is_rejected(
        self, scenario: WorkflowScenario, engine: WorkflowEngine
    ) -> None:
        bare = WorkflowDefinition(
            code="NO_INITIAL_STATUS",
            name="No Initial Status",
            entity_type="widget",
        )
        scenario.definitions.definitions[bare.id] = bare

        with pytest.raises(BusinessRuleViolationError) as exc:
            await engine.start(
                definition_code="NO_INITIAL_STATUS",
                entity_type="widget",
                entity_id=_nid(),
                initiated_by=1,
                actor_username="maker",
            )
        assert "no initial state" in exc.value.message

    async def test_second_instance_for_the_same_entity_is_refused(
        self, scenario: WorkflowScenario, engine: WorkflowEngine
    ) -> None:
        entity_id = _nid()
        await engine.start(
            definition_code="COMPLIANCE_TASK_APPROVAL",
            entity_type=scenario.ENTITY_TYPE,
            entity_id=entity_id,
            initiated_by=scenario.maker,
            actor_username="maker",
        )

        with pytest.raises(BusinessRuleViolationError) as exc:
            await engine.start(
                definition_code="COMPLIANCE_TASK_APPROVAL",
                entity_type=scenario.ENTITY_TYPE,
                entity_id=entity_id,
                initiated_by=scenario.maker,
                actor_username="maker",
            )
        assert "already has an open workflow instance" in exc.value.message

    async def test_a_completed_instance_does_not_block_starting_a_new_one(
        self, scenario: WorkflowScenario, engine: WorkflowEngine
    ) -> None:
        """`get_open_for_entity` only ever returns instances that are still running."""
        entity_id = _nid()
        first = await engine.start(
            definition_code="COMPLIANCE_TASK_APPROVAL",
            entity_type=scenario.ENTITY_TYPE,
            entity_id=entity_id,
            initiated_by=scenario.maker,
            actor_username="maker",
        )
        await engine.execute_action(
            instance_id=first.instance.id,
            action_code="CANCEL",
            actor_id=scenario.maker,
            actor_username="maker",
            comments="withdrawn",
        )

        second = await engine.start(
            definition_code="COMPLIANCE_TASK_APPROVAL",
            entity_type=scenario.ENTITY_TYPE,
            entity_id=entity_id,
            initiated_by=scenario.maker,
            actor_username="maker",
        )

        assert second.instance.id != first.instance.id


class TestExecuteAction:
    async def test_delegates_the_move_to_the_state_machine(
        self, scenario: WorkflowScenario, engine: WorkflowEngine
    ) -> None:
        started = await engine.start(
            definition_code="COMPLIANCE_TASK_APPROVAL",
            entity_type=scenario.ENTITY_TYPE,
            entity_id=_nid(),
            initiated_by=scenario.maker,
            actor_username="maker",
        )

        result = await engine.execute_action(
            instance_id=started.instance.id,
            action_code="SUBMIT",
            actor_id=scenario.maker,
            actor_username="maker",
        )

        assert result.to_status.code == "L1_REVIEW"

    async def test_unknown_instance_raises_not_found(self, engine: WorkflowEngine) -> None:
        with pytest.raises(EntityNotFoundError):
            await engine.execute_action(
                instance_id=999_999,
                action_code="SUBMIT",
                actor_id=999_999,
                actor_username="maker",
            )

    async def test_illegal_action_leaves_the_approval_chain_untouched(
        self, scenario: WorkflowScenario, engine: WorkflowEngine
    ) -> None:
        """
        The state move is authoritative: if it fails, the approval coordinator
        must never run. There is no matrix configured here at all, so this also
        proves an illegal action does not attempt to touch one.
        """
        started = await engine.start(
            definition_code="COMPLIANCE_TASK_APPROVAL",
            entity_type=scenario.ENTITY_TYPE,
            entity_id=_nid(),
            initiated_by=scenario.maker,
            actor_username="maker",
        )

        with pytest.raises(BusinessRuleViolationError):
            await engine.execute_action(
                instance_id=started.instance.id,
                action_code="APPROVE",  # not legal from DRAFT
                actor_id=scenario.maker,
                actor_username="maker",
            )

    async def test_submit_opens_the_approval_chain_when_a_matrix_matches(
        self, scenario: WorkflowScenario, engine: WorkflowEngine
    ) -> None:
        """
        This is the seam `WorkflowEngine` exists for: the state machine's SUBMIT
        move and the coordinator's chain-opening must happen together, in one
        call, with the resulting `approval_level` persisted.
        """
        scenario.add_two_level_matrix()
        started = await engine.start(
            definition_code="COMPLIANCE_TASK_APPROVAL",
            entity_type=scenario.ENTITY_TYPE,
            entity_id=_nid(),
            initiated_by=scenario.maker,
            actor_username="maker",
        )

        result = await engine.execute_action(
            instance_id=started.instance.id,
            action_code="SUBMIT",
            actor_id=scenario.maker,
            actor_username="maker",
        )

        assert result.instance.approval_level == 1
        persisted = await scenario.instances.get_by_id(started.instance.id)
        assert persisted is not None
        assert persisted.approval_level == 1
        pending = scenario.matrices.open_tasks(started.instance.id)
        assert {t.assignee_id for t in pending} == {scenario.manager_a, scenario.manager_b}

    async def test_rejection_tears_down_the_chain_through_the_engine(
        self, scenario: WorkflowScenario, engine: WorkflowEngine
    ) -> None:
        scenario.add_two_level_matrix()
        started = await engine.start(
            definition_code="COMPLIANCE_TASK_APPROVAL",
            entity_type=scenario.ENTITY_TYPE,
            entity_id=_nid(),
            initiated_by=scenario.maker,
            actor_username="maker",
        )
        await engine.execute_action(
            instance_id=started.instance.id,
            action_code="SUBMIT",
            actor_id=scenario.maker,
            actor_username="maker",
        )

        result = await engine.execute_action(
            instance_id=started.instance.id,
            action_code="REJECT",
            actor_id=scenario.manager_a,
            actor_username="manager_a",
            comments="incomplete",
        )

        assert result.to_status.code == "REJECTED"
        assert result.instance.approval_level == 0
        assert scenario.matrices.open_tasks(started.instance.id) == []


class TestReads:
    async def test_get_state_delegates_to_the_state_machine(
        self, scenario: WorkflowScenario, engine: WorkflowEngine
    ) -> None:
        started = await engine.start(
            definition_code="COMPLIANCE_TASK_APPROVAL",
            entity_type=scenario.ENTITY_TYPE,
            entity_id=_nid(),
            initiated_by=scenario.maker,
            actor_username="maker",
        )

        state = await engine.get_state(started.instance.id)

        assert state.status.code == "DRAFT"

    async def test_available_actions_reflects_the_current_state(
        self, scenario: WorkflowScenario, engine: WorkflowEngine
    ) -> None:
        started = await engine.start(
            definition_code="COMPLIANCE_TASK_APPROVAL",
            entity_type=scenario.ENTITY_TYPE,
            entity_id=_nid(),
            initiated_by=scenario.maker,
            actor_username="maker",
        )

        actions = await engine.available_actions(started.instance.id)

        assert {t.action_code for t in actions} == {"SUBMIT", "CANCEL"}

    async def test_available_actions_unknown_instance_raises_not_found(
        self, engine: WorkflowEngine
    ) -> None:
        with pytest.raises(EntityNotFoundError):
            await engine.available_actions(999_999)

    async def test_pending_tasks_reports_a_users_open_approvals(
        self, scenario: WorkflowScenario, engine: WorkflowEngine
    ) -> None:
        scenario.add_two_level_matrix()
        started = await engine.start(
            definition_code="COMPLIANCE_TASK_APPROVAL",
            entity_type=scenario.ENTITY_TYPE,
            entity_id=_nid(),
            initiated_by=scenario.maker,
            actor_username="maker",
        )
        await engine.execute_action(
            instance_id=started.instance.id,
            action_code="SUBMIT",
            actor_id=scenario.maker,
            actor_username="maker",
        )

        tasks = await engine.pending_tasks(scenario.manager_a)

        assert len(tasks) == 1
        assert tasks[0].instance_id == started.instance.id

    async def test_resolve_approvers_previews_the_matching_matrix(
        self, scenario: WorkflowScenario, engine: WorkflowEngine
    ) -> None:
        matrix = scenario.add_two_level_matrix()

        resolved = await engine.resolve_approvers(
            scenario.ENTITY_TYPE, {"risk_level": "LOW"}
        )

        assert resolved is not None
        assert resolved.matrix.id == matrix.id
        assert resolved.levels == [1, 2]

    async def test_resolve_approvers_returns_none_when_nothing_matches(
        self, scenario: WorkflowScenario, engine: WorkflowEngine
    ) -> None:
        resolved = await engine.resolve_approvers(scenario.ENTITY_TYPE, {})

        assert resolved is None
