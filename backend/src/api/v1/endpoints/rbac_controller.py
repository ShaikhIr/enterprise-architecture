"""
RBAC Management API endpoints.
Provides CRUD for roles, permissions, assignments, and audit log viewing.
All operations are audit-logged and restricted to ADMIN role.
"""

from uuid import UUID, uuid4

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from src.api.v1.dependencies import get_current_active_user
from src.api.v1.schemas.rbac_schema import (
    AuditLogListResponse,
    AuditLogResponse,
    FieldPermissionsResponse,
    MenuPermissionsResponse,
    PermissionCreate,
    PermissionGrantRequest,
    PermissionResponse,
    PermissionRevokeRequest,
    RoleAssignmentResponse,
    RoleAssignRequest,
    RoleCreate,
    RoleListResponse,
    RoleResponse,
    RoleRevokeRequest,
    RoleUpdate,
)
from src.domain.entities.audit_log import AuditAction
from src.domain.entities.role import PermissionScope
from src.domain.entities.user import User
from src.infrastructure.database.models.audit_log_model import AuditLogModel
from src.infrastructure.database.models.role_model import (
    PermissionModel,
    RoleAssignmentModel,
    RoleModel,
    RolePermissionModel,
)
from src.infrastructure.database.session import get_db_session
from src.infrastructure.security.audit_service import AuditService
from src.infrastructure.security.permission_manager import PermissionManager, require_permission, require_api_permission

router = APIRouter(prefix="/rbac", tags=["RBAC"])


def _get_client_ip(request: Request) -> str:
    """Extract client IP from request."""
    forwarded = request.headers.get("x-forwarded-for")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.client.host if request.client else ""


# â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•
# PERMISSIONS CRUD
# â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•


@router.get(
    "/permissions",
    response_model=list[PermissionResponse],
    summary="List all permissions",
    dependencies=[Depends(require_permission("rbac.read"))],
)
async def list_permissions(
    scope: str | None = Query(default=None, pattern="^(MENU|API|FIELD)$"),
    session: AsyncSession = Depends(get_db_session),
) -> list[PermissionResponse]:
    """GET /api/v1/rbac/permissions - List permissions, optionally filtered by scope."""
    stmt = select(PermissionModel).where(PermissionModel.is_active == True)  # noqa: E712
    if scope:
        stmt = stmt.where(PermissionModel.scope == scope)
    stmt = stmt.order_by(PermissionModel.scope, PermissionModel.resource)
    result = await session.execute(stmt)
    return [PermissionResponse.model_validate(p) for p in result.scalars().all()]


@router.post(
    "/permissions",
    response_model=PermissionResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create a permission ",
    dependencies=[Depends(require_permission("rbac.create"))],
)
async def create_permission(
    request_body: PermissionCreate,
    request: Request,
    current_user: User = Depends(get_current_active_user),
    session: AsyncSession = Depends(get_db_session),
) -> PermissionResponse:
    """POST /api/v1/rbac/permissions - Create a new permission definition."""
    # Check uniqueness
    existing = await session.execute(
        select(PermissionModel).where(PermissionModel.code == request_body.code)
    )
    if existing.scalar_one_or_none():
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Permission code '{request_body.code}' already exists",
        )

    perm = PermissionModel(
        id=uuid4(),
        code=request_body.code,
        name=request_body.name,
        description=request_body.description,
        scope=request_body.scope,
        resource=request_body.resource,
        action=request_body.action,
        is_active=True,
        created_by=current_user.username,
        modified_by=current_user.username,
    )
    session.add(perm)

    # Audit log
    audit = AuditService(session)
    await audit.log(
        actor_id=current_user.id,
        actor_username=current_user.username,
        action=AuditAction.PERMISSION_CREATED,
        resource_type="Permission",
        resource_id=str(perm.id),
        new_value={"code": perm.code, "scope": perm.scope, "resource": perm.resource, "action": perm.action},
        ip_address=_get_client_ip(request),
    )

    await session.commit()
    await session.refresh(perm)
    return PermissionResponse.model_validate(perm)


