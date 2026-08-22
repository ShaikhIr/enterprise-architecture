"""
Task Type master API endpoints.
Thin controller — delegates all business logic to TaskTypeService.
"""

from uuid import UUID

from fastapi import APIRouter, Depends, Query, status

from src.api.v1.dependencies import get_current_active_user, get_task_type_repository
from src.api.v1.schemas.task_type_schema import (
    TaskTypeCreate,
    TaskTypeListResponse,
    TaskTypeResponse,
    TaskTypeUpdate,
)
from src.application.services.task_type_service import TaskTypeService
from src.domain.entities.user import User
from src.domain.repositories.task_type_repository import ITaskTypeRepository
from src.infrastructure.security.permission_manager import require_api_permission

router = APIRouter(prefix="/masters/task-types", tags=["Masters - Task Types"])

RESOURCE = "task_types"


def _get_task_type_service(
    task_type_repo: ITaskTypeRepository = Depends(get_task_type_repository),
) -> TaskTypeService:
    """FastAPI dependency — creates TaskTypeService with injected dependencies."""
    return TaskTypeService(task_type_repo=task_type_repo)


@router.get(
    "",
    response_model=TaskTypeListResponse,
    summary="List task types",
    dependencies=[Depends(require_api_permission(RESOURCE, "READ"))],
)
async def list_task_types(
    skip: int = Query(default=0, ge=0),
    limit: int = Query(default=100, ge=1, le=500),
    search: str | None = Query(default=None, description="Match code or name"),
    is_active: bool | None = Query(default=None),
    service: TaskTypeService = Depends(_get_task_type_service),
) -> TaskTypeListResponse:
    """GET /api/v1/masters/task-types"""
    return await service.list_task_types(
        skip=skip, limit=limit, search=search, is_active=is_active
    )


@router.post(
    "",
    response_model=TaskTypeResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create a task type",
    dependencies=[Depends(require_api_permission(RESOURCE, "CREATE"))],
)
async def create_task_type(
    request: TaskTypeCreate,
    current_user: User = Depends(get_current_active_user),
    service: TaskTypeService = Depends(_get_task_type_service),
) -> TaskTypeResponse:
    """POST /api/v1/masters/task-types"""
    return await service.create_task_type(request=request, actor=current_user)


@router.get(
    "/{task_type_id}",
    response_model=TaskTypeResponse,
    summary="Get task type by ID",
    dependencies=[Depends(require_api_permission(RESOURCE, "READ"))],
)
async def get_task_type(
    task_type_id: UUID,
    service: TaskTypeService = Depends(_get_task_type_service),
) -> TaskTypeResponse:
    """GET /api/v1/masters/task-types/{task_type_id}"""
    return await service.get_task_type(task_type_id)


@router.patch(
    "/{task_type_id}",
    response_model=TaskTypeResponse,
    summary="Update a task type",
    dependencies=[Depends(require_api_permission(RESOURCE, "UPDATE"))],
)
async def update_task_type(
    task_type_id: UUID,
    request: TaskTypeUpdate,
    current_user: User = Depends(get_current_active_user),
    service: TaskTypeService = Depends(_get_task_type_service),
) -> TaskTypeResponse:
    """PATCH /api/v1/masters/task-types/{task_type_id}"""
    return await service.update_task_type(
        task_type_id=task_type_id, request=request, actor=current_user
    )


@router.delete(
    "/{task_type_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete a task type",
    dependencies=[Depends(require_api_permission(RESOURCE, "DELETE"))],
)
async def delete_task_type(
    task_type_id: UUID,
    service: TaskTypeService = Depends(_get_task_type_service),
) -> None:
    """DELETE /api/v1/masters/task-types/{task_type_id}"""
    await service.delete_task_type(task_type_id)
