"""
Approval matrix API endpoints.

Thin controller — all business logic sits in ApprovalMatrixService.
"""


from fastapi import APIRouter, Depends, Query, status

from src.api.v1.dependencies import (
    get_approval_matrix_repository,
    get_current_active_user,
)
from src.api.v1.schemas.approval_matrix_schema import (
    ApprovalMatrixCreate,
    ApprovalMatrixListResponse,
    ApprovalMatrixResponse,
    ApprovalMatrixUpdate,
    ApprovalResolveRequest,
    ApprovalResolveResponse,
)
from src.application.services.approval_matrix_service import ApprovalMatrixService
from src.domain.entities.user import User
from src.domain.repositories.approval_matrix_repository import IApprovalMatrixRepository
from src.infrastructure.security.permission_manager import require_api_permission

router = APIRouter(
    prefix="/workflow/approval-matrices", tags=["Workflow - Approval Matrix"]
)

RESOURCE = "approval_matrices"


def _get_approval_matrix_service(
    approval_matrix_repo: IApprovalMatrixRepository = Depends(
        get_approval_matrix_repository
    ),
) -> ApprovalMatrixService:
    """FastAPI dependency — creates ApprovalMatrixService with injected repository."""
    return ApprovalMatrixService(approval_matrix_repo=approval_matrix_repo)


@router.get(
    "",
    response_model=ApprovalMatrixListResponse,
    summary="List approval matrices",
    dependencies=[Depends(require_api_permission(RESOURCE, "READ"))],
)
async def list_matrices(
    skip: int = Query(default=0, ge=0),
    limit: int = Query(default=100, ge=1, le=500),
    search: str | None = Query(default=None, description="Match code, name or entity type"),
    is_active: bool | None = Query(default=None),
    entity_type: str | None = Query(default=None),
    service: ApprovalMatrixService = Depends(_get_approval_matrix_service),
) -> ApprovalMatrixListResponse:
    """GET /api/v1/workflow/approval-matrices"""
    return await service.list_matrices(
        skip=skip,
        limit=limit,
        search=search,
        is_active=is_active,
        entity_type=entity_type,
    )


@router.post(
    "",
    response_model=ApprovalMatrixResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create an approval matrix",
    dependencies=[Depends(require_api_permission(RESOURCE, "CREATE"))],
)
async def create_matrix(
    request: ApprovalMatrixCreate,
    current_user: User = Depends(get_current_active_user),
    service: ApprovalMatrixService = Depends(_get_approval_matrix_service),
) -> ApprovalMatrixResponse:
    """POST /api/v1/workflow/approval-matrices"""
    return await service.create_matrix(request=request, actor=current_user)


@router.post(
    "/resolve",
    response_model=ApprovalResolveResponse,
    summary="Preview which matrix would route a sample record",
    dependencies=[Depends(require_api_permission(RESOURCE, "READ"))],
)
async def resolve_matrix(
    request: ApprovalResolveRequest,
    service: ApprovalMatrixService = Depends(_get_approval_matrix_service),
) -> ApprovalResolveResponse:
    """
    POST /api/v1/workflow/approval-matrices/resolve

    Read-only dry run. Declared before the `/{matrix_id}` routes so "resolve" is
    never parsed as a matrix id.
    """
    return await service.resolve(
        entity_type=request.entity_type, entity_data=request.entity_data
    )


@router.get(
    "/{matrix_id}",
    response_model=ApprovalMatrixResponse,
    summary="Get an approval matrix",
    dependencies=[Depends(require_api_permission(RESOURCE, "READ"))],
)
async def get_matrix(
    matrix_id: int,
    service: ApprovalMatrixService = Depends(_get_approval_matrix_service),
) -> ApprovalMatrixResponse:
    """GET /api/v1/workflow/approval-matrices/{matrix_id}"""
    return await service.get_matrix(matrix_id)


@router.patch(
    "/{matrix_id}",
    response_model=ApprovalMatrixResponse,
    summary="Update an approval matrix",
    dependencies=[Depends(require_api_permission(RESOURCE, "UPDATE"))],
)
async def update_matrix(
    matrix_id: int,
    request: ApprovalMatrixUpdate,
    current_user: User = Depends(get_current_active_user),
    service: ApprovalMatrixService = Depends(_get_approval_matrix_service),
) -> ApprovalMatrixResponse:
    """PATCH /api/v1/workflow/approval-matrices/{matrix_id}"""
    return await service.update_matrix(
        matrix_id=matrix_id, request=request, actor=current_user
    )


@router.delete(
    "/{matrix_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete an approval matrix",
    dependencies=[Depends(require_api_permission(RESOURCE, "DELETE"))],
)
async def delete_matrix(
    matrix_id: int,
    service: ApprovalMatrixService = Depends(_get_approval_matrix_service),
) -> None:
    """DELETE /api/v1/workflow/approval-matrices/{matrix_id}"""
    await service.delete_matrix(matrix_id)
