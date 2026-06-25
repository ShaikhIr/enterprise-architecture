"""
Workflow Management API endpoints.
CRUD for workflow definitions, statuses, transitions, and runtime operations.
"""

from uuid import UUID, uuid4

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.api.v1.dependencies import get_current_active_user
from src.domain.entities.user import User
from src.infrastructure.database.session import get_db_session
from src.infrastructure.security.permission_manager import require_permission
from src.api.v1.endpoints.workflow.schemas import (
    ApprovalMatrixCreate,
    ApprovalMatrixResponse,
    ApprovalTaskResponse,
    WorkflowActionRequest,
    WorkflowDefinitionCreate,
    WorkflowDefinitionListResponse,
    WorkflowDefinitionResponse,
    WorkflowHistoryResponse,
    WorkflowInstanceResponse,
    WorkflowStartRequest,
    WorkflowStatusCreate,
    WorkflowStatusResponse,
    WorkflowTransitionCreate,
    WorkflowTransitionResponse,
)
from src.application.services.workflow.workflow_engine import WorkflowEngine
from src.infrastructure.database.models.workflow.approval_matrix_models import (
    ApprovalAssignmentModel,
    ApprovalMatrixModel,
    ApprovalRuleModel,
    ApprovalTaskModel,
)
from src.infrastructure.database.models.workflow.workflow_models import (
    WorkflowDefinitionModel,
    WorkflowHistoryModel,
    WorkflowInstanceModel,
    WorkflowStatusModel,
    WorkflowTransitionModel,
)

router = APIRouter(prefix="/workflow", tags=["Workflow Engine"])


# ═══════════════════════════════════════════════════════════════════
# WORKFLOW DEFINITIONS
# ═══════════════════════════════════════════════════════════════════


@router.get(
    "/definitions",
    response_model=WorkflowDefinitionListResponse,
    summary="List workflow definitions",
)
async def list_definitions(
    current_user: User = Depends(get_current_active_user),
    session: AsyncSession = Depends(get_db_session),
) -> WorkflowDefinitionListResponse:
    """GET /workflow/definitions"""
    stmt = select(WorkflowDefinitionModel).order_by(WorkflowDefinitionModel.code)
    result = await session.execute(stmt)
    definitions = result.scalars().all()
    return WorkflowDefinitionListResponse(
        definitions=[WorkflowDefinitionResponse.model_validate(d) for d in definitions],
        total=len(definitions),
    )


@router.post(
    "/definitions",
    response_model=WorkflowDefinitionResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create workflow definition",
)
async def create_definition(
    request: WorkflowDefinitionCreate,
    current_user: User = Depends(get_current_active_user),
    session: AsyncSession = Depends(get_db_session),
) -> WorkflowDefinitionResponse:
    """POST /workflow/definitions"""
    existing = await session.execute(
        select(WorkflowDefinitionModel).where(WorkflowDefinitionModel.code == request.code)
    )
    if existing.scalar_one_or_none():
        raise HTTPException(status_code=409, detail=f"Workflow '{request.code}' already exists")

    definition = WorkflowDefinitionModel(
        id=uuid4(),
        code=request.code,
        name=request.name,
        description=request.description,
        entity_type=request.entity_type,
        version=1,
        is_active=True,
        created_by=current_user.username,
        modified_by=current_user.username,
    )
    session.add(definition)
    await session.flush()
    return WorkflowDefinitionResponse.model_validate(definition)


@router.get(
    "/definitions/{definition_id}",
    summary="Get workflow definition with statuses and transitions",
)
async def get_definition(
    definition_id: UUID,
    current_user: User = Depends(get_current_active_user),
    session: AsyncSession = Depends(get_db_session),
) -> dict:
    """GET /workflow/definitions/{id} — full definition with statuses and transitions."""
    definition = await session.get(WorkflowDefinitionModel, str(definition_id))
    if not definition:
        raise HTTPException(status_code=404, detail="Definition not found")

    # Load statuses
    statuses_stmt = (
        select(WorkflowStatusModel)
        .where(WorkflowStatusModel.workflow_definition_id == str(definition_id))
        .order_by(WorkflowStatusModel.sequence)
    )
    statuses = (await session.execute(statuses_stmt)).scalars().all()

    # Load transitions
    transitions_stmt = select(WorkflowTransitionModel).where(
        WorkflowTransitionModel.workflow_definition_id == str(definition_id)
    )
    transitions = (await session.execute(transitions_stmt)).scalars().all()

    return {
        "definition": WorkflowDefinitionResponse.model_validate(definition),
        "statuses": [WorkflowStatusResponse.model_validate(s) for s in statuses],
        "transitions": [WorkflowTransitionResponse.model_validate(t) for t in transitions],
    }


