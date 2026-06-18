"""
User management API endpoints.
Protected by authentication and RBAC via FastAPI dependencies.
"""

from uuid import UUID, uuid4

from fastapi import APIRouter, Depends, HTTPException, Query, status

from src.api.v1.dependencies import (
    get_current_active_user,
    get_user_repository,
)
from src.api.v1.schemas.user_request import CreateUserRequest, UpdateUserRequest
from src.api.v1.schemas.user_response import UserListResponse, UserResponse
from src.domain.entities.user import User
from src.domain.repositories.user_repository import UserRepositoryInterface
from src.infrastructure.security.password_encoder import hash_password
from src.infrastructure.security.rbac_manager import require_role

router = APIRouter(prefix="/users", tags=["Users"])


@router.get(
    "",
    response_model=UserListResponse,
    summary="List all users (ADMIN only)",
    dependencies=[Depends(require_role("ADMIN"))],
)
async def list_users(
    skip: int = Query(default=0, ge=0),
    limit: int = Query(default=100, ge=1, le=500),
    user_repo: UserRepositoryInterface = Depends(get_user_repository),
) -> UserListResponse:
    """GET /api/v1/users - List users with pagination."""
    users = await user_repo.list_all(skip=skip, limit=limit)
    return UserListResponse(
        users=[_to_response(u) for u in users],
        total=len(users),
        skip=skip,
        limit=limit,
    )


@router.post(
    "",
    response_model=UserResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create a new user (ADMIN only)",
    dependencies=[Depends(require_role("ADMIN"))],
)
async def create_user(
    request: CreateUserRequest,
    current_user: User = Depends(get_current_active_user),
    user_repo: UserRepositoryInterface = Depends(get_user_repository),
) -> UserResponse:
    """POST /api/v1/users - Create a new user."""
    if await user_repo.exists_by_username(request.username):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Username '{request.username}' already exists",
        )

    user = User(
        id=uuid4(),
        username=request.username,
        password_hash=hash_password(request.password),
        role=request.role,
        is_validate_ad=request.is_validate_ad,
        created_by=current_user.username,
        modified_by=current_user.username,
    )

    created = await user_repo.create(user)
    return _to_response(created)


@router.get(
    "/{user_id}",
    response_model=UserResponse,
    summary="Get user by ID",
)
async def get_user(
    user_id: UUID,
    current_user: User = Depends(get_current_active_user),
    user_repo: UserRepositoryInterface = Depends(get_user_repository),
) -> UserResponse:
    """GET /api/v1/users/{user_id} - Get a specific user."""
    user = await user_repo.get_by_id(user_id)
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found",
        )
    return _to_response(user)


@router.patch(
    "/{user_id}",
    response_model=UserResponse,
    summary="Update user (ADMIN only)",
    dependencies=[Depends(require_role("ADMIN"))],
)
async def update_user(
    user_id: UUID,
    request: UpdateUserRequest,
    current_user: User = Depends(get_current_active_user),
    user_repo: UserRepositoryInterface = Depends(get_user_repository),
) -> UserResponse:
    """PATCH /api/v1/users/{user_id} - Update user properties."""
    user = await user_repo.get_by_id(user_id)
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found",
        )

    if request.is_active is not None:
        user.is_active = request.is_active
    if request.is_blocked is not None:
        user.is_blocked = request.is_blocked
    if request.is_validate_ad is not None:
        user.is_validate_ad = request.is_validate_ad
    if request.role is not None:
        user.role = request.role

    user.mark_modified(current_user.username)
    updated = await user_repo.update(user)
    return _to_response(updated)


def _to_response(user: User) -> UserResponse:
    """Map domain entity to response schema (excludes password_hash)."""
    return UserResponse(
        id=user.id,
        username=user.username,
        is_active=user.is_active,
        is_blocked=user.is_blocked,
        is_validate_ad=user.is_validate_ad,
        role=user.role,
        created_by=user.created_by,
        created_date=user.created_date,
        modified_by=user.modified_by,
        modified_date=user.modified_date,
    )