# â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•
# ROLES CRUD
# â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•


@router.get(
    "/roles",
    response_model=RoleListResponse,
    summary="List all roles",
    dependencies=[Depends(require_permission("rbac.read"))],
)
async def list_roles(
    tenant_id: UUID | None = Query(default=None),
    session: AsyncSession = Depends(get_db_session),
) -> RoleListResponse:
    """GET /api/v1/rbac/roles - List roles with their permissions."""
    stmt = (
        select(RoleModel)
        .options(selectinload(RoleModel.permissions))
        .where(RoleModel.is_active == True)  # noqa: E712
    )
    if tenant_id:
        stmt = stmt.where(
            (RoleModel.tenant_id == str(tenant_id)) | (RoleModel.tenant_id.is_(None))
        )
    stmt = stmt.order_by(RoleModel.code)
    result = await session.execute(stmt)
    roles = result.scalars().all()
    return RoleListResponse(
        roles=[RoleResponse.model_validate(r) for r in roles],
        total=len(roles),
    )


@router.post(
    "/roles",
    response_model=RoleResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create a role ",
    dependencies=[Depends(require_permission("rbac.create"))],
)
async def create_role(
    request_body: RoleCreate,
    request: Request,
    current_user: User = Depends(get_current_active_user),
    session: AsyncSession = Depends(get_db_session),
) -> RoleResponse:
    """POST /api/v1/rbac/roles - Create a new role."""
    existing = await session.execute(
        select(RoleModel).where(RoleModel.code == request_body.code)
    )
    if existing.scalar_one_or_none():
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Role code '{request_body.code}' already exists",
        )

    role = RoleModel(
        id=uuid4(),
        code=request_body.code,
        name=request_body.name,
        description=request_body.description,
        is_system=False,
        is_active=True,
        tenant_id=str(request_body.tenant_id) if request_body.tenant_id else None,
        parent_role_id=str(request_body.parent_role_id) if request_body.parent_role_id else None,
        created_by=current_user.username,
        modified_by=current_user.username,
    )
    session.add(role)

    audit = AuditService(session)
    await audit.log(
        actor_id=current_user.id,
        actor_username=current_user.username,
        action=AuditAction.ROLE_CREATED,
        resource_type="Role",
        resource_id=str(role.id),
        tenant_id=request_body.tenant_id,
        new_value={"code": role.code, "name": role.name},
        ip_address=_get_client_ip(request),
    )

    await session.commit()
    await session.refresh(role)
    return RoleResponse.model_validate(role)


@router.patch(
    "/roles/{role_id}",
    response_model=RoleResponse,
    summary="Update a role ",
    dependencies=[Depends(require_permission("rbac.update"))],
)
async def update_role(
    role_id: UUID,
    request_body: RoleUpdate,
    request: Request,
    current_user: User = Depends(get_current_active_user),
    session: AsyncSession = Depends(get_db_session),
) -> RoleResponse:
    """PATCH /api/v1/rbac/roles/{role_id} - Update role properties."""
    stmt = (
        select(RoleModel)
        .options(selectinload(RoleModel.permissions))
        .where(RoleModel.id == str(role_id))
    )
    result = await session.execute(stmt)
    role = result.scalar_one_or_none()

    if not role:
        raise HTTPException(status_code=404, detail="Role not found")
    if role.is_system:
        raise HTTPException(status_code=403, detail="System roles cannot be modified")

    old_value = {"name": role.name, "description": role.description, "is_active": role.is_active}

    if request_body.name is not None:
        role.name = request_body.name
    if request_body.description is not None:
        role.description = request_body.description
    if request_body.is_active is not None:
        role.is_active = request_body.is_active
    if request_body.parent_role_id is not None:
        role.parent_role_id = str(request_body.parent_role_id)

    role.modified_by = current_user.username

    audit = AuditService(session)
    await audit.log(
        actor_id=current_user.id,
        actor_username=current_user.username,
        action=AuditAction.ROLE_UPDATED,
        resource_type="Role",
        resource_id=str(role_id),
        old_value=old_value,
        new_value={"name": role.name, "description": role.description, "is_active": role.is_active},
        ip_address=_get_client_ip(request),
    )

    await session.commit()
    await session.refresh(role)
    return RoleResponse.model_validate(role)


