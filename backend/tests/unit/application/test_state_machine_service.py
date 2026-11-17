"""
State machine service tests.

This is the piece that decides whether a requested move is legal and what gets
written when it is executed — and, until now, nothing exercised it directly.
`test_approval_task_coordinator.py` calls `coordinator.apply()` in isolation, so
none of those tests actually route through `StateMachineService.execute()`
either. These tests close that gap.
"""

import pytest
from workflow_fakes import WorkflowScenario

from src.application.services.workflow.state_machine_service import (
    StateMachineService,
)
from src.domain.enums.workflow_enums import WorkflowActionType
from src.domain.exceptions.domain_exceptions import (
    BusinessRuleViolationError,
    EntityNotFoundError,
)


@pytest.fixture
def machine(scenario: WorkflowScenario) -> StateMachineService:
    return StateMachineService(scenario.definitions, scenario.instances)


class TestGetState:
    async def test_resolves_instance_status_and_definition(
        self, scenario: WorkflowScenario, machine: StateMachineService
    ) -> None:
        instance = scenario.new_instance()

        state = await machine.get_state(instance.id)

        assert state.instance.id == instance.id
        assert state.status.code == "DRAFT"
        assert state.definition.id == scenario.definition.id

    async def test_unknown_instance_raises_not_found(
        self, machine: StateMachineService
    ) -> None:
        with pytest.raises(EntityNotFoundError):
            await machine.get_state(999_999)


class TestAvailableActions:
    async def test_lists_transitions_leaving_the_current_state(
        self, scenario: WorkflowScenario, machine: StateMachineService
    ) -> None:
        instance = scenario.new_instance(status_code="DRAFT")

        actions = await machine.available_actions(instance)

        assert {t.action_code for t in actions} == {"SUBMIT", "CANCEL"}

    async def test_completed_instance_offers_nothing(
        self, scenario: WorkflowScenario, machine: StateMachineService
    ) -> None:
        instance = scenario.new_instance(status_code="APPROVED")
        instance.move_to(scenario.status_ids["APPROVED"], is_terminal=True)

        actions = await machine.available_actions(instance)

        assert actions == []


class TestExecute:
    async def test_legal_action_moves_the_instance_and_records_history(
        self, scenario: WorkflowScenario, machine: StateMachineService
    ) -> None:
        instance = scenario.new_instance(status_code="DRAFT")

        result = await machine.execute(
            instance=instance,
            action_code="SUBMIT",
            actor_id=scenario.maker,
            actor_username="maker",
        )

        assert result.to_status.code == "L1_REVIEW"
        assert result.from_status is not None
        assert result.from_status.code == "DRAFT"
        assert result.history.action_code == "SUBMIT"
        assert result.history.actor_username == "maker"
        assert result.instance.current_status_id == scenario.status_ids["L1_REVIEW"]

    async def test_reaching_a_terminal_status_stamps_completed_at(
        self, scenario: WorkflowScenario, machine: StateMachineService
    ) -> None:
        instance = scenario.new_instance(status_code="DRAFT")

        result = await machine.execute(
            instance=instance,
            action_code="CANCEL",
            actor_id=scenario.maker,
            actor_username="maker",
            comments="no longer needed",
        )

        assert result.to_status.is_terminal is True
        assert result.instance.completed_at is not None
        assert result.instance.is_completed is True

    async def test_action_not_wired_from_current_state_is_rejected(
        self, scenario: WorkflowScenario, machine: StateMachineService
    ) -> None:
        """APPROVE only exists from L1_REVIEW/L2_REVIEW, not from DRAFT."""
        instance = scenario.new_instance(status_code="DRAFT")

        with pytest.raises(BusinessRuleViolationError) as exc:
            await machine.execute(
                instance=instance,
                action_code="APPROVE",
                actor_id=scenario.maker,
                actor_username="maker",
            )
        assert "not allowed" in exc.value.message

    async def test_completed_instance_accepts_no_further_actions(
        self, scenario: WorkflowScenario, machine: StateMachineService
    ) -> None:
        instance = scenario.new_instance(status_code="APPROVED")
        instance.move_to(scenario.status_ids["APPROVED"], is_terminal=True)

        with pytest.raises(BusinessRuleViolationError) as exc:
            await machine.execute(
                instance=instance,
                action_code="SUBMIT",
                actor_id=scenario.maker,
                actor_username="maker",
            )
        assert "already completed" in exc.value.message

    async def test_requires_comment_is_enforced_even_though_untracked_by_the_source(
        self, scenario: WorkflowScenario, machine: StateMachineService
    ) -> None:
        """CANCEL from DRAFT is wired with requires_comment=True."""
        instance = scenario.new_instance(status_code="DRAFT")

        with pytest.raises(BusinessRuleViolationError) as exc:
            await machine.execute(
                instance=instance,
                action_code="CANCEL",
                actor_id=scenario.maker,
                actor_username="maker",
            )
        assert "requires a comment" in exc.value.message

    async def test_whitespace_only_comment_does_not_satisfy_the_requirement(
        self, scenario: WorkflowScenario, machine: StateMachineService
    ) -> None:
        instance = scenario.new_instance(status_code="DRAFT")

        with pytest.raises(BusinessRuleViolationError):
            await machine.execute(
                instance=instance,
                action_code="CANCEL",
                actor_id=scenario.maker,
                actor_username="maker",
                comments="   ",
            )

    async def test_execute_persists_the_updated_instance(
        self, scenario: WorkflowScenario, machine: StateMachineService
    ) -> None:
        instance = scenario.new_instance(status_code="DRAFT")

        await machine.execute(
            instance=instance,
            action_code="SUBMIT",
            actor_id=scenario.maker,
            actor_username="maker",
        )

        persisted = await scenario.instances.get_by_id(instance.id)
        assert persisted is not None
        assert persisted.current_status_id == scenario.status_ids["L1_REVIEW"]

    async def test_history_entry_is_appended_and_queryable(
        self, scenario: WorkflowScenario, machine: StateMachineService
    ) -> None:
        instance = scenario.new_instance(status_code="DRAFT")

        await machine.execute(
            instance=instance,
            action_code="SUBMIT",
            actor_id=scenario.maker,
            actor_username="maker",
            ip_address="10.0.0.1",
        )

        history = await scenario.instances.list_history(instance.id)
        assert len(history) == 1
        assert history[0].action_code == "SUBMIT"
        assert history[0].ip_address == "10.0.0.1"

    async def test_action_type_from_the_transition_is_carried_on_the_result(
        self, scenario: WorkflowScenario, machine: StateMachineService
    ) -> None:
        """The engine reads `result.transition.action_type` to drive approvals."""
        instance = scenario.new_instance(status_code="DRAFT")

        result = await machine.execute(
            instance=instance,
            action_code="SUBMIT",
            actor_id=scenario.maker,
            actor_username="maker",
        )

        assert result.transition.action_type == WorkflowActionType.SUBMIT