# ═══════════════════════════════════════════════════════════════════
# WORKFLOW STATUSES
# ═══════════════════════════════════════════════════════════════════


@router.post(
    "/definitions/{definition_id}/statuses",
    response_model=WorkflowStatusResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Add status to workflow",
)
async def create_status(
    definition_id: UUID,
    request: WorkflowStatusCreate,
    current_user: User = Depends(get_current_active_user),
    session: AsyncSession = Depends(get_db_session),
) -> WorkflowStatusResponse:
    """POST /workflow/definitions/{id}/statuses"""
    definition = await session.get(WorkflowDefinitionModel, str(definition_id))
    if not definition:
        raise HTTPException(status_code=404, detail="Definition not found")

    wf_status = WorkflowStatusModel(
        id=uuid4(),
        workflow_definition_id=str(definition_id),
        code=request.code,
        name=request.name,
        is_initial=request.is_initial,
        is_terminal=request.is_terminal,
        sequence=request.sequence,
        created_by=current_user.username,
        modified_by=current_user.username,
    )
    session.add(wf_status)
    await session.flush()
    return WorkflowStatusResponse.model_validate(wf_status)


@router.get(
    "/definitions/{definition_id}/statuses",
    response_model=list[WorkflowStatusResponse],
    summary="List statuses for a workflow",
)
async def list_statuses(
    definition_id: UUID,
    current_user: User = Depends(get_current_active_user),
    session: AsyncSession = Depends(get_db_session),
) -> list[WorkflowStatusResponse]:
    """GET /workflow/definitions/{id}/statuses"""
    stmt = (
        select(WorkflowStatusModel)
        .where(WorkflowStatusModel.workflow_definition_id == str(definition_id))
        .order_by(WorkflowStatusModel.sequence)
    )
    result = await session.execute(stmt)
    return [WorkflowStatusResponse.model_validate(s) for s in result.scalars().all()]


# ═══════════════════════════════════════════════════════════════════
# WORKFLOW TRANSITIONS
# ═══════════════════════════════════════════════════════════════════


@router.post(
    "/definitions/{definition_id}/transitions",
    response_model=WorkflowTransitionResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Add transition to workflow",
)
async def create_transition(
    definition_id: UUID,
    request: WorkflowTransitionCreate,
    current_user: User = Depends(get_current_active_user),
    session: AsyncSession = Depends(get_db_session),
) -> WorkflowTransitionResponse:
    """POST /workflow/definitions/{id}/transitions"""
    transition = WorkflowTransitionModel(
        id=uuid4(),
        workflow_definition_id=str(definition_id),
        from_status_id=str(request.from_status_id),
        to_status_id=str(request.to_status_id),
        action_code=request.action_code,
        guard_expression=request.guard_expression,
        requires_comment=request.requires_comment,
        auto_execute=request.auto_execute,
        priority=request.priority,
        created_by=current_user.username,
        modified_by=current_user.username,
    )
    session.add(transition)
    await session.flush()
    return WorkflowTransitionResponse.model_validate(transition)


@router.delete(
    "/transitions/{transition_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete a transition",
)
async def delete_transition(
    transition_id: UUID,
    current_user: User = Depends(get_current_active_user),
    session: AsyncSession = Depends(get_db_session),
) -> None:
    """DELETE /workflow/transitions/{id}"""
    transition = await session.get(WorkflowTransitionModel, str(transition_id))
    if not transition:
        raise HTTPException(status_code=404, detail="Transition not found")
    await session.delete(transition)


# ═══════════════════════════════════════════════════════════════════
# WORKFLOW RUNTIME
# ═══════════════════════════════════════════════════════════════════


@router.post(
    "/start",
    status_code=status.HTTP_201_CREATED,
    summary="Start a workflow instance",
)
async def start_workflow(
    request: WorkflowStartRequest,
    current_user: User = Depends(get_current_active_user),
    session: AsyncSession = Depends(get_db_session),
) -> dict:
    """POST /workflow/start"""
    engine = WorkflowEngine(session)
    result = await engine.start_workflow(
        definition_code=request.definition_code,
        entity_type=request.entity_type,
        entity_id=request.entity_id,
        initiated_by=current_user.id,
        metadata=request.metadata,
    )
    return result


