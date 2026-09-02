"""
Workflow configuration API endpoints.

Covers the definition and the state machine wired under it. Runtime execution
lives in `workflow_instance_controller` so that permission to design a workflow
is separable from permission to act on one.

Thin controller — all business logic sits in WorkflowService.
"""


from fastapi import APIRouter, Depends, Query, status

from src.api.v1.dependencies import (
    get_approval_matrix_repository,
    get_current_active_user,
    get_role_assignment_repository,
    get_workflow_definition_repository,
    get_workflow_instance_repository,
)
from src.api.v1.schemas.workflow_schema import (
    WorkflowDefinitionCreate,
    WorkflowDefinitionDetailResponse,
    WorkflowDefinitionListResponse,
    WorkflowDefinitionResponse,
    WorkflowDefinitionUpdate,
    WorkflowStatusCreate,
    WorkflowStatusResponse,
    WorkflowStatusUpdate,
    WorkflowTransitionCreate,
    WorkflowTransitionResponse,
)
from src.application.services.workflow_service import WorkflowService
from src.domain.entities.user import User
from src.domain.repositories.approval_matrix_repository import IApprovalMatrixRepository
from src.domain.repositories.role_assignment_repository import IRoleAssignmentRepository
from src.domain.repositories.workflow_definition_repository import (
    IWorkflowDefinitionRepository,
)
from src.domain.repositories.workflow_instance_repository import (
    IWorkflowInstanceRepository,
)
from src.infrastructure.security.permission_manager import require_api_permission

router = APIRouter(prefix="/workflow", tags=["Workflow - Configuration"])

RESOURCE = "workflows"


def get_workflow_service(
    workflow_definition_repo: IWorkflowDefinitionRepository = Depends(
        get_workflow_definition_repository
    ),
    workflow_instance_repo: IWorkflowInstanceRepository = Depends(
        get_workflow_instance_repository
    ),
    approval_matrix_repo: IApprovalMatrixRepository = Depends(
        get_approval_matrix_repository
    ),
    role_assignment_repo: IRoleAssignmentRepository = Depends(
        get_role_assignment_repository
    ),
) -> WorkflowService:
    """
    FastAPI dependency — creates WorkflowService with injected repositories.

    Shared with `workflow_instance_controller`, which drives the same service, so
    this one is public rather than module-private. The role assignment repository
    is needed because a role-based approval level fans out to its holders.
    """
    return WorkflowService(
        workflow_definition_repo=workflow_definition_repo,
        workflow_instance_repo=workflow_instance_repo,
        approval_matrix_repo=approval_matrix_repo,
        role_assignment_repo=role_assignment_repo,
    )


# ─── Definitions ───


@router.get(
    "/definitions",
    response_model=WorkflowDefinitionListResponse,
    summary="List workflow definitions",
    dependencies=[Depends(require_api_permission(RESOURCE, "READ"))],
)
async def list_definitions(
    skip: int = Query(default=0, ge=0),
    limit: int = Query(default=100, ge=1, le=500),
    search: str | None = Query(default=None, description="Match code, name or entity type"),
    is_active: bool | None = Query(default=None),
    entity_type: str | None = Query(default=None),
    service: WorkflowService = Depends(get_workflow_service),
) -> WorkflowDefinitionListResponse:
    """GET /api/v1/workflow/definitions"""
    return await service.list_definitions(
        skip=skip,
        limit=limit,
        search=search,
        is_active=is_active,
        entity_type=entity_type,
    )


@router.post(
    "/definitions",
    response_model=WorkflowDefinitionResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create a workflow definition",
    dependencies=[Depends(require_api_permission(RESOURCE, "CREATE"))],
)
async def create_definition(
    request: WorkflowDefinitionCreate,
    current_user: User = Depends(get_current_active_user),
    service: WorkflowService = Depends(get_workflow_service),
) -> WorkflowDefinitionResponse:
    """POST /api/v1/workflow/definitions"""
    return await service.create_definition(request=request, actor=current_user)


@router.get(
    "/definitions/{definition_id}",
    response_model=WorkflowDefinitionDetailResponse,
    summary="Get a workflow definition with its states and transitions",
    dependencies=[Depends(require_api_permission(RESOURCE, "READ"))],
)
async def get_definition(
    definition_id: int,
    service: WorkflowService = Depends(get_workflow_service),
) -> WorkflowDefinitionDetailResponse:
    """GET /api/v1/workflow/definitions/{definition_id}"""
    return await service.get_definition_detail(definition_id)


