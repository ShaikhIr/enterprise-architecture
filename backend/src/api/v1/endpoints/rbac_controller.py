"""
RBAC Management API endpoints.
Thin controller — delegates all business logic to RbacService.
"""

from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status

from src.api.v1.dependencies import (
    get_audit_log_repository,
    get_current_active_user,
    get_permission_repository,
    get_permission_resolver,
    get_role_assignment_repository,
    get_role_repository,
)
from src.api.v1.schemas.rbac_schema import (
    ApiPermissionsResponse,
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
from src.application.services.rbac_service import RbacService
from src.domain.entities.user import User
from src.domain.repositories.audit_log_repository import IAuditLogRepository
from src.domain.repositories.permission_repository import IPermissionRepository
from src.domain.repositories.role_assignment_repository import IRoleAssignmentRepository
from src.domain.repositories.role_repository import IRoleRepository
from src.domain.services.permission_resolver import IPermissionResolver
from src.infrastructure.security.permission_manager import require_permission

router = APIRouter(prefix="/rbac", tags=["RBAC"])


def _get_client_ip(request: Request) -> str:
    """Extract client IP from request."""
    forwarded = request.headers.get("x-forwarded-for")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.client.host if request.client else ""


def _get_rbac_service(
    permission_repo: IPermissionRepository = Depends(get_permission_repository),
    role_repo: IRoleRepository = Depends(get_role_repository),
    assignment_repo: IRoleAssignmentRepository = Depends(get_role_assignment_repository),
    audit_repo: IAuditLogRepository = Depends(get_audit_log_repository),
    permission_resolver: IPermissionResolver = Depends(get_permission_resolver),
) -> RbacService:
    """FastAPI dependency — builds RbacService from repository ports."""
    return RbacService(
        permission_repo=permission_repo,
        role_repo=role_repo,
        assignment_repo=assignment_repo,
        audit_repo=audit_repo,
        permission_resolver=permission_resolver,
    )


# ═══════════════════════════════════════════════════════════════════
# PERMISSIONS CRUD
# ═══════════════════════════════════════════════════════════════════


@router.get(
    "/permissions",
    response_model=list[PermissionResponse],
    summary="List all permissions",
    dependencies=[Depends(require_permission("rbac.read"))],
)
async def list_permissions(
    scope: str | None = Query(default=None, pattern="^(MENU|API|FIELD)$"),
    service: RbacService = Depends(_get_rbac_service),
) -> list[PermissionResponse]:
    perms = await service.list_permissions(scope=scope)
    return [PermissionResponse.model_validate(p) for p in perms]


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
    service: RbacService = Depends(_get_rbac_service),
) -> PermissionResponse:
    try:
        perm = await service.create_permission(
            code=request_body.code,
            name=request_body.name,
            description=request_body.description,
            scope=request_body.scope,
            resource=request_body.resource,
            action=request_body.action,
            actor_id=current_user.id,
            actor_username=current_user.username,
            ip_address=_get_client_ip(request),
        )
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(e)) from e
    return PermissionResponse.model_validate(perm)


# ═══════════════════════════════════════════════════════════════════
# ROLES CRUD
# ═══════════════════════════════════════════════════════════════════


@router.get(
    "/roles",
    response_model=RoleListResponse,
    summary="List all roles",
    dependencies=[Depends(require_permission("rbac.read"))],
)
async def list_roles(
    tenant_id: int | None = Query(default=None),
    service: RbacService = Depends(_get_rbac_service),
) -> RoleListResponse:
    data = await service.list_roles(tenant_id=tenant_id)
    return RoleListResponse(
        roles=[RoleResponse.model_validate(r) for r in data["roles"]],
        total=data["total"],
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
    service: RbacService = Depends(_get_rbac_service),
) -> RoleResponse:
    try:
        role = await service.create_role(
            code=request_body.code,
            name=request_body.name,
            description=request_body.description,
            tenant_id=request_body.tenant_id,
            parent_role_id=request_body.parent_role_id,
            actor_id=current_user.id,
            actor_username=current_user.username,
            ip_address=_get_client_ip(request),
        )
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(e)) from e
    return RoleResponse.model_validate(role)


@router.patch(
    "/roles/{role_id}",
    response_model=RoleResponse,
    summary="Update a role ",
    dependencies=[Depends(require_permission("rbac.update"))],
)
async def update_role(
    role_id: int,
    request_body: RoleUpdate,
    request: Request,
    current_user: User = Depends(get_current_active_user),
    service: RbacService = Depends(_get_rbac_service),
) -> RoleResponse:
    try:
        role = await service.update_role(
            role_id=role_id,
            name=request_body.name,
            description=request_body.description,
            is_active=request_body.is_active,
            parent_role_id=request_body.parent_role_id,
            actor_id=current_user.id,
            actor_username=current_user.username,
            ip_address=_get_client_ip(request),
        )
    except ValueError as e:
        msg = str(e)
        if "not found" in msg:
            raise HTTPException(status_code=404, detail=msg) from e
        if "cannot be modified" in msg:
            raise HTTPException(status_code=403, detail=msg) from e
        raise HTTPException(status_code=400, detail=msg) from e
    return RoleResponse.model_validate(role)


