"""
Workflow engine.

The single entry point other modules use to drive a workflow: start one, act on
one, ask what can be done next. Business modules should never read the workflow
tables themselves, so that the state machine stays the only thing that decides
what a valid move is.

Composition: the engine holds the state machine (transition rules) and the
approval matrix resolver (routing), and owns the cross-cutting decisions that
need both — such as retiring outstanding approval tasks once an instance reaches
a terminal state.
"""

import logging
from typing import Any
from uuid import UUID

from src.application.services.workflow.approval_matrix_resolver import (
    ApprovalMatrixResolver,
    ResolvedApprovers,
)
from src.application.services.workflow.approval_task_coordinator import (
    ApprovalTaskCoordinator,
)
from src.application.services.workflow.state_machine_service import (
    InstanceState,
    StateMachineService,
    TransitionResult,
)
from src.domain.entities.approval_matrix import ApprovalTask
from src.domain.entities.workflow import WorkflowInstance, WorkflowTransition
from src.domain.exceptions.domain_exceptions import (
    BusinessRuleViolationError,
    EntityNotFoundError,
)
from src.domain.repositories.approval_matrix_repository import IApprovalMatrixRepository
from src.domain.repositories.role_assignment_repository import IRoleAssignmentRepository
from src.domain.repositories.workflow_definition_repository import (
    IWorkflowDefinitionRepository,
)
from src.domain.repositories.workflow_instance_repository import (
    IWorkflowInstanceRepository,
)

logger = logging.getLogger(__name__)

DEFINITION = "WorkflowDefinition"
INSTANCE = "WorkflowInstance"


class WorkflowEngine:
    """Orchestrates workflow execution on top of the state machine."""

    def __init__(
        self,
        definition_repo: IWorkflowDefinitionRepository,
        instance_repo: IWorkflowInstanceRepository,
        matrix_repo: IApprovalMatrixRepository,
        role_assignment_repo: IRoleAssignmentRepository,
    ) -> None:
        self._definitions = definition_repo
        self._instances = instance_repo
        self._matrices = matrix_repo
        self._state_machine = StateMachineService(definition_repo, instance_repo)
        self._resolver = ApprovalMatrixResolver(matrix_repo)
        self._approvals = ApprovalTaskCoordinator(
            matrix_repo, role_assignment_repo, self._resolver
        )

    # ─── Lifecycle ───

    async def start(
        self,
        *,
        definition_code: str,
        entity_type: str,
        entity_id: UUID,
        initiated_by: UUID,
        actor_username: str,
        priority: int = 0,
        metadata: dict[str, Any] | None = None,
    ) -> InstanceState:
        """
        Open a workflow instance for one business record.

        Raises:
            EntityNotFoundError: No such definition code.
            BusinessRuleViolationError: The definition is inactive, has no initial
                state, is bound to a different entity type, or the record already
                has a workflow in flight.
        """
        definition = await self._definitions.get_by_code(definition_code)
        if definition is None:
            raise EntityNotFoundError(DEFINITION, definition_code)
        if not definition.is_active:
            raise BusinessRuleViolationError(
                f"Workflow '{definition_code}' is inactive and cannot be started"
            )
        if definition.entity_type != entity_type:
            raise BusinessRuleViolationError(
                f"Workflow '{definition_code}' is defined for entity type "
                f"'{definition.entity_type}', not '{entity_type}'"
            )

        initial_status = await self._definitions.get_initial_status(definition.id)
        if initial_status is None:
            raise BusinessRuleViolationError(
                f"Workflow '{definition_code}' has no initial state configured"
            )

        in_flight = await self._instances.get_open_for_entity(entity_type, entity_id)
        if in_flight is not None:
            raise BusinessRuleViolationError(
                f"{entity_type} '{entity_id}' already has an open workflow instance "
                f"({in_flight.id})"
            )

        instance = await self._instances.create(
            WorkflowInstance(
                workflow_definition_id=definition.id,
                entity_type=entity_type,
                entity_id=entity_id,
                current_status_id=initial_status.id,
                initiated_by=initiated_by,
                priority=priority,
                extra_data=metadata or {},
                created_by=actor_username,
                modified_by=actor_username,
            )
        )

        logger.info(
            "Workflow started: definition=%s entity=%s/%s instance=%s state=%s",
            definition_code,
            entity_type,
            entity_id,
            instance.id,
            initial_status.code,
        )

        return InstanceState(
            instance=instance, status=initial_status, definition=definition
        )

    async def execute_action(
        self,
        *,
        instance_id: UUID,
        action_code: str,
        actor_id: UUID,
        actor_username: str,
        comments: str = "",
        ip_address: str = "",
    ) -> TransitionResult:
        """
        Apply an action to an instance and settle the approval chain around it.

        The state move happens first and is authoritative — if it is illegal,
        nothing about the approval chain is touched. The coordinator then reacts to
        what the transition declared it means, which is what opens level 1 on
        SUBMIT, steps to the next level on APPROVE, and tears the chain down on a
        rejection, a cancellation or a refer-back.
        """
        instance = await self._instances.get_by_id(instance_id)
        if instance is None:
            raise EntityNotFoundError(INSTANCE, instance_id)

        result = await self._state_machine.execute(
            instance=instance,
            action_code=action_code,
            actor_id=actor_id,
            actor_username=actor_username,
            comments=comments,
            ip_address=ip_address,
        )

        transition = result.transition
        await self._approvals.apply(
            instance=result.instance,
            action_type=transition.action_type,
            actor_id=actor_id,
            actor_username=actor_username,
            comments=comments,
            reached_terminal_state=result.to_status.is_terminal,
        )

        # The coordinator moves `approval_level` on the instance; persist that in
        # the same request so the level and the tasks cannot disagree.
        updated = await self._instances.update(result.instance)

        return TransitionResult(
            instance=updated,
            from_status=result.from_status,
            to_status=result.to_status,
            transition=transition,
            history=result.history,
        )

    # ─── Reads ───

    async def get_state(self, instance_id: UUID) -> InstanceState:
        """Current status and definition of an instance."""
        return await self._state_machine.get_state(instance_id)

    async def available_actions(self, instance_id: UUID) -> list[WorkflowTransition]:
        """Actions the current state allows, empty once the instance is finished."""
        instance = await self._instances.get_by_id(instance_id)
        if instance is None:
            raise EntityNotFoundError(INSTANCE, instance_id)
        return await self._state_machine.available_actions(instance)

    async def pending_tasks(self, user_id: UUID) -> list[ApprovalTask]:
        """Open approval tasks assigned to a user."""
        return await self._matrices.list_pending_tasks_for_user(user_id)

    async def resolve_approvers(
        self, entity_type: str, entity_data: dict[str, Any]
    ) -> ResolvedApprovers | None:
        """
        Preview which matrix would route a record, and to whom.

        Exposed so the rule configuration can be checked against a sample payload
        before it is relied on.
        """
        return await self._resolver.resolve(entity_type, entity_data)
