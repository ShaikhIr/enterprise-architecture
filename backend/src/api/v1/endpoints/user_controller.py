"""
User management API endpoints.
Thin controller — delegates all business logic to UserService.
"""

from typing import NoReturn
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from src.api.v1.dependencies import get_current_active_user, get_user_repository
from src.api.v1.schemas.user_request import (
    CreateUserRequest,
    EditUserRequest,
    HrImportRow,
)
from src.api.v1.schemas.user_response import (
    ImportSummary,
    UserDetailResponse,
    UserListResponse,
    UserResponse,
)
from src.application.exceptions.application_exceptions import (
    MasterConflictError,
    MasterError,
    MasterNotFoundError,
    MasterValidationError,
)
from src.application.services.user_service import UserService
from src.domain.entities.user import User
from src.domain.repositories.user_repository import IUserRepository
from src.infrastructure.database.session import get_db_session
from src.infrastructure.security.permission_manager import require_api_permission

router = APIRouter(prefix="/users", tags=["Users"])

# Map the master application exceptions to their HTTP status codes
# (MasterValidationError -> 422, MasterConflictError -> 409, MasterNotFoundError -> 404).
_MASTER_ERROR_STATUS: dict[type[MasterError], int] = {
    MasterValidationError: status.HTTP_422_UNPROCESSABLE_ENTITY,
    MasterConflictError: status.HTTP_409_CONFLICT,
    MasterNotFoundError: status.HTTP_404_NOT_FOUND,
}


def _raise_master_error(exc: MasterError) -> NoReturn:
    """Translate a master application exception into an HTTPException.

    Emits the stable error shape ``{"detail", "code", "field"?}`` so clients get
    a machine-readable field reference for validation failures.
    """
    status_code = _MASTER_ERROR_STATUS.get(type(exc), status.HTTP_400_BAD_REQUEST)
    detail: dict[str, object] = {"detail": str(exc), "code": type(exc).__name__}
    if isinstance(exc, MasterValidationError):
        detail["field"] = exc.field
    raise HTTPException(status_code=status_code, detail=detail)


def _get_user_service(
    session: AsyncSession = Depends(get_db_session),
    user_repo: IUserRepository = Depends(get_user_repository),
) -> UserService:
    """FastAPI dependency — creates UserService with injected dependencies."""
    return UserService(session=session, user_repo=user_repo)


@router.get(
    "",
    response_model=UserListResponse,
    summary="List all users",
    dependencies=[Depends(require_api_permission("users", "READ"))],
)
async def list_users(
    skip: int = Query(default=0, ge=0),
    limit: int = Query(default=100, ge=1, le=500),
    service: UserService = Depends(_get_user_service),
) -> UserListResponse:
    """GET /api/v1/users"""
    return await service.list_users(skip=skip, limit=limit)


@router.post(
    "",
    response_model=UserResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create a new user",
    dependencies=[Depends(require_api_permission("users", "CREATE"))],
)
async def create_user(
    request: CreateUserRequest,
    current_user: User = Depends(get_current_active_user),
    service: UserService = Depends(_get_user_service),
) -> UserResponse:
    """POST /api/v1/users — Create User page (Requirement 4)."""
    try:
        return await service.create_user(request=request, actor=current_user)
    except MasterError as e:
        _raise_master_error(e)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(e))


@router.get(
    "/{user_id}",
    response_model=UserResponse,
    summary="Get user by ID",
)
async def get_user(
    user_id: UUID,
    current_user: User = Depends(get_current_active_user),
    service: UserService = Depends(_get_user_service),
) -> UserResponse:
    """GET /api/v1/users/{user_id}"""
    try:
        user = await service.get_user(user_id)
        return UserService._to_response(user)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))


@router.patch(
    "/{user_id}",
    response_model=UserResponse,
    summary="Edit user",
    dependencies=[Depends(require_api_permission("users", "UPDATE"))],
)
async def update_user(
    user_id: UUID,
    request: EditUserRequest,
    current_user: User = Depends(get_current_active_user),
    service: UserService = Depends(_get_user_service),
) -> UserResponse:
    """PATCH /api/v1/users/{user_id} — Edit User page (Requirement 5)."""
    try:
        return await service.update_user(
            user_id=user_id, request=request, actor=current_user
        )
    except MasterError as e:
        _raise_master_error(e)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))


@router.post(
    "/import",
    response_model=ImportSummary,
    summary="Import/upsert users from the HR system",
    dependencies=[Depends(require_api_permission("users", "CREATE"))],
)
async def import_users(
    rows: list[HrImportRow],
    current_user: User = Depends(get_current_active_user),
    service: UserService = Depends(_get_user_service),
) -> ImportSummary:
    """POST /api/v1/users/import — HR import (Requirement 3).

    Each row is processed independently: resolvable rows are created/updated and
    unresolvable rows are reported in ``errors`` while the batch continues, so a
    single bad row never aborts the whole import.
    """
    try:
        return await service.import_users(rows=rows, actor=current_user)
    except MasterError as e:
        _raise_master_error(e)


@router.get(
    "/{user_id}/details",
    response_model=UserDetailResponse,
    summary="Get full user details (all employee AD fields)",
)
async def get_user_details(
    user_id: UUID,
    current_user: User = Depends(get_current_active_user),
    service: UserService = Depends(_get_user_service),
) -> UserDetailResponse:
    """GET /api/v1/users/{user_id}/details"""
    try:
        return await service.get_user_details(user_id)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))


@router.get(
    "/{user_id}/roles",
    summary="Get roles assigned to a user",
)
async def get_user_roles(
    user_id: UUID,
    current_user: User = Depends(get_current_active_user),
    service: UserService = Depends(_get_user_service),
) -> dict:
    """GET /api/v1/users/{user_id}/roles"""
    return await service.get_user_roles(user_id)


@router.get(
    "/{user_id}/login-history",
    summary="Get login/logout history for a user",
)
async def get_user_login_history(
    user_id: UUID,
    limit: int = Query(default=20, ge=1, le=100),
    current_user: User = Depends(get_current_active_user),
    service: UserService = Depends(_get_user_service),
) -> list[dict]:
    """GET /api/v1/users/{user_id}/login-history"""
    return await service.get_login_history(user_id=user_id, limit=limit)
