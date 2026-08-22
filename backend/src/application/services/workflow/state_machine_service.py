"""
State machine service.

Owns the rules about moving a workflow instance between states: which actions are
offered from the current state, whether a requested action is legal, and what
gets written when it is executed.

Only talks to repository ports, so it holds no SQLAlchemy dependency and can be
unit tested against in-memory fakes.
"""

import logging
from dataclasses import dataclass
from uuid import UUID

from src.domain.entities.workflow import (
    WorkflowDefinition,
    WorkflowHistoryEntry,
    WorkflowInstance,
    WorkflowStatus,
    WorkflowTransition,
)
from src.domain.exceptions.domain_exceptions import (
    BusinessRuleViolationError,
    EntityNotFoundError,
)
from src.domain.repositories.workflow_definition_repository import (
    IWorkflowDefinitionRepository,
)
from src.domain.repositories.workflow_instance_repository import (
    IWorkflowInstanceRepository,
)

logger = logging.getLogger(__name__)

INSTANCE = "WorkflowInstance"
STATUS = "WorkflowStatus"


@dataclass(frozen=True)
class InstanceState:
    """An instance together with the state and definition it resolves to."""

    instance: WorkflowInstance
    status: WorkflowStatus
    definition: WorkflowDefinition


@dataclass(frozen=True)
class TransitionResult:
    """
    Everything one executed action produced.

    `transition` is carried out so callers can react to what the move was declared
    to mean (its `action_type`) without looking it up a second time.
    """

    instance: WorkflowInstance
    from_status: WorkflowStatus | None
    to_status: WorkflowStatus
    transition: WorkflowTransition
    history: WorkflowHistoryEntry


class StateMachineService:
    """Validates and executes state transitions for workflow instances."""

    def __init__(
        self,
        definition_repo: IWorkflowDefinitionRepository,
        instance_repo: IWorkflowInstanceRepository,
    ) -> None:
        self._definitions = definition_repo
        self._instances = instance_repo

    # ─── Reads ───

    async def get_state(self, instance_id: UUID) -> InstanceState:
        """Resolve an instance to its current status and owning definition."""
        instance = await self._instances.get_by_id(instance_id)
        if instance is None:
            raise EntityNotFoundError(INSTANCE, instance_id)
        return await self._resolve(instance)

    async def available_actions(
        self, instance: WorkflowInstance
    ) -> list[WorkflowTransition]:
        """
        Transitions leaving the instance's current state.

        A completed instance offers nothing, so callers do not have to special
        case terminal states in the UI.
        """
        if instance.is_completed:
            return []
        return await self._definitions.list_transitions_from(
            instance.workflow_definition_id, instance.current_status_id
        )

    # ─── Writes ───

    async def execute(
        self,
        *,
        instance: WorkflowInstance,
        action_code: str,
        actor_id: UUID,
        actor_username: str,
        comments: str = "",
        ip_address: str = "",
    ) -> TransitionResult:
        """
        Apply an action to an instance.

        Raises:
            BusinessRuleViolationError: The instance is finished, the action is
                not wired up from the current state, or the transition requires a
                comment that was not supplied.
        """
        if instance.is_completed:
            raise BusinessRuleViolationError(
                f"Workflow instance '{instance.id}' is already completed and "
                "accepts no further actions"
            )

        transition = await self._definitions.find_transition(
            instance.workflow_definition_id, instance.current_status_id, action_code
        )
        if transition is None:
            raise BusinessRuleViolationError(
                f"Action '{action_code}' is not allowed from the current state"
            )

        # The source system stored `requires_comment` but never enforced it, so a
        # rejection could be recorded with no reason attached. Enforced here.
        if transition.requires_comment and not comments.strip():
            raise BusinessRuleViolationError(
                f"Action '{action_code}' requires a comment"
            )

        from_status = await self._definitions.get_status(instance.current_status_id)
        to_status = await self._definitions.get_status(transition.to_status_id)
        if to_status is None:
            raise EntityNotFoundError(STATUS, transition.to_status_id)

        instance.move_to(to_status.id, is_terminal=to_status.is_terminal)
        instance.mark_modified(actor_username)
        updated = await self._instances.update(instance)

        history = await self._instances.add_history(
            WorkflowHistoryEntry(
                instance_id=updated.id,
                from_status_id=from_status.id if from_status else None,
                to_status_id=to_status.id,
                action_code=action_code,
                actor_id=actor_id,
                actor_username=actor_username,
                comments=comments,
                ip_address=ip_address,
            )
        )

        logger.info(
            "Workflow transition: instance=%s action=%s %s -> %s terminal=%s",
            updated.id,
            action_code,
            from_status.code if from_status else "-",
            to_status.code,
            to_status.is_terminal,
        )

        return TransitionResult(
            instance=updated,
            from_status=from_status,
            to_status=to_status,
            transition=transition,
            history=history,
        )

    # ─── Internals ───

    async def _resolve(self, instance: WorkflowInstance) -> InstanceState:
        status = await self._definitions.get_status(instance.current_status_id)
        if status is None:
            raise EntityNotFoundError(STATUS, instance.current_status_id)

        definition = await self._definitions.get_by_id(
            instance.workflow_definition_id
        )
        if definition is None:
            raise EntityNotFoundError(
                "WorkflowDefinition", instance.workflow_definition_id
            )

        return InstanceState(instance=instance, status=status, definition=definition)
