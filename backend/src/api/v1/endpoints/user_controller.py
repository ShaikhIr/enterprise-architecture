"""
User management API endpoints.
Protected by authentication and RBAC via FastAPI dependencies.
"""

from uuid import UUID, uuid4

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from src.api.v1.dependencies import (
    get_current_active_user,
    get_user_repository,
)
from src.api.v1.schemas.user_request import CreateUserRequest, UpdateUserRequest
from src.api.v1.schemas.user_response import UserListResponse, UserResponse
from src.domain.entities.user import User
from src.domain.repositories.user_repository import UserRepositoryInterface
from src.infrastructure.database.models.role_model import RoleAssignmentModel, RoleModel
from src.infrastructure.database.session import get_db_session
from src.infrastructure.security.password_encoder import hash_password
from src.infrastructure.security.permission_manager import require_api_permission

router = APIRouter(prefix="/users", tags=["Users"])


@router.get(
    "",
    response_model=UserListResponse,
    summary="List all users",
    dependencies=[Depends(require_api_permission("users", "READ"))],
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
    summary="Create a new user",
    dependencies=[Depends(require_api_permission("users", "CREATE"))],
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
    summary="Update user",
    dependencies=[Depends(require_api_permission("users", "UPDATE"))],
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

    user.mark_modified(current_user.username)
    updated = await user_repo.update(user)
    return _to_response(updated)


@router.get(
    "/{user_id}/roles",
    summary="Get roles assigned to a user",
)
async def get_user_roles(
    user_id: UUID,
    current_user: User = Depends(get_current_active_user),
    session: AsyncSession = Depends(get_db_session),
) -> dict:
    """GET /api/v1/users/{user_id}/roles - Returns all roles and their permissions for a user."""
    # Get active role assignments
    stmt = (
        select(RoleAssignmentModel)
        .where(
            RoleAssignmentModel.user_id == str(user_id),
            RoleAssignmentModel.is_active == True,  # noqa: E712
        )
    )
    result = await session.execute(stmt)
    assignments = result.scalars().all()

    if not assignments:
        return {"user_id": str(user_id), "roles": []}

    role_ids = [a.role_id for a in assignments]

    # Fetch roles with permissions
    role_stmt = (
        select(RoleModel)
        .options(selectinload(RoleModel.permissions))
        .where(RoleModel.id.in_(role_ids), RoleModel.is_active == True)  # noqa: E712
    )
    role_result = await session.execute(role_stmt)
    roles = role_result.scalars().all()

    roles_data = []
    for role in roles:
        roles_data.append({
            "id": str(role.id),
            "code": role.code,
            "name": role.name,
            "permissions": [
                {
                    "code": p.code,
                    "name": p.name,
                    "scope": p.scope,
                    "resource": p.resource,
                    "action": p.action,
                }
                for p in role.permissions
                if p.is_active
            ],
        })

    return {"user_id": str(user_id), "roles": roles_data}


def _to_response(user: User) -> UserResponse:
    """Map domain entity to response schema (excludes password_hash)."""
    return UserResponse(
        id=user.id,
        username=user.username,
        is_active=user.is_active,
        is_blocked=user.is_blocked,
        is_validate_ad=user.is_validate_ad,
        created_by=user.created_by,
        created_date=user.created_date,
        modified_by=user.modified_by,
        modified_date=user.modified_date,
    )