# â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•
# PERMISSION GRANT / REVOKE ON ROLES
# â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•


@router.post(
    "/roles/grant-permission",
    status_code=status.HTTP_201_CREATED,
    summary="Grant permission to a role ",
    dependencies=[Depends(require_permission("rbac.update"))],
)
async def grant_permission_to_role(
    request_body: PermissionGrantRequest,
    request: Request,
    current_user: User = Depends(get_current_active_user),
    session: AsyncSession = Depends(get_db_session),
) -> dict:
    """POST /api/v1/rbac/roles/grant-permission - Add a permission to a role."""
    # Verify role exists
    role = await session.get(RoleModel, str(request_body.role_id))
    if not role:
        raise HTTPException(status_code=404, detail="Role not found")

    perm = await session.get(PermissionModel, str(request_body.permission_id))
    if not perm:
        raise HTTPException(status_code=404, detail="Permission not found")

    # Check if already granted
    existing = await session.execute(
        select(RolePermissionModel).where(
            RolePermissionModel.role_id == str(request_body.role_id),
            RolePermissionModel.permission_id == str(request_body.permission_id),
        )
    )
    if existing.scalar_one_or_none():
        raise HTTPException(status_code=409, detail="Permission already granted to this role")

    rp = RolePermissionModel(
        id=uuid4(),
        role_id=str(request_body.role_id),
        permission_id=str(request_body.permission_id),
        created_by=current_user.username,
        modified_by=current_user.username,
    )
    session.add(rp)

    audit = AuditService(session)
    await audit.log_permission_change(
        actor_id=current_user.id,
        actor_username=current_user.username,
        action=AuditAction.PERMISSION_GRANTED,
        role_id=request_body.role_id,
        permission_code=perm.code,
        ip_address=_get_client_ip(request),
    )

    await session.commit()
    return {"detail": f"Permission '{perm.code}' granted to role '{role.code}'"}


@router.post(
    "/roles/revoke-permission",
    summary="Revoke permission from a role ",
    dependencies=[Depends(require_permission("rbac.update"))],
)
async def revoke_permission_from_role(
    request_body: PermissionRevokeRequest,
    request: Request,
    current_user: User = Depends(get_current_active_user),
    session: AsyncSession = Depends(get_db_session),
) -> dict:
    """POST /api/v1/rbac/roles/revoke-permission - Remove a permission from a role."""
    stmt = select(RolePermissionModel).where(
        RolePermissionModel.role_id == str(request_body.role_id),
        RolePermissionModel.permission_id == str(request_body.permission_id),
    )
    result = await session.execute(stmt)
    rp = result.scalar_one_or_none()

    if not rp:
        raise HTTPException(status_code=404, detail="Permission not assigned to this role")

    # Get permission code for audit
    perm = await session.get(PermissionModel, str(request_body.permission_id))

    await session.delete(rp)

    audit = AuditService(session)
    await audit.log_permission_change(
        actor_id=current_user.id,
        actor_username=current_user.username,
        action=AuditAction.PERMISSION_REVOKED,
        role_id=request_body.role_id,
        permission_code=perm.code if perm else str(request_body.permission_id),
        ip_address=_get_client_ip(request),
    )

    await session.commit()
    return {"detail": "Permission revoked"}


# â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•
# ROLE ASSIGNMENTS (User â†” Role)
# â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•