@router.patch(
    "/definitions/{definition_id}",
    response_model=WorkflowDefinitionResponse,
    summary="Update a workflow definition",
    dependencies=[Depends(require_api_permission(RESOURCE, "UPDATE"))],
)
async def update_definition(
    definition_id: int,
    request: WorkflowDefinitionUpdate,
    current_user: User = Depends(get_current_active_user),
    service: WorkflowService = Depends(get_workflow_service),
) -> WorkflowDefinitionResponse:
    """PATCH /api/v1/workflow/definitions/{definition_id}"""
    return await service.update_definition(
        definition_id=definition_id, request=request, actor=current_user
    )


@router.delete(
    "/definitions/{definition_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete a workflow definition",
    dependencies=[Depends(require_api_permission(RESOURCE, "DELETE"))],
)
async def delete_definition(
    definition_id: int,
    service: WorkflowService = Depends(get_workflow_service),
) -> None:
    """DELETE /api/v1/workflow/definitions/{definition_id}"""
    await service.delete_definition(definition_id)


# ─── States ───


@router.get(
    "/definitions/{definition_id}/statuses",
    response_model=list[WorkflowStatusResponse],
    summary="List states of a workflow",
    dependencies=[Depends(require_api_permission(RESOURCE, "READ"))],
)
async def list_statuses(
    definition_id: int,
    service: WorkflowService = Depends(get_workflow_service),
) -> list[WorkflowStatusResponse]:
    """GET /api/v1/workflow/definitions/{definition_id}/statuses"""
    return await service.list_statuses(definition_id)


@router.post(
    "/definitions/{definition_id}/statuses",
    response_model=WorkflowStatusResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Add a state to a workflow",
    dependencies=[Depends(require_api_permission(RESOURCE, "CREATE"))],
)
async def create_status(
    definition_id: int,
    request: WorkflowStatusCreate,
    current_user: User = Depends(get_current_active_user),
    service: WorkflowService = Depends(get_workflow_service),
) -> WorkflowStatusResponse:
    """POST /api/v1/workflow/definitions/{definition_id}/statuses"""
    return await service.create_status(
        definition_id=definition_id, request=request, actor=current_user
    )


@router.patch(
    "/statuses/{status_id}",
    response_model=WorkflowStatusResponse,
    summary="Update a workflow state",
    dependencies=[Depends(require_api_permission(RESOURCE, "UPDATE"))],
)
async def update_status(
    status_id: int,
    request: WorkflowStatusUpdate,
    current_user: User = Depends(get_current_active_user),
    service: WorkflowService = Depends(get_workflow_service),
) -> WorkflowStatusResponse:
    """PATCH /api/v1/workflow/statuses/{status_id}"""
    return await service.update_status(
        status_id=status_id, request=request, actor=current_user
    )


@router.delete(
    "/statuses/{status_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete a workflow state",
    dependencies=[Depends(require_api_permission(RESOURCE, "DELETE"))],
)
async def delete_status(
    status_id: int,
    service: WorkflowService = Depends(get_workflow_service),
) -> None:
    """DELETE /api/v1/workflow/statuses/{status_id}"""
    await service.delete_status(status_id)


# ─── Transitions ───


@router.get(
    "/definitions/{definition_id}/transitions",
    response_model=list[WorkflowTransitionResponse],
    summary="List transitions of a workflow",
    dependencies=[Depends(require_api_permission(RESOURCE, "READ"))],
)
async def list_transitions(
    definition_id: int,
    service: WorkflowService = Depends(get_workflow_service),
) -> list[WorkflowTransitionResponse]:
    """GET /api/v1/workflow/definitions/{definition_id}/transitions"""
    return await service.list_transitions(definition_id)


@router.post(
    "/definitions/{definition_id}/transitions",
    response_model=WorkflowTransitionResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Add a transition to a workflow",
    dependencies=[Depends(require_api_permission(RESOURCE, "CREATE"))],
)
async def create_transition(
    definition_id: int,
    request: WorkflowTransitionCreate,
    current_user: User = Depends(get_current_active_user),
    service: WorkflowService = Depends(get_workflow_service),
) -> WorkflowTransitionResponse:
    """POST /api/v1/workflow/definitions/{definition_id}/transitions"""
    return await service.create_transition(
        definition_id=definition_id, request=request, actor=current_user
    )


@router.delete(
    "/transitions/{transition_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete a transition",
    dependencies=[Depends(require_api_permission(RESOURCE, "DELETE"))],
)
async def delete_transition(
    transition_id: int,
    service: WorkflowService = Depends(get_workflow_service),
) -> None:
    """DELETE /api/v1/workflow/transitions/{transition_id}"""
    await service.delete_transition(transition_id)
