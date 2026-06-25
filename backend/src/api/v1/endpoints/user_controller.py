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
from src.api.v1.schemas.user_response import UserDetailResponse, UserListResponse, UserResponse
from src.domain.entities.user import User
from src.domain.repositories.user_repository import UserRepositoryInterface
from src.infrastructure.database.models.role_model import RoleAssignmentModel, RoleModel
from src.infrastructure.database.models.user_details_model import UserDetailsModel
from src.infrastructure.database.models.user_model import UserModel
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
    session: AsyncSession = Depends(get_db_session),
) -> UserListResponse:
    """GET /api/v1/users - List users with employee details and last login."""
    from src.infrastructure.database.models.audit_log_model import AuditLogModel
    from sqlalchemy import func, and_

    # Query users with LEFT JOIN to user_details
    stmt = (
        select(UserModel, UserDetailsModel)
        .outerjoin(UserDetailsModel, UserDetailsModel.user_id == UserModel.id)
        .offset(skip)
        .limit(limit)
    )
    result = await session.execute(stmt)
    rows = result.all()

    # Get last login for each user in one query
    user_ids = [str(row[0].id) for row in rows]
    last_login_map: dict[str, str] = {}
    if user_ids:
        # Subquery: max created_at per actor_id where action=LOGIN_SUCCESS
        last_login_stmt = (
            select(
                AuditLogModel.actor_id,
                func.max(AuditLogModel.created_at).label("last_login"),
            )
            .where(
                AuditLogModel.action == "LOGIN_SUCCESS",
                AuditLogModel.actor_id.in_(user_ids),
            )
            .group_by(AuditLogModel.actor_id)
        )
        ll_result = await session.execute(last_login_stmt)
        for row_ll in ll_result.all():
            last_login_map[str(row_ll[0])] = row_ll[1]

    users = []
    for user_model, details_model in rows:
        users.append(UserResponse(
            id=user_model.id,
            username=user_model.username,
            is_active=user_model.is_active,
            is_blocked=user_model.is_blocked,
            is_validate_ad=user_model.is_validate_ad,
            employee_id=details_model.employee_id if details_model else None,
            employee_name=details_model.employee_name if details_model else None,
            email=details_model.email if details_model else None,
            last_login=last_login_map.get(str(user_model.id)),
            created_by=user_model.created_by,
            created_date=user_model.created_date,
            modified_by=user_model.modified_by,
            modified_date=user_model.modified_date,
        ))

    return UserListResponse(
        users=users,
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
    session: AsyncSession = Depends(get_db_session),
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

    # Assign role if provided
    if request.role_id:
        assignment = RoleAssignmentModel(
            id=uuid4(),
            user_id=str(created.id),
            role_id=str(request.role_id),
            tenant_id=None,
            is_active=True,
            created_by=current_user.username,
            modified_by=current_user.username,
        )
        session.add(assignment)

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
    session: AsyncSession = Depends(get_db_session),
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

    # Update role assignment if provided (replace existing)
    if request.role_id is not None:
        # Deactivate existing assignments
        existing_stmt = select(RoleAssignmentModel).where(
            RoleAssignmentModel.user_id == str(user_id),
            RoleAssignmentModel.is_active == True,  # noqa: E712
        )
        existing_result = await session.execute(existing_stmt)
        for assignment in existing_result.scalars().all():
            assignment.is_active = False
            assignment.modified_by = current_user.username

        # Create new single assignment
        assignment = RoleAssignmentModel(
            id=uuid4(),
            user_id=str(user_id),
            role_id=str(request.role_id),
            tenant_id=None,
            is_active=True,
            created_by=current_user.username,
            modified_by=current_user.username,
        )
        session.add(assignment)

    return _to_response(updated)


@router.get(
    "/{user_id}/details",
    response_model=UserDetailResponse,
    summary="Get full user details (all employee AD fields)",
)
async def get_user_details(
    user_id: UUID,
    current_user: User = Depends(get_current_active_user),
    session: AsyncSession = Depends(get_db_session),
) -> UserDetailResponse:
    """GET /api/v1/users/{user_id}/details — Full user profile with all employee data."""
    stmt = (
        select(UserModel, UserDetailsModel)
        .outerjoin(UserDetailsModel, UserDetailsModel.user_id == UserModel.id)
        .where(UserModel.id == user_id)
    )
    result = await session.execute(stmt)
    row = result.one_or_none()

    if not row:
        raise HTTPException(status_code=404, detail="User not found")

    user_model, details = row

    return UserDetailResponse(
        id=user_model.id,
        username=user_model.username,
        is_active=user_model.is_active,
        is_blocked=user_model.is_blocked,
        is_validate_ad=user_model.is_validate_ad,
        employee_id=details.employee_id if details else None,
        employee_name=details.employee_name if details else None,
        first_name=details.first_name if details else None,
        middle_name=details.middle_name if details else None,
        last_name=details.last_name if details else None,
        email=details.email if details else None,
        designation_title=details.designation_title if details else None,
        department=details.department if details else None,
        business_unit=details.business_unit if details else None,
        group_company=details.group_company if details else None,
        location=details.location if details else None,
        region=details.region if details else None,
        zone=details.zone if details else None,
        grade=details.grade if details else None,
        office_mobile_no=details.office_mobile_no if details else None,
        personal_mobile_no=details.personal_mobile_no if details else None,
        date_of_joining=details.date_of_joining if details else None,
        reporting_manager=details.reporting_manager if details else None,
        direct_manager_employee_id=details.direct_manager_employee_id if details else None,
        direct_manager_name=details.direct_manager_name if details else None,
        direct_manager_email=details.direct_manager_email if details else None,
        sap_user_id=details.sap_user_id if details else None,
        division_id=details.division_id if details else None,
        territory_id=details.territory_id if details else None,
        created_by=user_model.created_by,
        created_date=user_model.created_date,
        modified_by=user_model.modified_by,
        modified_date=user_model.modified_date,
    )


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


@router.get(
    "/{user_id}/login-history",
    summary="Get login/logout history for a user",
)
async def get_user_login_history(
    user_id: UUID,
    limit: int = Query(default=20, ge=1, le=100),
    current_user: User = Depends(get_current_active_user),
    session: AsyncSession = Depends(get_db_session),
) -> list[dict]:
    """GET /api/v1/users/{user_id}/login-history — Login/logout audit trail."""
    from src.infrastructure.database.models.audit_log_model import AuditLogModel

    stmt = (
        select(AuditLogModel)
        .where(
            AuditLogModel.resource_type == "Authentication",
            AuditLogModel.resource_id == str(user_id),
        )
        .order_by(AuditLogModel.created_at.desc())
        .limit(limit)
    )
    # Also try matching by actor_id
    stmt2 = (
        select(AuditLogModel)
        .where(
            AuditLogModel.resource_type == "Authentication",
            AuditLogModel.actor_id == str(user_id),
        )
        .order_by(AuditLogModel.created_at.desc())
        .limit(limit)
    )

    result = await session.execute(stmt2)
    entries = result.scalars().all()

    # If no results by actor_id, try by username from resource_id
    if not entries:
        # Get the username
        user_model = await session.get(UserModel, str(user_id))
        if user_model:
            stmt3 = (
                select(AuditLogModel)
                .where(
                    AuditLogModel.resource_type == "Authentication",
                    AuditLogModel.actor_username == user_model.username,
                )
                .order_by(AuditLogModel.created_at.desc())
                .limit(limit)
            )
            result = await session.execute(stmt3)
            entries = result.scalars().all()

    return [
        {
            "action": e.action,
            "ip_address": e.ip_address,
            "user_agent": e.user_agent,
            "created_at": e.created_at.isoformat() if e.created_at else None,
        }
        for e in entries
    ]


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
