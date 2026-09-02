"""
RBAC Application Service.

Depends only on domain ports — no SQLAlchemy session, no ORM models. That keeps
the application layer free of infrastructure and makes the service unit-testable
with fake repositories.

Transaction boundary: repositories flush but never commit. The request-scoped
session (`get_db_session`) commits once if the request succeeds and rolls back
otherwise. Committing inside these methods previously made each one its own
transaction, so a caller could not compose two operations atomically — a later
failure left earlier writes permanently applied.
"""

import json
from typing import Any

from src.domain.entities.audit_log import AuditAction, AuditLog
from src.domain.entities.role import (
    Permission,
    PermissionScope,
    Role,
    RoleAssignment,
)
from src.domain.entities.user import User
from src.domain.repositories.audit_log_repository import IAuditLogRepository
from src.domain.repositories.permission_repository import IPermissionRepository
from src.domain.repositories.role_assignment_repository import IRoleAssignmentRepository
from src.domain.repositories.role_repository import IRoleRepository
from src.domain.services.permission_resolver import IPermissionResolver


class RbacService:
    """Application service for RBAC management."""

    def __init__(
        self,
        permission_repo: IPermissionRepository,
        role_repo: IRoleRepository,
        assignment_repo: IRoleAssignmentRepository,
        audit_repo: IAuditLogRepository,
        permission_resolver: IPermissionResolver,
    ) -> None:
        self._permissions = permission_repo
        self._roles = role_repo
        self._assignments = assignment_repo
        self._audit = audit_repo
        self._resolver = permission_resolver

    # ─── Audit helper ───

    async def _audit_log(
        self,
        *,
        actor_id: int | None,
        actor_username: str,
        action: AuditAction,
        resource_type: str,
        resource_id: str,
        tenant_id: int | None = None,
        old_value: dict[str, Any] | None = None,
        new_value: dict[str, Any] | None = None,
        ip_address: str = "",
    ) -> None:
        """Append an audit entry, JSON-encoding the before/after snapshots."""
        await self._audit.add(
            AuditLog(
                actor_id=actor_id,
                actor_username=actor_username,
                action=str(action),
                resource_type=resource_type,
                resource_id=resource_id,
                tenant_id=tenant_id,
                old_value=json.dumps(old_value) if old_value else None,
                new_value=json.dumps(new_value) if new_value else None,
                ip_address=ip_address,
            )
        )

    # ─── Permissions ───

    async def list_permissions(self, scope: str | None = None) -> list[Permission]:
        """List permissions, optionally filtered by scope."""
        return await self._permissions.list_active(scope=scope)

    async def create_permission(
        self,
        *,
        code: str,
        name: str,
        description: str | None,
        scope: str,
        resource: str,
        action: str,
        actor_id: int,
        actor_username: str,
        ip_address: str,
    ) -> Permission:
        """Create a new permission definition."""
        if await self._permissions.get_by_code(code):
            raise ValueError(f"Permission code '{code}' already exists")

        created = await self._permissions.create(
            Permission(
                code=code,
                name=name,
                description=description or "",
                scope=scope,
                resource=resource,
                action=action,
                is_active=True,
                created_by=actor_username,
                modified_by=actor_username,
            )
        )

        await self._audit_log(
            actor_id=actor_id,
            actor_username=actor_username,
            action=AuditAction.PERMISSION_CREATED,
            resource_type="Permission",
            resource_id=str(created.id),
            new_value={
                "code": created.code,
                "scope": created.scope,
                "resource": created.resource,
                "action": created.action,
            },
            ip_address=ip_address,
        )
        return created

    # ─── Roles ───

    async def list_roles(self, tenant_id: int | None = None) -> dict[str, Any]:
        """List roles with their permissions."""
        roles = await self._roles.list_active(tenant_id=tenant_id)
        return {"roles": roles, "total": len(roles)}

    async def create_role(
        self,
        *,
        code: str,
        name: str,
        description: str | None,
        tenant_id: int | None,
        parent_role_id: int | None,
        actor_id: int,
        actor_username: str,
        ip_address: str,
    ) -> Role:
        """Create a new role."""
        if await self._roles.get_by_code(code):
            raise ValueError(f"Role code '{code}' already exists")

        created = await self._roles.create(
            Role(
                code=code,
                name=name,
                description=description or "",
                is_system=False,
                is_active=True,
                tenant_id=tenant_id,
                parent_role_id=parent_role_id,
                created_by=actor_username,
                modified_by=actor_username,
            )
        )

        await self._audit_log(
            actor_id=actor_id,
            actor_username=actor_username,
            action=AuditAction.ROLE_CREATED,
            resource_type="Role",
            resource_id=str(created.id),
            tenant_id=tenant_id,
            new_value={"code": created.code, "name": created.name},
            ip_address=ip_address,
        )
        return created

    async def update_role(
        self,
        *,
        role_id: int,
        name: str | None = None,
        description: str | None = None,
        is_active: bool | None = None,
        parent_role_id: int | None = None,
        actor_id: int,
        actor_username: str,
        ip_address: str,
    ) -> Role:
        """Update role properties."""
        role = await self._roles.get_by_id(role_id, with_permissions=True)
        if not role:
            raise ValueError("Role not found")
        if role.is_system:
            raise ValueError("System roles cannot be modified")

        old_value = {
            "name": role.name,
            "description": role.description,
            "is_active": role.is_active,
        }

        if name is not None:
            role.name = name
        if description is not None:
            role.description = description
        if is_active is not None:
            role.is_active = is_active
        if parent_role_id is not None:
            role.parent_role_id = parent_role_id
        role.modified_by = actor_username

        updated = await self._roles.update(role)

        await self._audit_log(
            actor_id=actor_id,
            actor_username=actor_username,
            action=AuditAction.ROLE_UPDATED,
            resource_type="Role",
            resource_id=str(role_id),
            old_value=old_value,
            new_value={
                "name": updated.name,
                "description": updated.description,
                "is_active": updated.is_active,
            },
            ip_address=ip_address,
        )
        return updated

    # ─── Permission grant / revoke on roles ───

    async def grant_permission(
        self,
        *,
        role_id: int,
        permission_id: int,
        actor_id: int,
        actor_username: str,
        ip_address: str,
    ) -> dict[str, Any]:
        """Grant a permission to a role."""
        role = await self._roles.get_by_id(role_id)
        if not role:
            raise ValueError("Role not found")

        permission = await self._permissions.get_by_id(permission_id)
        if not permission:
            raise ValueError("Permission not found")

        if await self._roles.is_permission_granted(role_id, permission_id):
            raise ValueError("Permission already granted to this role")

        await self._roles.grant_permission(role_id, permission_id, actor_username)

        await self._audit_log(
            actor_id=actor_id,
            actor_username=actor_username,
            action=AuditAction.PERMISSION_GRANTED,
            resource_type="RolePermission",
            resource_id=str(role_id),
            new_value={"role_id": str(role_id), "permission_code": permission.code},
            ip_address=ip_address,
        )
        return {"detail": f"Permission '{permission.code}' granted to role '{role.code}'"}

    async def revoke_permission(
        self,
        *,
        role_id: int,
        permission_id: int,
        actor_id: int,
        actor_username: str,
        ip_address: str,
    ) -> dict[str, Any]:
        """Revoke a permission from a role."""
        permission = await self._permissions.get_by_id(permission_id)

        if not await self._roles.revoke_permission(role_id, permission_id):
            raise ValueError("Permission not assigned to this role")

        await self._audit_log(
            actor_id=actor_id,
            actor_username=actor_username,
            action=AuditAction.PERMISSION_REVOKED,
            resource_type="RolePermission",
            resource_id=str(role_id),
            new_value={
                "role_id": str(role_id),
                "permission_code": permission.code if permission else str(permission_id),
            },
            ip_address=ip_address,
        )
        return {"detail": "Permission revoked"}

    # ─── Role assignments (User <-> Role) ───

    async def assign_role(
        self,
        *,
        user_id: int,
        role_id: int,
        tenant_id: int | None,
        actor_id: int,
        actor_username: str,
        ip_address: str,
    ) -> RoleAssignment:
        """Assign a role to a user."""
        role = await self._roles.get_by_id(role_id)
        if not role:
            raise ValueError("Role not found")

        if await self._assignments.get_active(user_id, role_id):
            raise ValueError("Role already assigned to this user")

        created = await self._assignments.create(
            RoleAssignment(
                user_id=user_id,
                role_id=role_id,
                tenant_id=tenant_id,
                is_active=True,
                created_by=actor_username,
                modified_by=actor_username,
            )
        )

        await self._audit_log(
            actor_id=actor_id,
            actor_username=actor_username,
            action=AuditAction.ROLE_ASSIGNED,
            resource_type="RoleAssignment",
            resource_id=str(user_id),
            tenant_id=tenant_id,
            new_value={
                "user_id": str(user_id),
                "role_id": str(role_id),
                "role_code": role.code,
            },
            ip_address=ip_address,
        )
        return created

    async def revoke_role(
        self,
        *,
        user_id: int,
        role_id: int,
        tenant_id: int | None,
        actor_id: int,
        actor_username: str,
        ip_address: str,
    ) -> dict[str, Any]:
        """Revoke a role from a user."""
        assignment = await self._assignments.get_active(user_id, role_id)
        if not assignment:
            raise ValueError("Active role assignment not found")

        await self._assignments.deactivate(assignment.id, actor_username)

        role = await self._roles.get_by_id(role_id)

        await self._audit_log(
            actor_id=actor_id,
            actor_username=actor_username,
            action=AuditAction.ROLE_REVOKED,
            resource_type="RoleAssignment",
            resource_id=str(user_id),
            tenant_id=tenant_id,
            old_value={
                "user_id": str(user_id),
                "role_id": str(role_id),
                "role_code": role.code if role else str(role_id),
            },
            ip_address=ip_address,
        )
        return {"detail": "Role revoked"}

    # ─── User permission queries ───

    async def get_my_menu_permissions(self, current_user: User) -> dict[str, Any]:
        """Menu keys and MENU-scoped permissions for the current user."""
        permissions = await self._resolver.get_user_permissions(
            current_user.id, scope=PermissionScope.MENU
        )
        return {
            "menu_keys": list({p.resource for p in permissions}),
            "permissions": permissions,
        }

    async def get_my_api_permissions(self, current_user: User) -> dict[str, Any]:
        """
        API-scope permissions for the current user, shaped for the frontend.

        Returned as codes and as resource/action pairs: the UI gates some controls
        by permission code and others by the (resource, action) pair the endpoints
        authorise on, and the two are not mechanically derivable from each other.
        """
        permissions = await self._resolver.get_user_permissions(
            current_user.id, scope=PermissionScope.API
        )

        resource_actions: dict[str, list[str]] = {}
        for permission in permissions:
            actions = resource_actions.setdefault(permission.resource, [])
            if permission.action not in actions:
                actions.append(permission.action)

        return {
            "codes": sorted({p.code for p in permissions}),
            "resource_actions": resource_actions,
            "permissions": permissions,
        }

    async def get_my_all_permissions(self, current_user: User) -> dict[str, Any]:
        """Everything the current user can do (debug/introspection)."""
        assignments = await self._assignments.list_for_user(current_user.id)
        roles = await self._roles.list_by_ids([a.role_id for a in assignments])
        permissions = await self._resolver.get_user_permissions(current_user.id)

        return {
            "user_id": current_user.id,
            "username": current_user.username,
            "role_assignments": [
                {
                    "role_id": a.role_id,
                    "is_active": a.is_active,
                    "tenant_id": a.tenant_id,
                }
                for a in assignments
            ],
            "assigned_roles": [
                {
                    "id": r.id,
                    "code": r.code,
                    "name": r.name,
                    "is_active": r.is_active,
                    "permission_count": len(r.permissions),
                    "permissions": [self._permission_summary(p) for p in r.permissions],
                }
                for r in roles
            ],
            "total_effective_permissions": len(permissions),
            "effective_permissions": [self._permission_summary(p) for p in permissions],
        }

    async def get_my_field_permissions(
        self, current_user: User, resource: str
    ) -> dict[str, Any]:
        """Field-level permissions for the current user on one resource."""
        fields = await self._resolver.get_field_permissions(current_user.id, resource)
        return {"resource": resource, "fields": fields}

    # ─── Audit logs ───

    async def list_audit_logs(
        self,
        *,
        action: str | None = None,
        actor_username: str | None = None,
        resource_type: str | None = None,
        skip: int = 0,
        limit: int = 50,
    ) -> dict[str, Any]:
        """Query the audit trail with filters."""
        logs = await self._audit.query(
            action=action,
            actor_username=actor_username,
            resource_type=resource_type,
            skip=skip,
            limit=limit,
        )
        total = await self._audit.count(
            action=action,
            actor_username=actor_username,
            resource_type=resource_type,
        )
        return {"logs": logs, "total": total, "skip": skip, "limit": limit}

    # ─── Internals ───

    @staticmethod
    def _permission_summary(permission: Permission) -> dict[str, str]:
        """Compact permission shape used by the introspection endpoints."""
        return {
            "code": permission.code,
            "scope": permission.scope,
            "resource": permission.resource,
            "action": permission.action,
        }