@router.post(
    "/instances/{instance_id}/action",
    summary="Execute action on workflow instance",
)
async def execute_action(
    instance_id: UUID,
    request: WorkflowActionRequest,
    current_user: User = Depends(get_current_active_user),
    session: AsyncSession = Depends(get_db_session),
) -> dict:
    """POST /workflow/instances/{id}/action"""
    engine = WorkflowEngine(session)
    result = await engine.execute_action(
        instance_id=instance_id,
        action_code=request.action_code,
        actor_id=current_user.id,
        actor_username=current_user.username,
        comments=request.comments,
    )
    return result


@router.get(
    "/instances/{instance_id}",
    summary="Get workflow instance status",
)
async def get_instance(
    instance_id: UUID,
    current_user: User = Depends(get_current_active_user),
    session: AsyncSession = Depends(get_db_session),
) -> dict:
    """GET /workflow/instances/{id}"""
    engine = WorkflowEngine(session)
    return await engine.get_workflow_status(instance_id)


@router.get(
    "/instances/{instance_id}/actions",
    summary="Get available actions for instance",
)
async def get_instance_actions(
    instance_id: UUID,
    current_user: User = Depends(get_current_active_user),
    session: AsyncSession = Depends(get_db_session),
) -> list[dict]:
    """GET /workflow/instances/{id}/actions"""
    engine = WorkflowEngine(session)
    return await engine.get_available_actions(instance_id)


@router.get(
    "/instances/{instance_id}/history",
    response_model=list[WorkflowHistoryResponse],
    summary="Get workflow instance history",
)
async def get_instance_history(
    instance_id: UUID,
    current_user: User = Depends(get_current_active_user),
    session: AsyncSession = Depends(get_db_session),
) -> list[WorkflowHistoryResponse]:
    """GET /workflow/instances/{id}/history"""
    stmt = (
        select(WorkflowHistoryModel)
        .where(WorkflowHistoryModel.instance_id == str(instance_id))
        .order_by(WorkflowHistoryModel.created_at.desc())
    )
    result = await session.execute(stmt)
    return [WorkflowHistoryResponse.model_validate(h) for h in result.scalars().all()]


@router.get(
    "/my-tasks",
    summary="Get pending approval tasks for current user",
)
async def get_my_tasks(
    current_user: User = Depends(get_current_active_user),
    session: AsyncSession = Depends(get_db_session),
) -> list[dict]:
    """GET /workflow/my-tasks"""
    engine = WorkflowEngine(session)
    return await engine.get_pending_tasks(current_user.id)


# ═══════════════════════════════════════════════════════════════════
# APPROVAL MATRIX
# ═══════════════════════════════════════════════════════════════════


@router.get(
    "/approval-matrices",
    summary="List approval matrices",
)
async def list_approval_matrices(
    current_user: User = Depends(get_current_active_user),
    session: AsyncSession = Depends(get_db_session),
) -> list[ApprovalMatrixResponse]:
    """GET /workflow/approval-matrices"""
    stmt = select(ApprovalMatrixModel).order_by(ApprovalMatrixModel.priority)
    result = await session.execute(stmt)
    matrices = result.scalars().all()

    response = []
    for matrix in matrices:
        # Load rules
        rules_stmt = select(ApprovalRuleModel).where(ApprovalRuleModel.matrix_id == str(matrix.id))
        rules = (await session.execute(rules_stmt)).scalars().all()

        # Load assignments
        assign_stmt = (
            select(ApprovalAssignmentModel)
            .where(ApprovalAssignmentModel.matrix_id == str(matrix.id))
            .order_by(ApprovalAssignmentModel.level)
        )
        assignments = (await session.execute(assign_stmt)).scalars().all()

        response.append(ApprovalMatrixResponse(
            id=matrix.id,
            code=matrix.code,
            name=matrix.name,
            entity_type=matrix.entity_type,
            priority=matrix.priority,
            is_active=matrix.is_active,
            rules=[{"field": r.field, "operator": r.operator, "value": r.value, "data_type": r.data_type, "logical_group": r.logical_group} for r in rules],
            assignments=[{"level": a.level, "assignment_type": a.assignment_type, "user_id": str(a.user_id) if a.user_id else None, "role_id": str(a.role_id) if a.role_id else None} for a in assignments],
        ))

    return response


