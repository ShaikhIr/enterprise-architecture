"""
Workflow application service.

Two jobs, kept in one service because the screens that use them are the same
screens: configuring a workflow (definition, states, transitions) and running one
(start, act, inspect). Runtime work is delegated to `WorkflowEngine` so the
transition rules live in exactly one place.

Business rules enforced here rather than left to the database, so callers get a
409 with a reason instead of a 500 from a constraint:

- a definition cannot be deleted while instances reference it
- a definition has at most one initial state
- a state cannot be both initial and terminal
- a state cannot be deleted while transitions or live instances point at it
- a transition's endpoints must belong to the same definition
- no transition may leave a terminal state
"""

from uuid import UUID, uuid4

from src.api.v1.schemas.approval_matrix_schema import ApprovalTaskResponse
from src.api.v1.schemas.workflow_schema import (
    WorkflowActionRequest,
    WorkflowAvailableActionResponse,
    WorkflowDefinitionCreate,
    WorkflowDefinitionDetailResponse,
    WorkflowDefinitionListResponse,
    WorkflowDefinitionResponse,
    WorkflowDefinitionUpdate,
    WorkflowHistoryResponse,
    WorkflowInstanceListResponse,
    WorkflowInstanceResponse,
    WorkflowStartRequest,
    WorkflowStatusCreate,
    WorkflowStatusResponse,
    WorkflowStatusUpdate,
    WorkflowTransitionCreate,
    WorkflowTransitionResponse,
)
from src.application.services.workflow.state_machine_service import InstanceState
from src.application.services.workflow.workflow_engine import WorkflowEngine
from src.domain.entities.user import User
from src.domain.entities.workflow import (
    WorkflowDefinition,
    WorkflowInstance,
    WorkflowStatus,
    WorkflowTransition,
)
from src.domain.exceptions.domain_exceptions import (
    BusinessRuleViolationError,
    DuplicateEntityError,
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

DEFINITION = "WorkflowDefinition"
STATUS = "WorkflowStatus"
TRANSITION = "WorkflowTransition"
INSTANCE = "WorkflowInstance"


class WorkflowService:
    """Application service for workflow configuration and execution."""

    def __init__(
        self,
        workflow_definition_repo: IWorkflowDefinitionRepository,
        workflow_instance_repo: IWorkflowInstanceRepository,
        approval_matrix_repo: IApprovalMatrixRepository,
        role_assignment_repo: IRoleAssignmentRepository,
    ) -> None:
        self._definitions = workflow_definition_repo
        self._instances = workflow_instance_repo
        self._matrices = approval_matrix_repo
        self._engine = WorkflowEngine(
            definition_repo=workflow_definition_repo,
            instance_repo=workflow_instance_repo,
            matrix_repo=approval_matrix_repo,
            role_assignment_repo=role_assignment_repo,
        )

    # ═══════════════════════════ Definitions ═══════════════════════════

    async def list_definitions(
        self,
        skip: int = 0,
        limit: int = 100,
        search: str | None = None,
        is_active: bool | None = None,
        entity_type: str | None = None,
    ) -> WorkflowDefinitionListResponse:
        """Get a page of workflow definitions plus the total match count."""
        definitions = await self._definitions.list_all(
            skip=skip,
            limit=limit,
            search=search,
            is_active=is_active,
            entity_type=entity_type,
        )
        total = await self._definitions.count(
            search=search, is_active=is_active, entity_type=entity_type
        )
        return WorkflowDefinitionListResponse(
            definitions=[
                WorkflowDefinitionResponse.model_validate(d) for d in definitions
            ],
            total=total,
            skip=skip,
            limit=limit,
        )

    async def get_definition(self, definition_id: UUID) -> WorkflowDefinitionResponse:
        """Get a single definition. Raises EntityNotFoundError if missing."""
        return WorkflowDefinitionResponse.model_validate(
            await self._require_definition(definition_id)
        )

    async def get_definition_detail(
        self, definition_id: UUID
    ) -> WorkflowDefinitionDetailResponse:
        """Get a definition together with its states and transitions."""
        definition = await self._require_definition(definition_id)
        statuses = await self._definitions.list_statuses(definition_id)
        transitions = await self._definitions.list_transitions(definition_id)
        return WorkflowDefinitionDetailResponse(
            definition=WorkflowDefinitionResponse.model_validate(definition),
            statuses=[WorkflowStatusResponse.model_validate(s) for s in statuses],
            transitions=[
                WorkflowTransitionResponse.model_validate(t) for t in transitions
            ],
        )

    async def create_definition(
        self, request: WorkflowDefinitionCreate, actor: User
    ) -> WorkflowDefinitionResponse:
        """Create a definition after checking code and name uniqueness."""
        if await self._definitions.exists_by_code(request.code):
            raise DuplicateEntityError(DEFINITION, "code", request.code)
        if await self._definitions.exists_by_name(request.name):
            raise DuplicateEntityError(DEFINITION, "name", request.name)

        created = await self._definitions.create(
            WorkflowDefinition(
                id=uuid4(),
                code=request.code,
                name=request.name,
                description=request.description,
                entity_type=request.entity_type,
                version=1,
                is_active=request.is_active,
                created_by=actor.username,
                modified_by=actor.username,
            )
        )
        return WorkflowDefinitionResponse.model_validate(created)

    async def update_definition(
        self, definition_id: UUID, request: WorkflowDefinitionUpdate, actor: User
    ) -> WorkflowDefinitionResponse:
        """Apply a partial update to a definition."""
        definition = await self._require_definition(definition_id)

        if request.code is not None and request.code != definition.code:
            if await self._definitions.exists_by_code(
                request.code, exclude_id=definition_id
            ):
                raise DuplicateEntityError(DEFINITION, "code", request.code)
            definition.code = request.code

        if request.name is not None and request.name != definition.name:
            if await self._definitions.exists_by_name(
                request.name, exclude_id=definition_id
            ):
                raise DuplicateEntityError(DEFINITION, "name", request.name)
            definition.name = request.name

        if request.entity_type is not None:
            definition.entity_type = request.entity_type
        if request.description is not None:
            definition.description = request.description
        if request.is_active is not None:
            definition.is_active = request.is_active

        definition.mark_modified(actor.username)
        return WorkflowDefinitionResponse.model_validate(
            await self._definitions.update(definition)
        )

    async def delete_definition(self, definition_id: UUID) -> None:
        """Delete a definition, refusing while any instance still references it."""
        await self._require_definition(definition_id)

        in_use = await self._instances.count(definition_id=definition_id)
        if in_use:
            raise BusinessRuleViolationError(
                f"Workflow cannot be deleted: {in_use} instance(s) reference it. "
                "Deactivate it instead."
            )

        await self._definitions.delete(definition_id)

    # ═══════════════════════════ Statuses ═══════════════════════════

    async def list_statuses(self, definition_id: UUID) -> list[WorkflowStatusResponse]:
        """States of a definition, ordered by sequence."""
        await self._require_definition(definition_id)
        statuses = await self._definitions.list_statuses(definition_id)
        return [WorkflowStatusResponse.model_validate(s) for s in statuses]

    async def create_status(
        self, definition_id: UUID, request: WorkflowStatusCreate, actor: User
    ) -> WorkflowStatusResponse:
        """Add a state to a definition."""
        await self._require_definition(definition_id)
        self._reject_initial_and_terminal(
            is_initial=request.is_initial, is_terminal=request.is_terminal
        )

        if await self._definitions.exists_status_code(definition_id, request.code):
            raise DuplicateEntityError(STATUS, "code", request.code)
        if request.is_initial:
            await self._reject_second_initial(definition_id)

        created = await self._definitions.create_status(
            WorkflowStatus(
                id=uuid4(),
                workflow_definition_id=definition_id,
                code=request.code,
                name=request.name,
                is_initial=request.is_initial,
                is_terminal=request.is_terminal,
                sequence=request.sequence,
                created_by=actor.username,
                modified_by=actor.username,
            )
        )
        return WorkflowStatusResponse.model_validate(created)

    async def update_status(
        self, status_id: UUID, request: WorkflowStatusUpdate, actor: User
    ) -> WorkflowStatusResponse:
        """Apply a partial update to a state."""
        status = await self._require_status(status_id)

        target_initial = (
            request.is_initial if request.is_initial is not None else status.is_initial
        )
        target_terminal = (
            request.is_terminal if request.is_terminal is not None else status.is_terminal
        )
        self._reject_initial_and_terminal(
            is_initial=target_initial, is_terminal=target_terminal
        )

        if request.code is not None and request.code != status.code:
            if await self._definitions.exists_status_code(
                status.workflow_definition_id, request.code, exclude_id=status_id
            ):
                raise DuplicateEntityError(STATUS, "code", request.code)
            status.code = request.code

        if target_initial and not status.is_initial:
            await self._reject_second_initial(
                status.workflow_definition_id, exclude_id=status_id
            )

        if request.name is not None:
            status.name = request.name
        if request.sequence is not None:
            status.sequence = request.sequence
        status.is_initial = target_initial
        status.is_terminal = target_terminal

        status.mark_modified(actor.username)
        return WorkflowStatusResponse.model_validate(
            await self._definitions.update_status(status)
        )

    async def delete_status(self, status_id: UUID) -> None:
        """Delete a state, refusing while it is wired up or occupied."""
        await self._require_status(status_id)

        wired = await self._definitions.count_transitions_touching_status(status_id)
        if wired:
            raise BusinessRuleViolationError(
                f"State cannot be deleted: {wired} transition(s) reference it"
            )

        occupied = await self._definitions.count_instances_in_status(status_id)
        if occupied:
            raise BusinessRuleViolationError(
                f"State cannot be deleted: {occupied} instance(s) are currently in it"
            )

        await self._definitions.delete_status(status_id)

    # ═══════════════════════════ Transitions ═══════════════════════════

    async def list_transitions(
        self, definition_id: UUID
    ) -> list[WorkflowTransitionResponse]:
        """Transitions of a definition, ordered by priority."""
        await self._require_definition(definition_id)
        transitions = await self._definitions.list_transitions(definition_id)
        return [WorkflowTransitionResponse.model_validate(t) for t in transitions]

    async def create_transition(
        self, definition_id: UUID, request: WorkflowTransitionCreate, actor: User
    ) -> WorkflowTransitionResponse:
        """Wire an action from one state of a definition to another."""
        await self._require_definition(definition_id)

        from_status = await self._require_status(request.from_status_id)
        to_status = await self._require_status(request.to_status_id)

        for status in (from_status, to_status):
            if status.workflow_definition_id != definition_id:
                raise BusinessRuleViolationError(
                    f"State '{status.code}' belongs to a different workflow"
                )

        if from_status.is_terminal:
            raise BusinessRuleViolationError(
                f"State '{from_status.code}' is terminal, so no action can leave it"
            )
        if from_status.id == to_status.id:
            raise BusinessRuleViolationError(
                "A transition must move between two different states"
            )

        if await self._definitions.exists_transition(
            definition_id, request.from_status_id, request.action_code
        ):
            raise DuplicateEntityError(
                TRANSITION,
                "action_code",
                f"{request.action_code} from {from_status.code}",
            )

        created = await self._definitions.create_transition(
            WorkflowTransition(
                id=uuid4(),
                workflow_definition_id=definition_id,
                from_status_id=request.from_status_id,
                to_status_id=request.to_status_id,
                action_code=request.action_code,
                action_type=request.action_type,
                guard_expression=request.guard_expression,
                requires_comment=request.requires_comment,
                auto_execute=request.auto_execute,
                priority=request.priority,
                created_by=actor.username,
                modified_by=actor.username,
            )
        )
        return WorkflowTransitionResponse.model_validate(created)

    async def delete_transition(self, transition_id: UUID) -> None:
        """Delete a transition."""
        if await self._definitions.get_transition(transition_id) is None:
            raise EntityNotFoundError(TRANSITION, transition_id)
        await self._definitions.delete_transition(transition_id)

    # ═══════════════════════════ Runtime ═══════════════════════════

    async def start_workflow(
        self, request: WorkflowStartRequest, actor: User
    ) -> WorkflowInstanceResponse:
        """Open a workflow instance against one business record."""
        state = await self._engine.start(
            definition_code=request.definition_code,
            entity_type=request.entity_type,
            entity_id=request.entity_id,
            initiated_by=actor.id,
            actor_username=actor.username,
            priority=request.priority,
            metadata=request.metadata,
        )
        return self._instance_response(state)

    async def execute_action(
        self,
        instance_id: UUID,
        request: WorkflowActionRequest,
        actor: User,
        ip_address: str = "",
    ) -> WorkflowInstanceResponse:
        """Execute an action and return the instance's new state."""
        result = await self._engine.execute_action(
            instance_id=instance_id,
            action_code=request.action_code,
            actor_id=actor.id,
            actor_username=actor.username,
            comments=request.comments,
            ip_address=ip_address,
        )
        definition = await self._require_definition(
            result.instance.workflow_definition_id
        )
        return self._build_instance_response(
            instance=result.instance, status=result.to_status, definition=definition
        )

    async def get_instance(self, instance_id: UUID) -> WorkflowInstanceResponse:
        """Current state of one instance."""
        return self._instance_response(await self._engine.get_state(instance_id))

    async def list_instances(
        self,
        skip: int = 0,
        limit: int = 100,
        entity_type: str | None = None,
        entity_id: UUID | None = None,
        definition_id: UUID | None = None,
        status_id: UUID | None = None,
        is_completed: bool | None = None,
    ) -> WorkflowInstanceListResponse:
        """Get a page of instances with their definition and state resolved."""
        instances = await self._instances.list_all(
            skip=skip,
            limit=limit,
            entity_type=entity_type,
            entity_id=entity_id,
            definition_id=definition_id,
            status_id=status_id,
            is_completed=is_completed,
        )
        total = await self._instances.count(
            entity_type=entity_type,
            entity_id=entity_id,
            definition_id=definition_id,
            status_id=status_id,
            is_completed=is_completed,
        )

        # Two batched lookups rather than two queries per row.
        definitions = {
            d.id: d
            for d in await self._definitions.get_definitions_by_ids(
                [i.workflow_definition_id for i in instances]
            )
        }
        statuses = {
            s.id: s
            for s in await self._definitions.get_statuses_by_ids(
                [i.current_status_id for i in instances]
            )
        }

        rows = []
        for instance in instances:
            definition = definitions.get(instance.workflow_definition_id)
            status = statuses.get(instance.current_status_id)
            if definition is None or status is None:
                # Foreign keys are RESTRICT, so this means the row was changed
                # underneath us; skipping beats returning a half-populated row.
                continue
            rows.append(
                self._build_instance_response(
                    instance=instance, status=status, definition=definition
                )
            )

        return WorkflowInstanceListResponse(
            instances=rows, total=total, skip=skip, limit=limit
        )

    async def available_actions(
        self, instance_id: UUID
    ) -> list[WorkflowAvailableActionResponse]:
        """Actions the instance's current state offers."""
        transitions = await self._engine.available_actions(instance_id)
        statuses = {
            s.id: s
            for s in await self._definitions.get_statuses_by_ids(
                [t.to_status_id for t in transitions]
            )
        }

        actions = []
        for transition in transitions:
            target = statuses.get(transition.to_status_id)
            if target is None:
                continue
            actions.append(
                WorkflowAvailableActionResponse(
                    action_code=transition.action_code,
                    action_type=transition.action_type,
                    to_status_id=target.id,
                    to_status_code=target.code,
                    to_status_name=target.name,
                    requires_comment=transition.requires_comment,
                    is_terminal=target.is_terminal,
                )
            )
        return actions

    async def instance_history(
        self, instance_id: UUID
    ) -> list[WorkflowHistoryResponse]:
        """Audit trail for one instance, newest first."""
        if await self._instances.get_by_id(instance_id) is None:
            raise EntityNotFoundError(INSTANCE, instance_id)

        entries = await self._instances.list_history(instance_id)
        referenced = [e.to_status_id for e in entries]
        referenced += [e.from_status_id for e in entries if e.from_status_id]
        statuses = {
            s.id: s for s in await self._definitions.get_statuses_by_ids(referenced)
        }

        return [
            WorkflowHistoryResponse(
                id=entry.id,
                instance_id=entry.instance_id,
                from_status_id=entry.from_status_id,
                from_status_code=(
                    statuses[entry.from_status_id].code
                    if entry.from_status_id in statuses
                    else None
                ),
                to_status_id=entry.to_status_id,
                to_status_code=(
                    statuses[entry.to_status_id].code
                    if entry.to_status_id in statuses
                    else None
                ),
                action_code=entry.action_code,
                actor_id=entry.actor_id,
                actor_username=entry.actor_username,
                comments=entry.comments,
                ip_address=entry.ip_address,
                created_at=entry.created_at,
            )
            for entry in entries
        ]

    async def my_tasks(self, user_id: UUID) -> list[ApprovalTaskResponse]:
        """Open approval tasks assigned to a user."""
        tasks = await self._engine.pending_tasks(user_id)
        return [ApprovalTaskResponse.model_validate(t) for t in tasks]

    async def instance_tasks(self, instance_id: UUID) -> list[ApprovalTaskResponse]:
        """
        Every approval task raised for an instance, open or settled.

        The full chain rather than just the open level, so the record shows who was
        asked and who was cancelled when someone else got there first.
        """
        if await self._instances.get_by_id(instance_id) is None:
            raise EntityNotFoundError(INSTANCE, instance_id)
        tasks = await self._matrices.list_tasks_for_instance(instance_id)
        return [ApprovalTaskResponse.model_validate(t) for t in tasks]

    # ═══════════════════════════ Internals ═══════════════════════════

    async def _require_definition(self, definition_id: UUID) -> WorkflowDefinition:
        definition = await self._definitions.get_by_id(definition_id)
        if definition is None:
            raise EntityNotFoundError(DEFINITION, definition_id)
        return definition

    async def _require_status(self, status_id: UUID) -> WorkflowStatus:
        status = await self._definitions.get_status(status_id)
        if status is None:
            raise EntityNotFoundError(STATUS, status_id)
        return status

    async def _reject_second_initial(
        self, definition_id: UUID, exclude_id: UUID | None = None
    ) -> None:
        existing = await self._definitions.get_initial_status(definition_id)
        if existing is not None and existing.id != exclude_id:
            raise BusinessRuleViolationError(
                f"Workflow already has an initial state ('{existing.code}'); "
                "clear it before setting another"
            )

    @staticmethod
    def _reject_initial_and_terminal(*, is_initial: bool, is_terminal: bool) -> None:
        if is_initial and is_terminal:
            raise BusinessRuleViolationError(
                "A state cannot be both initial and terminal"
            )

    @staticmethod
    def _instance_response(state: InstanceState) -> WorkflowInstanceResponse:
        return WorkflowService._build_instance_response(
            instance=state.instance, status=state.status, definition=state.definition
        )

    @staticmethod
    def _build_instance_response(
        *,
        instance: WorkflowInstance,
        status: WorkflowStatus,
        definition: WorkflowDefinition,
    ) -> WorkflowInstanceResponse:
        """Flatten instance, state and definition into one row for the client."""
        return WorkflowInstanceResponse(
            id=instance.id,
            workflow_definition_id=definition.id,
            definition_code=definition.code,
            definition_name=definition.name,
            entity_type=instance.entity_type,
            entity_id=instance.entity_id,
            current_status_id=status.id,
            current_status_code=status.code,
            current_status_name=status.name,
            is_terminal=status.is_terminal,
            initiated_by=instance.initiated_by,
            priority=instance.priority,
            due_date=instance.due_date,
            started_at=instance.started_at,
            completed_at=instance.completed_at,
            is_completed=instance.is_completed,
            approval_level=instance.approval_level,
            is_awaiting_approval=instance.is_awaiting_approval,
            metadata=instance.extra_data,
        )