@router.post(
    "/assignments",
    response_model=RoleAssignmentResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Assign role to user ",
    dependencies=[Depends(require_permission("rbac.update"))],
)
async def assign_role(
    request_body: RoleAssignRequest,
    request: Request,
    current_user: User = Depends(get_current_active_user),
    session: AsyncSession = Depends(get_db_session),
) -> RoleAssignmentResponse:
    """POST /api/v1/rbac/assignments - Assign a role to a user."""
    role = await session.get(RoleModel, str(request_body.role_id))
    if not role:
        raise HTTPException(status_code=404, detail="Role not found")

    # Check duplicate
    existing = await session.execute(
        select(RoleAssignmentModel).where(
            RoleAssignmentModel.user_id == str(request_body.user_id),
            RoleAssignmentModel.role_id == str(request_body.role_id),
            RoleAssignmentModel.is_active == True,  # noqa: E712
        )
    )
    if existing.scalar_one_or_none():
        raise HTTPException(status_code=409, detail="Role already assigned to this user")

    assignment = RoleAssignmentModel(
        id=uuid4(),
        user_id=str(request_body.user_id),
        role_id=str(request_body.role_id),
        tenant_id=str(request_body.tenant_id) if request_body.tenant_id else None,
        is_active=True,
        created_by=current_user.username,
        modified_by=current_user.username,
    )
    session.add(assignment)

    audit = AuditService(session)
    await audit.log_role_assigned(
        actor_id=current_user.id,
        actor_username=current_user.username,
        user_id=request_body.user_id,
        role_id=request_body.role_id,
        role_code=role.code,
        tenant_id=request_body.tenant_id,
        ip_address=_get_client_ip(request),
    )

    await session.commit()
    await session.refresh(assignment)
    return RoleAssignmentResponse.model_validate(assignment)


@router.post(
    "/assignments/revoke",
    summary="Revoke role from user ",
    dependencies=[Depends(require_permission("rbac.update"))],
)
async def revoke_role(
    request_body: RoleRevokeRequest,
    request: Request,
    current_user: User = Depends(get_current_active_user),
    session: AsyncSession = Depends(get_db_session),
) -> dict:
    """POST /api/v1/rbac/assignments/revoke - Revoke a role from a user."""
    stmt = select(RoleAssignmentModel).where(
        RoleAssignmentModel.user_id == str(request_body.user_id),
        RoleAssignmentModel.role_id == str(request_body.role_id),
        RoleAssignmentModel.is_active == True,  # noqa: E712
    )
    result = await session.execute(stmt)
    assignment = result.scalar_one_or_none()

    if not assignment:
        raise HTTPException(status_code=404, detail="Active role assignment not found")

    assignment.is_active = False
    assignment.modified_by = current_user.username

    role = await session.get(RoleModel, str(request_body.role_id))

    audit = AuditService(session)
    await audit.log_role_revoked(
        actor_id=current_user.id,
        actor_username=current_user.username,
        user_id=request_body.user_id,
        role_id=request_body.role_id,
        role_code=role.code if role else str(request_body.role_id),
        tenant_id=request_body.tenant_id,
        ip_address=_get_client_ip(request),
    )

    await session.commit()
    return {"detail": "Role revoked"}


# â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•
# USER PERMISSION QUERIES (for frontend consumption)
# â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•


@router.get(
    "/my-permissions/menu",
    response_model=MenuPermissionsResponse,
    summary="Get current user's menu permissions",
)
async def get_my_menu_permissions(
    current_user: User = Depends(get_current_active_user),
    session: AsyncSession = Depends(get_db_session),
) -> MenuPermissionsResponse:
    """GET /api/v1/rbac/my-permissions/menu - Returns menu keys the user can access."""
    manager = PermissionManager(session)
    permissions = await manager.get_user_permissions(
        current_user.id, scope=PermissionScope.MENU
    )
    menu_keys = list({p.resource for p in permissions})
    return MenuPermissionsResponse(
        menu_keys=menu_keys,
        permissions=[PermissionResponse.model_validate(p) for p in permissions],
    )