@router.post(
    "/approval-matrices",
    response_model=ApprovalMatrixResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create approval matrix with rules and assignments",
)
async def create_approval_matrix(
    request: ApprovalMatrixCreate,
    current_user: User = Depends(get_current_active_user),
    session: AsyncSession = Depends(get_db_session),
) -> ApprovalMatrixResponse:
    """POST /workflow/approval-matrices"""
    existing = await session.execute(
        select(ApprovalMatrixModel).where(ApprovalMatrixModel.code == request.code)
    )
    if existing.scalar_one_or_none():
        raise HTTPException(status_code=409, detail=f"Matrix '{request.code}' already exists")

    matrix = ApprovalMatrixModel(
        id=uuid4(),
        code=request.code,
        name=request.name,
        entity_type=request.entity_type,
        priority=request.priority,
        is_active=True,
        created_by=current_user.username,
        modified_by=current_user.username,
    )
    session.add(matrix)
    await session.flush()

    # Create rules
    for rule in request.rules:
        r = ApprovalRuleModel(
            id=uuid4(),
            matrix_id=str(matrix.id),
            field=rule.field,
            operator=rule.operator,
            value=rule.value,
            data_type=rule.data_type,
            logical_group=rule.logical_group,
            created_by=current_user.username,
            modified_by=current_user.username,
        )
        session.add(r)

    # Create assignments
    for assignment in request.assignments:
        a = ApprovalAssignmentModel(
            id=uuid4(),
            matrix_id=str(matrix.id),
            assignment_type=assignment.assignment_type,
            user_id=str(assignment.user_id) if assignment.user_id else None,
            role_id=str(assignment.role_id) if assignment.role_id else None,
            level=assignment.level,
            created_by=current_user.username,
            modified_by=current_user.username,
        )
        session.add(a)

    return ApprovalMatrixResponse(
        id=matrix.id,
        code=matrix.code,
        name=matrix.name,
        entity_type=request.entity_type,
        priority=request.priority,
        is_active=matrix.is_active,
        rules=[{"field": r.field, "operator": r.operator, "value": r.value, "data_type": r.data_type, "logical_group": r.logical_group} for r in request.rules],
        assignments=[{"level": a.level, "assignment_type": a.assignment_type, "user_id": str(a.user_id) if a.user_id else None, "role_id": str(a.role_id) if a.role_id else None} for a in request.assignments],
    )


@router.put(
    "/approval-matrices/{matrix_id}",
    response_model=ApprovalMatrixResponse,
    summary="Update approval matrix (replaces rules and assignments)",
)
async def update_approval_matrix(
    matrix_id: UUID,
    request: ApprovalMatrixCreate,
    current_user: User = Depends(get_current_active_user),
    session: AsyncSession = Depends(get_db_session),
) -> ApprovalMatrixResponse:
    """PUT /workflow/approval-matrices/{id} — Update matrix, rules, and assignments."""
    matrix = await session.get(ApprovalMatrixModel, str(matrix_id))
    if not matrix:
        raise HTTPException(status_code=404, detail="Approval matrix not found")

    # Update basic fields
    matrix.name = request.name
    matrix.entity_type = request.entity_type
    matrix.priority = request.priority
    matrix.modified_by = current_user.username

    # Delete existing rules
    existing_rules = await session.execute(
        select(ApprovalRuleModel).where(ApprovalRuleModel.matrix_id == str(matrix_id))
    )
    for r in existing_rules.scalars().all():
        await session.delete(r)

    # Delete existing assignments
    existing_assigns = await session.execute(
        select(ApprovalAssignmentModel).where(ApprovalAssignmentModel.matrix_id == str(matrix_id))
    )
    for a in existing_assigns.scalars().all():
        await session.delete(a)

    await session.flush()

    # Create new rules
    for rule in request.rules:
        r = ApprovalRuleModel(
            id=uuid4(),
            matrix_id=str(matrix_id),
            field=rule.field,
            operator=rule.operator,
            value=rule.value,
            data_type=rule.data_type,
            logical_group=rule.logical_group,
            created_by=current_user.username,
            modified_by=current_user.username,
        )
        session.add(r)

    # Create new assignments
    for assignment in request.assignments:
        a = ApprovalAssignmentModel(
            id=uuid4(),
            matrix_id=str(matrix_id),
            assignment_type=assignment.assignment_type,
            user_id=str(assignment.user_id) if assignment.user_id else None,
            role_id=str(assignment.role_id) if assignment.role_id else None,
            level=assignment.level,
            created_by=current_user.username,
            modified_by=current_user.username,
        )
        session.add(a)

    return ApprovalMatrixResponse(
        id=matrix.id,
        code=matrix.code,
        name=request.name,
        entity_type=request.entity_type,
        priority=request.priority,
        is_active=matrix.is_active,
        rules=[{"field": r.field, "operator": r.operator, "value": r.value, "data_type": r.data_type, "logical_group": r.logical_group} for r in request.rules],
        assignments=[{"level": a.level, "assignment_type": a.assignment_type, "user_id": str(a.user_id) if a.user_id else None, "role_id": str(a.role_id) if a.role_id else None} for a in request.assignments],
    )
