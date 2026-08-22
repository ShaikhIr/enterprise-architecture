"""
Workflow runtime API endpoints.

Separate from `workflow_controller` because designing a workflow and acting on one
are different privileges: an approver needs `workflow_instances.UPDATE` but has no
business editing the state machine.

Thin controller — all business logic sits in WorkflowService.
"""

from uuid import UUID

from fastapi import APIRouter, Depends, Query, Request, status

from src.api.v1.dependencies import get_current_active_user
from src.api.v1.endpoints.workflow_controller import get_workflow_service
from src.api.v1.schemas.approval_matrix_schema import ApprovalTaskResponse
from src.api.v1.schemas.workflow_schema import (
    WorkflowActionRequest,
    WorkflowAvailableActionResponse,
    WorkflowHistoryResponse,
    WorkflowInstanceListResponse,
    WorkflowInstanceResponse,
    WorkflowStartRequest,
)
from src.application.services.workflow_service import WorkflowService
from src.domain.entities.user import User
from src.infrastructure.security.permission_manager import require_api_permission

router = APIRouter(prefix="/workflow", tags=["Workflow - Runtime"])

RESOURCE = "workflow_instances"


def _client_ip(request: Request) -> str:
    """
    Best-effort caller IP for the audit trail.

    Prefers the left-most `X-Forwarded-For` hop because the app runs behind a
    reverse proxy, where `request.client` is the proxy itself.
    """
    forwarded = request.headers.get("x-forwarded-for", "")
    if forwarded:
        return forwarded.split(",")[0].strip()[:45]
    return request.client.host[:45] if request.client else ""


@router.get(
    "/instances",
    response_model=WorkflowInstanceListResponse,
    summary="List workflow instances",
    dependencies=[Depends(require_api_permission(RESOURCE, "READ"))],
)
async def list_instances(
    skip: int = Query(default=0, ge=0),
    limit: int = Query(default=100, ge=1, le=500),
    entity_type: str | None = Query(default=None),
    entity_id: UUID | None = Query(default=None),
    definition_id: UUID | None = Query(default=None),
    status_id: UUID | None = Query(default=None),
    is_completed: bool | None = Query(default=None),
    service: WorkflowService = Depends(get_workflow_service),
) -> WorkflowInstanceListResponse:
    """GET /api/v1/workflow/instances"""
    return await service.list_instances(
        skip=skip,
        limit=limit,
        entity_type=entity_type,
        entity_id=entity_id,
        definition_id=definition_id,
        status_id=status_id,
        is_completed=is_completed,
    )


@router.post(
    "/instances",
    response_model=WorkflowInstanceResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Start a workflow instance",
    dependencies=[Depends(require_api_permission(RESOURCE, "CREATE"))],
)
async def start_workflow(
    request: WorkflowStartRequest,
    current_user: User = Depends(get_current_active_user),
    service: WorkflowService = Depends(get_workflow_service),
) -> WorkflowInstanceResponse:
    """POST /api/v1/workflow/instances"""
    return await service.start_workflow(request=request, actor=current_user)


@router.get(
    "/instances/{instance_id}",
    response_model=WorkflowInstanceResponse,
    summary="Get a workflow instance",
    dependencies=[Depends(require_api_permission(RESOURCE, "READ"))],
)
async def get_instance(
    instance_id: UUID,
    service: WorkflowService = Depends(get_workflow_service),
) -> WorkflowInstanceResponse:
    """GET /api/v1/workflow/instances/{instance_id}"""
    return await service.get_instance(instance_id)


@router.post(
    "/instances/{instance_id}/actions",
    response_model=WorkflowInstanceResponse,
    summary="Execute an action on a workflow instance",
    dependencies=[Depends(require_api_permission(RESOURCE, "UPDATE"))],
)
async def execute_action(
    instance_id: UUID,
    request: WorkflowActionRequest,
    http_request: Request,
    current_user: User = Depends(get_current_active_user),
    service: WorkflowService = Depends(get_workflow_service),
) -> WorkflowInstanceResponse:
    """POST /api/v1/workflow/instances/{instance_id}/actions"""
    return await service.execute_action(
        instance_id=instance_id,
        request=request,
        actor=current_user,
        ip_address=_client_ip(http_request),
    )


@router.get(
    "/instances/{instance_id}/actions",
    response_model=list[WorkflowAvailableActionResponse],
    summary="List actions available from the instance's current state",
    dependencies=[Depends(require_api_permission(RESOURCE, "READ"))],
)
async def list_available_actions(
    instance_id: UUID,
    service: WorkflowService = Depends(get_workflow_service),
) -> list[WorkflowAvailableActionResponse]:
    """GET /api/v1/workflow/instances/{instance_id}/actions"""
    return await service.available_actions(instance_id)


@router.get(
    "/instances/{instance_id}/history",
    response_model=list[WorkflowHistoryResponse],
    summary="Get the audit trail of a workflow instance",
    dependencies=[Depends(require_api_permission(RESOURCE, "READ"))],
)
async def get_instance_history(
    instance_id: UUID,
    service: WorkflowService = Depends(get_workflow_service),
) -> list[WorkflowHistoryResponse]:
    """GET /api/v1/workflow/instances/{instance_id}/history"""
    return await service.instance_history(instance_id)


@router.get(
    "/instances/{instance_id}/tasks",
    response_model=list[ApprovalTaskResponse],
    summary="Get the approval chain of a workflow instance",
    dependencies=[Depends(require_api_permission(RESOURCE, "READ"))],
)
async def get_instance_tasks(
    instance_id: UUID,
    service: WorkflowService = Depends(get_workflow_service),
) -> list[ApprovalTaskResponse]:
    """GET /api/v1/workflow/instances/{instance_id}/tasks"""
    return await service.instance_tasks(instance_id)


@router.get(
    "/my-tasks",
    response_model=list[ApprovalTaskResponse],
    summary="List the current user's pending approval tasks",
    dependencies=[Depends(require_api_permission(RESOURCE, "READ"))],
)
async def get_my_tasks(
    current_user: User = Depends(get_current_active_user),
    service: WorkflowService = Depends(get_workflow_service),
) -> list[ApprovalTaskResponse]:
    """
    GET /api/v1/workflow/my-tasks

    Carries the same READ permission as the rest of the runtime endpoints. The
    result is already scoped to the caller, so the check adds no filtering — it is
    there so that every route is uniformly authorised and none can be reached on
    authentication alone.
    """
    return await service.my_tasks(current_user.id)