@router.get(
    "/my-permissions/all",
    summary="Get ALL permissions for the current user (debug)",
)
async def get_my_all_permissions(
    current_user: User = Depends(get_current_active_user),
    session: AsyncSession = Depends(get_db_session),
) -> dict:
    """GET /api/v1/rbac/my-permissions/all - Returns all permissions (all scopes) for debugging."""
    manager = PermissionManager(session)

    # Get role assignments for this user
    from src.infrastructure.database.models.role_model import RoleAssignmentModel as RA
    assign_result = await session.execute(
        select(RA).where(RA.user_id == str(current_user.id))
    )
    assignments = assign_result.scalars().all()

    # Get role details
    role_ids = [a.role_id for a in assignments]
    roles_info = []
    if role_ids:
        role_result = await session.execute(
            select(RoleModel).options(selectinload(RoleModel.permissions)).where(RoleModel.id.in_(role_ids))
        )
        roles = role_result.scalars().all()
        for r in roles:
            roles_info.append({
                "id": str(r.id),
                "code": r.code,
                "name": r.name,
                "is_active": r.is_active,
                "permission_count": len(r.permissions),
                "permissions": [{"code": p.code, "scope": p.scope, "resource": p.resource, "action": p.action} for p in r.permissions],
            })

    permissions = await manager.get_user_permissions(current_user.id)
    return {
        "user_id": str(current_user.id),
        "username": current_user.username,
        "legacy_role": current_user.role,
        "role_assignments": [
            {"role_id": str(a.role_id), "is_active": a.is_active, "tenant_id": str(a.tenant_id) if a.tenant_id else None}
            for a in assignments
        ],
        "assigned_roles": roles_info,
        "total_effective_permissions": len(permissions),
        "effective_permissions": [
            {
                "code": p.code,
                "scope": p.scope,
                "resource": p.resource,
                "action": p.action,
            }
            for p in permissions
        ],
    }


@router.get(
    "/my-permissions/fields/{resource}",
    response_model=FieldPermissionsResponse,
    summary="Get current user's field-level permissions for a resource",
)
async def get_my_field_permissions(
    resource: str,
    current_user: User = Depends(get_current_active_user),
    session: AsyncSession = Depends(get_db_session),
) -> FieldPermissionsResponse:
    """GET /api/v1/rbac/my-permissions/fields/{resource} - Field-level access."""
    manager = PermissionManager(session)
    field_perms = await manager.get_field_permissions(current_user.id, resource)
    return FieldPermissionsResponse(resource=resource, fields=field_perms)


# â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•
# AUDIT LOGS (read-only)
# â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•


@router.get(
    "/audit-logs",
    response_model=AuditLogListResponse,
    summary="View audit logs",
    dependencies=[Depends(require_permission("audit.read"))],
)
async def list_audit_logs(
    action: str | None = Query(default=None),
    actor_username: str | None = Query(default=None),
    resource_type: str | None = Query(default=None),
    skip: int = Query(default=0, ge=0),
    limit: int = Query(default=50, ge=1, le=200),
    session: AsyncSession = Depends(get_db_session),
) -> AuditLogListResponse:
    """GET /api/v1/rbac/audit-logs - Query audit logs with filters."""
    stmt = select(AuditLogModel)
    count_stmt = select(func.count()).select_from(AuditLogModel)

    if action:
        stmt = stmt.where(AuditLogModel.action == action)
        count_stmt = count_stmt.where(AuditLogModel.action == action)
    if actor_username:
        stmt = stmt.where(AuditLogModel.actor_username == actor_username)
        count_stmt = count_stmt.where(AuditLogModel.actor_username == actor_username)
    if resource_type:
        stmt = stmt.where(AuditLogModel.resource_type == resource_type)
        count_stmt = count_stmt.where(AuditLogModel.resource_type == resource_type)

    stmt = stmt.order_by(AuditLogModel.created_at.desc()).offset(skip).limit(limit)

    result = await session.execute(stmt)
    total_result = await session.execute(count_stmt)

    logs = result.scalars().all()
    total = total_result.scalar() or 0

    return AuditLogListResponse(
        logs=[AuditLogResponse.model_validate(log) for log in logs],
        total=total,
        skip=skip,
        limit=limit,
    )