# ═══════════════════════════════════════════════════════════════════
# PERMISSION GRANT / REVOKE ON ROLES
# ═══════════════════════════════════════════════════════════════════


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
    service: RbacService = Depends(_get_rbac_service),
) -> dict[str, Any]:
    try:
        return await service.grant_permission(
            role_id=request_body.role_id,
            permission_id=request_body.permission_id,
            actor_id=current_user.id,
            actor_username=current_user.username,
            ip_address=_get_client_ip(request),
        )
    except ValueError as e:
        msg = str(e)
        if "not found" in msg:
            raise HTTPException(status_code=404, detail=msg) from e
        if "already granted" in msg:
            raise HTTPException(status_code=409, detail=msg) from e
        raise HTTPException(status_code=400, detail=msg) from e


@router.post(
    "/roles/revoke-permission",
    summary="Revoke permission from a role ",
    dependencies=[Depends(require_permission("rbac.update"))],
)
async def revoke_permission_from_role(
    request_body: PermissionRevokeRequest,
    request: Request,
    current_user: User = Depends(get_current_active_user),
    service: RbacService = Depends(_get_rbac_service),
) -> dict[str, Any]:
    try:
        return await service.revoke_permission(
            role_id=request_body.role_id,
            permission_id=request_body.permission_id,
            actor_id=current_user.id,
            actor_username=current_user.username,
            ip_address=_get_client_ip(request),
        )
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e)) from e


# ═══════════════════════════════════════════════════════════════════
# ROLE ASSIGNMENTS (User ↔ Role)
# ═══════════════════════════════════════════════════════════════════


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
    service: RbacService = Depends(_get_rbac_service),
) -> RoleAssignmentResponse:
    try:
        assignment = await service.assign_role(
            user_id=request_body.user_id,
            role_id=request_body.role_id,
            tenant_id=request_body.tenant_id,
            actor_id=current_user.id,
            actor_username=current_user.username,
            ip_address=_get_client_ip(request),
        )
    except ValueError as e:
        msg = str(e)
        if "not found" in msg:
            raise HTTPException(status_code=404, detail=msg) from e
        if "already assigned" in msg:
            raise HTTPException(status_code=409, detail=msg) from e
        raise HTTPException(status_code=400, detail=msg) from e
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
    service: RbacService = Depends(_get_rbac_service),
) -> dict[str, Any]:
    try:
        return await service.revoke_role(
            user_id=request_body.user_id,
            role_id=request_body.role_id,
            tenant_id=request_body.tenant_id,
            actor_id=current_user.id,
            actor_username=current_user.username,
            ip_address=_get_client_ip(request),
        )
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e)) from e


# ═══════════════════════════════════════════════════════════════════
# USER PERMISSION QUERIES (for frontend consumption)
# ═══════════════════════════════════════════════════════════════════


@router.get(
    "/my-permissions/menu",
    response_model=MenuPermissionsResponse,
    summary="Get current user's menu permissions",
)
async def get_my_menu_permissions(
    current_user: User = Depends(get_current_active_user),
    service: RbacService = Depends(_get_rbac_service),
) -> MenuPermissionsResponse:
    data = await service.get_my_menu_permissions(current_user)
    return MenuPermissionsResponse(
        menu_keys=data["menu_keys"],
        permissions=[PermissionResponse.model_validate(p) for p in data["permissions"]],
    )


@router.get(
    "/my-permissions/api",
    response_model=ApiPermissionsResponse,
    summary="Get current user's API permissions",
)
async def get_my_api_permissions(
    current_user: User = Depends(get_current_active_user),
    service: RbacService = Depends(_get_rbac_service),
) -> ApiPermissionsResponse:
    """
    GET /api/v1/rbac/my-permissions/api

    Lets the UI hide controls the caller could not use anyway. Guarded by
    authentication alone, like the menu equivalent: it only ever reports the
    caller's own grants, and needing a permission to discover your permissions
    would be circular.
    """
    data = await service.get_my_api_permissions(current_user)
    return ApiPermissionsResponse(
        codes=data["codes"],
        resource_actions=data["resource_actions"],
        permissions=[PermissionResponse.model_validate(p) for p in data["permissions"]],
    )


@router.get(
    "/my-permissions/all",
    summary="Get ALL permissions for the current user (debug)",
)
async def get_my_all_permissions(
    current_user: User = Depends(get_current_active_user),
    service: RbacService = Depends(_get_rbac_service),
) -> dict[str, Any]:
    return await service.get_my_all_permissions(current_user)


@router.get(
    "/my-permissions/fields/{resource}",
    response_model=FieldPermissionsResponse,
    summary="Get current user's field-level permissions for a resource",
)
async def get_my_field_permissions(
    resource: str,
    current_user: User = Depends(get_current_active_user),
    service: RbacService = Depends(_get_rbac_service),
) -> FieldPermissionsResponse:
    data = await service.get_my_field_permissions(current_user, resource)
    return FieldPermissionsResponse(resource=data["resource"], fields=data["fields"])


# ═══════════════════════════════════════════════════════════════════
# AUDIT LOGS (read-only)
# ═══════════════════════════════════════════════════════════════════


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
    service: RbacService = Depends(_get_rbac_service),
) -> AuditLogListResponse:
    data = await service.list_audit_logs(
        action=action,
        actor_username=actor_username,
        resource_type=resource_type,
        skip=skip,
        limit=limit,
    )
    return AuditLogListResponse(
        logs=[AuditLogResponse.model_validate(log) for log in data["logs"]],
        total=data["total"],
        skip=data["skip"],
        limit=data["limit"],
    )
