"""
RBAC service tests.

`RbacService` owns the rules around permissions, roles, role grants and role
assignments, and writes an audit entry for every change. The repositories only run
queries and the API tests only prove the wiring, so these tests pin the rules down
against in-memory fakes: existence and uniqueness checks, the system-role guard, which
fields of a partial role update actually change, and exactly what each operation records
in the audit trail.
"""

import json
from datetime import UTC, datetime, timedelta
from typing import Any

import pytest
from rbac_fakes import (
    FakeAuditLogRepository,
    FakePermissionRepository,
    FakePermissionResolver,
    FakeRoleAssignmentStore,
    FakeRoleRepository,
)

from src.application.services.rbac_service import RbacService
from src.domain.entities.audit_log import AuditAction, AuditLog
from src.domain.entities.role import (
    Permission,
    PermissionAction,
    PermissionScope,
    Role,
    RoleAssignment,
)
from src.domain.entities.user import User

ACTOR_ID = 1
ACTOR = "alice"
IP = "10.0.0.7"


def actor_kwargs() -> dict[str, Any]:
    """The audit-context arguments every mutating call takes."""
    return {"actor_id": ACTOR_ID, "actor_username": ACTOR, "ip_address": IP}


def make_permission(
    code: str,
    *,
    scope: str = PermissionScope.API,
    resource: str = "users",
    action: str = PermissionAction.READ,
    is_active: bool = True,
) -> Permission:
    return Permission(
        code=code,
        name=code.title(),
        scope=scope,
        resource=resource,
        action=action,
        is_active=is_active,
    )


def make_role(code: str = "EDITOR", **overrides: Any) -> Role:
    values: dict[str, Any] = {"code": code, "name": code.title(), "description": "d"}
    values.update(overrides)
    return Role(**values)


@pytest.fixture
def permissions() -> FakePermissionRepository:
    return FakePermissionRepository()


@pytest.fixture
def roles(permissions: FakePermissionRepository) -> FakeRoleRepository:
    return FakeRoleRepository(permissions)


@pytest.fixture
def assignments() -> FakeRoleAssignmentStore:
    return FakeRoleAssignmentStore()


@pytest.fixture
def audit() -> FakeAuditLogRepository:
    return FakeAuditLogRepository()


@pytest.fixture
def resolver() -> FakePermissionResolver:
    return FakePermissionResolver()


@pytest.fixture
def service(
    permissions: FakePermissionRepository,
    roles: FakeRoleRepository,
    assignments: FakeRoleAssignmentStore,
    audit: FakeAuditLogRepository,
    resolver: FakePermissionResolver,
) -> RbacService:
    return RbacService(permissions, roles, assignments, audit, resolver)


@pytest.fixture
def current_user() -> User:
    return User(id=42, username="bob")


class TestListPermissions:
    async def test_returns_only_active_permissions(
        self, service: RbacService, permissions: FakePermissionRepository
    ) -> None:
        permissions.add(make_permission("users.list"))
        permissions.add(make_permission("users.old", is_active=False))

        result = await service.list_permissions()

        assert [p.code for p in result] == ["users.list"]

    async def test_scope_filter_narrows_the_list(
        self, service: RbacService, permissions: FakePermissionRepository
    ) -> None:
        permissions.add(make_permission("menu.users", scope=PermissionScope.MENU))
        permissions.add(make_permission("users.list", scope=PermissionScope.API))

        result = await service.list_permissions(scope=PermissionScope.MENU)

        assert [p.code for p in result] == ["menu.users"]


class TestCreatePermission:
    async def _create(self, service: RbacService, **overrides: Any) -> Permission:
        values: dict[str, Any] = {
            "code": "users.create",
            "name": "Create users",
            "description": "Can create users",
            "scope": PermissionScope.API,
            "resource": "users",
            "action": PermissionAction.CREATE,
            **actor_kwargs(),
        }
        values.update(overrides)
        return await service.create_permission(**values)

    async def test_creates_an_active_permission_stamped_with_the_actor(
        self, service: RbacService, permissions: FakePermissionRepository
    ) -> None:
        created = await self._create(service)

        assert created.id != 0
        assert created.is_active is True
        assert created.created_by == ACTOR
        assert created.modified_by == ACTOR
        stored = await permissions.get_by_code("users.create")
        assert stored is not None
        assert (stored.scope, stored.resource, stored.action) == (
            PermissionScope.API,
            "users",
            PermissionAction.CREATE,
        )

    async def test_missing_description_is_stored_as_empty_string(
        self, service: RbacService
    ) -> None:
        created = await self._create(service, description=None)

        assert created.description == ""

    async def test_duplicate_code_is_rejected_and_nothing_is_audited(
        self,
        service: RbacService,
        permissions: FakePermissionRepository,
        audit: FakeAuditLogRepository,
    ) -> None:
        permissions.add(make_permission("users.create"))

        with pytest.raises(ValueError, match="Permission code 'users.create' already exists"):
            await self._create(service)

        assert len(permissions.rows) == 1
        assert audit.entries == []

    async def test_records_a_permission_created_audit_entry(
        self, service: RbacService, audit: FakeAuditLogRepository
    ) -> None:
        created = await self._create(service)

        (entry,) = audit.entries
        assert entry.action == "PERMISSION_CREATED"
        assert entry.resource_type == "Permission"
        assert entry.resource_id == str(created.id)
        assert (entry.actor_id, entry.actor_username, entry.ip_address) == (
            ACTOR_ID,
            ACTOR,
            IP,
        )
        assert entry.old_value is None
        assert entry.new_value is not None
        assert json.loads(entry.new_value) == {
            "code": "users.create",
            "scope": "API",
            "resource": "users",
            "action": "CREATE",
        }


class TestListRoles:
    async def test_returns_active_roles_with_total_ordered_by_code(
        self, service: RbacService, roles: FakeRoleRepository
    ) -> None:
        roles.add(make_role("ZETA"))
        roles.add(make_role("ALPHA"))
        roles.add(make_role("GONE", is_active=False))

        result = await service.list_roles()

        assert [r.code for r in result["roles"]] == ["ALPHA", "ZETA"]
        assert result["total"] == 2

    async def test_tenant_filter_returns_that_tenants_roles_plus_global_ones(
        self, service: RbacService, roles: FakeRoleRepository
    ) -> None:
        roles.add(make_role("GLOBAL"))
        roles.add(make_role("T1_ROLE", tenant_id=1))
        roles.add(make_role("T2_ROLE", tenant_id=2))

        result = await service.list_roles(tenant_id=1)

        assert [r.code for r in result["roles"]] == ["GLOBAL", "T1_ROLE"]
        assert result["total"] == 2

    async def test_roles_carry_their_granted_permissions(
        self,
        service: RbacService,
        roles: FakeRoleRepository,
        permissions: FakePermissionRepository,
    ) -> None:
        role = roles.add(make_role("EDITOR"))
        perm = permissions.add(make_permission("users.list"))
        roles.link(role.id, perm.id)

        result = await service.list_roles()

        assert [p.code for p in result["roles"][0].permissions] == ["users.list"]


class TestCreateRole:
    async def _create(self, service: RbacService, **overrides: Any) -> Role:
        values: dict[str, Any] = {
            "code": "EDITOR",
            "name": "Editor",
            "description": "Edits things",
            "tenant_id": None,
            "parent_role_id": None,
            **actor_kwargs(),
        }
        values.update(overrides)
        return await service.create_role(**values)

    async def test_creates_an_active_non_system_role(
        self, service: RbacService, roles: FakeRoleRepository
    ) -> None:
        created = await self._create(service, tenant_id=3, parent_role_id=9)

        assert created.id != 0
        assert created.is_system is False
        assert created.is_active is True
        assert created.tenant_id == 3
        assert created.parent_role_id == 9
        assert created.created_by == ACTOR
        assert await roles.get_by_code("EDITOR") is not None

    async def test_missing_description_is_stored_as_empty_string(
        self, service: RbacService
    ) -> None:
        created = await self._create(service, description=None)

        assert created.description == ""

    async def test_duplicate_code_is_rejected_and_nothing_is_audited(
        self,
        service: RbacService,
        roles: FakeRoleRepository,
        audit: FakeAuditLogRepository,
    ) -> None:
        roles.add(make_role("EDITOR"))

        with pytest.raises(ValueError, match="Role code 'EDITOR' already exists"):
            await self._create(service)

        assert len(roles.rows) == 1
        assert audit.entries == []

    async def test_records_a_role_created_audit_entry_with_the_tenant(
        self, service: RbacService, audit: FakeAuditLogRepository
    ) -> None:
        created = await self._create(service, tenant_id=3)

        (entry,) = audit.entries
        assert entry.action == "ROLE_CREATED"
        assert entry.resource_type == "Role"
        assert entry.resource_id == str(created.id)
        assert entry.tenant_id == 3
        assert entry.new_value is not None
        assert json.loads(entry.new_value) == {"code": "EDITOR", "name": "Editor"}


class TestUpdateRole:
    async def _update(self, service: RbacService, role_id: int, **fields: Any) -> Role:
        return await service.update_role(role_id=role_id, **fields, **actor_kwargs())

    async def test_unknown_role_is_rejected(self, service: RbacService) -> None:
        with pytest.raises(ValueError, match="Role not found"):
            await self._update(service, 999, name="x")

    async def test_system_role_cannot_be_modified(
        self,
        service: RbacService,
        roles: FakeRoleRepository,
        audit: FakeAuditLogRepository,
    ) -> None:
        role = roles.add(make_role("ADMIN", is_system=True))

        with pytest.raises(ValueError, match="System roles cannot be modified"):
            await self._update(service, role.id, name="Renamed")

        stored = await roles.get_by_id(role.id)
        assert stored is not None
        assert stored.name == "Admin"
        assert audit.entries == []

    async def test_name_alone_changes_only_the_name(
        self, service: RbacService, roles: FakeRoleRepository
    ) -> None:
        role = roles.add(make_role("EDITOR", description="old", parent_role_id=5))

        updated = await self._update(service, role.id, name="New Name")

        assert updated.name == "New Name"
        assert updated.description == "old"
        assert updated.is_active is True
        assert updated.parent_role_id == 5

    async def test_description_alone_changes_only_the_description(
        self, service: RbacService, roles: FakeRoleRepository
    ) -> None:
        role = roles.add(make_role("EDITOR", parent_role_id=5))

        updated = await self._update(service, role.id, description="new description")

        assert updated.description == "new description"
        assert updated.name == "Editor"
        assert updated.is_active is True
        assert updated.parent_role_id == 5

    async def test_is_active_false_deactivates_without_touching_other_fields(
        self, service: RbacService, roles: FakeRoleRepository
    ) -> None:
        role = roles.add(make_role("EDITOR", parent_role_id=5))

        updated = await self._update(service, role.id, is_active=False)

        assert updated.is_active is False
        assert updated.name == "Editor"
        assert updated.description == "d"
        assert updated.parent_role_id == 5

    async def test_parent_role_alone_changes_only_the_parent(
        self, service: RbacService, roles: FakeRoleRepository
    ) -> None:
        role = roles.add(make_role("EDITOR"))

        updated = await self._update(service, role.id, parent_role_id=8)

        assert updated.parent_role_id == 8
        assert updated.name == "Editor"
        assert updated.description == "d"
        assert updated.is_active is True

    async def test_empty_description_is_applied_not_skipped(
        self, service: RbacService, roles: FakeRoleRepository
    ) -> None:
        role = roles.add(make_role("EDITOR", description="something"))

        updated = await self._update(service, role.id, description="")

        assert updated.description == ""

    async def test_update_is_persisted_and_stamps_the_actor(
        self, service: RbacService, roles: FakeRoleRepository
    ) -> None:
        role = roles.add(make_role("EDITOR"))

        await self._update(service, role.id, name="Persisted")

        stored = await roles.get_by_id(role.id)
        assert stored is not None
        assert stored.name == "Persisted"
        assert stored.modified_by == ACTOR

    async def test_update_returns_the_roles_permissions(
        self,
        service: RbacService,
        roles: FakeRoleRepository,
        permissions: FakePermissionRepository,
    ) -> None:
        role = roles.add(make_role("EDITOR"))
        perm = permissions.add(make_permission("users.list"))
        roles.link(role.id, perm.id)

        updated = await self._update(service, role.id, name="Renamed")

        assert [p.code for p in updated.permissions] == ["users.list"]

    async def test_audit_entry_records_before_and_after(
        self,
        service: RbacService,
        roles: FakeRoleRepository,
        audit: FakeAuditLogRepository,
    ) -> None:
        role = roles.add(make_role("EDITOR", description="old"))

        await self._update(service, role.id, name="New Name", is_active=False)

        (entry,) = audit.entries
        assert entry.action == "ROLE_UPDATED"
        assert entry.resource_type == "Role"
        assert entry.resource_id == str(role.id)
        assert entry.old_value is not None
        assert entry.new_value is not None
        assert json.loads(entry.old_value) == {
            "name": "Editor",
            "description": "old",
            "is_active": True,
        }
        assert json.loads(entry.new_value) == {
            "name": "New Name",
            "description": "old",
            "is_active": False,
        }


class TestGrantPermission:
    async def _grant(self, service: RbacService, role_id: int, permission_id: int) -> Any:
        return await service.grant_permission(
            role_id=role_id, permission_id=permission_id, **actor_kwargs()
        )

    async def test_unknown_role_is_rejected(
        self, service: RbacService, permissions: FakePermissionRepository
    ) -> None:
        perm = permissions.add(make_permission("users.list"))

        with pytest.raises(ValueError, match="Role not found"):
            await self._grant(service, 999, perm.id)

    async def test_unknown_permission_is_rejected(
        self, service: RbacService, roles: FakeRoleRepository
    ) -> None:
        role = roles.add(make_role("EDITOR"))

        with pytest.raises(ValueError, match="Permission not found"):
            await self._grant(service, role.id, 999)

    async def test_missing_role_is_reported_before_missing_permission(
        self, service: RbacService
    ) -> None:
        with pytest.raises(ValueError, match="Role not found"):
            await self._grant(service, 998, 999)

    async def test_already_granted_permission_is_rejected(
        self,
        service: RbacService,
        roles: FakeRoleRepository,
        permissions: FakePermissionRepository,
        audit: FakeAuditLogRepository,
    ) -> None:
        role = roles.add(make_role("EDITOR"))
        perm = permissions.add(make_permission("users.list"))
        roles.link(role.id, perm.id)

        with pytest.raises(ValueError, match="Permission already granted to this role"):
            await self._grant(service, role.id, perm.id)

        assert audit.entries == []

    async def test_grant_links_the_permission_and_reports_it(
        self,
        service: RbacService,
        roles: FakeRoleRepository,
        permissions: FakePermissionRepository,
    ) -> None:
        role = roles.add(make_role("EDITOR"))
        perm = permissions.add(make_permission("users.list"))

        result = await self._grant(service, role.id, perm.id)

        assert result == {"detail": "Permission 'users.list' granted to role 'EDITOR'"}
        assert await roles.is_permission_granted(role.id, perm.id) is True

    async def test_grant_records_a_permission_granted_audit_entry(
        self,
        service: RbacService,
        roles: FakeRoleRepository,
        permissions: FakePermissionRepository,
        audit: FakeAuditLogRepository,
    ) -> None:
        role = roles.add(make_role("EDITOR"))
        perm = permissions.add(make_permission("users.list"))

        await self._grant(service, role.id, perm.id)

        (entry,) = audit.entries
        assert entry.action == "PERMISSION_GRANTED"
        assert entry.resource_type == "RolePermission"
        assert entry.resource_id == str(role.id)
        assert entry.new_value is not None
        assert json.loads(entry.new_value) == {
            "role_id": str(role.id),
            "permission_code": "users.list",
        }


class TestRevokePermission:
    async def _revoke(self, service: RbacService, role_id: int, permission_id: int) -> Any:
        return await service.revoke_permission(
            role_id=role_id, permission_id=permission_id, **actor_kwargs()
        )

    async def test_permission_not_assigned_to_the_role_is_rejected(
        self,
        service: RbacService,
        roles: FakeRoleRepository,
        permissions: FakePermissionRepository,
        audit: FakeAuditLogRepository,
    ) -> None:
        role = roles.add(make_role("EDITOR"))
        perm = permissions.add(make_permission("users.list"))

        with pytest.raises(ValueError, match="Permission not assigned to this role"):
            await self._revoke(service, role.id, perm.id)

        assert audit.entries == []

    async def test_revoke_unlinks_the_permission(
        self,
        service: RbacService,
        roles: FakeRoleRepository,
        permissions: FakePermissionRepository,
    ) -> None:
        role = roles.add(make_role("EDITOR"))
        perm = permissions.add(make_permission("users.list"))
        roles.link(role.id, perm.id)

        result = await self._revoke(service, role.id, perm.id)

        assert result == {"detail": "Permission revoked"}
        assert await roles.is_permission_granted(role.id, perm.id) is False

    async def test_revoke_records_the_permission_code_in_the_audit_entry(
        self,
        service: RbacService,
        roles: FakeRoleRepository,
        permissions: FakePermissionRepository,
        audit: FakeAuditLogRepository,
    ) -> None:
        role = roles.add(make_role("EDITOR"))
        perm = permissions.add(make_permission("users.list"))
        roles.link(role.id, perm.id)

        await self._revoke(service, role.id, perm.id)

        (entry,) = audit.entries
        assert entry.action == "PERMISSION_REVOKED"
        assert entry.resource_type == "RolePermission"
        assert entry.resource_id == str(role.id)
        assert entry.new_value is not None
        assert json.loads(entry.new_value) == {
            "role_id": str(role.id),
            "permission_code": "users.list",
        }

    async def test_audit_falls_back_to_the_id_when_the_permission_row_is_gone(
        self,
        service: RbacService,
        roles: FakeRoleRepository,
        audit: FakeAuditLogRepository,
    ) -> None:
        role = roles.add(make_role("EDITOR"))
        roles.link(role.id, 777)  # a link whose permission row no longer exists

        await self._revoke(service, role.id, 777)

        (entry,) = audit.entries
        assert entry.new_value is not None
        assert json.loads(entry.new_value)["permission_code"] == "777"


class TestAssignRole:
    async def _assign(
        self, service: RbacService, user_id: int, role_id: int, tenant_id: int | None = None
    ) -> RoleAssignment:
        return await service.assign_role(
            user_id=user_id, role_id=role_id, tenant_id=tenant_id, **actor_kwargs()
        )

    async def test_unknown_role_is_rejected(
        self, service: RbacService, assignments: FakeRoleAssignmentStore
    ) -> None:
        with pytest.raises(ValueError, match="Role not found"):
            await self._assign(service, 10, 999)

        assert assignments.rows == {}

    async def test_user_already_holding_the_role_is_rejected(
        self,
        service: RbacService,
        roles: FakeRoleRepository,
        assignments: FakeRoleAssignmentStore,
        audit: FakeAuditLogRepository,
    ) -> None:
        role = roles.add(make_role("EDITOR"))
        assignments.add(RoleAssignment(user_id=10, role_id=role.id))

        with pytest.raises(ValueError, match="Role already assigned to this user"):
            await self._assign(service, 10, role.id)

        assert len(assignments.rows) == 1
        assert audit.entries == []

    async def test_a_revoked_assignment_does_not_block_reassignment(
        self,
        service: RbacService,
        roles: FakeRoleRepository,
        assignments: FakeRoleAssignmentStore,
    ) -> None:
        role = roles.add(make_role("EDITOR"))
        assignments.add(RoleAssignment(user_id=10, role_id=role.id, is_active=False))

        created = await self._assign(service, 10, role.id)

        assert created.is_active is True
        assert len(assignments.rows) == 2

    async def test_creates_an_active_assignment_stamped_with_the_actor(
        self, service: RbacService, roles: FakeRoleRepository
    ) -> None:
        role = roles.add(make_role("EDITOR"))

        created = await self._assign(service, 10, role.id, tenant_id=4)

        assert created.id != 0
        assert (created.user_id, created.role_id, created.tenant_id) == (10, role.id, 4)
        assert created.is_active is True
        assert created.created_by == ACTOR

    async def test_same_role_can_go_to_different_users(
        self, service: RbacService, roles: FakeRoleRepository
    ) -> None:
        role = roles.add(make_role("EDITOR"))

        first = await self._assign(service, 10, role.id)
        second = await self._assign(service, 11, role.id)

        assert first.id != second.id

    async def test_records_a_role_assigned_audit_entry(
        self,
        service: RbacService,
        roles: FakeRoleRepository,
        audit: FakeAuditLogRepository,
    ) -> None:
        role = roles.add(make_role("EDITOR"))

        await self._assign(service, 10, role.id, tenant_id=4)

        (entry,) = audit.entries
        assert entry.action == "ROLE_ASSIGNED"
        assert entry.resource_type == "RoleAssignment"
        assert entry.resource_id == "10"
        assert entry.tenant_id == 4
        assert entry.new_value is not None
        assert json.loads(entry.new_value) == {
            "user_id": "10",
            "role_id": str(role.id),
            "role_code": "EDITOR",
        }


class TestRevokeRole:
    async def _revoke(
        self, service: RbacService, user_id: int, role_id: int, tenant_id: int | None = None
    ) -> Any:
        return await service.revoke_role(
            user_id=user_id, role_id=role_id, tenant_id=tenant_id, **actor_kwargs()
        )

    async def test_missing_assignment_is_rejected(
        self, service: RbacService, audit: FakeAuditLogRepository
    ) -> None:
        with pytest.raises(ValueError, match="Active role assignment not found"):
            await self._revoke(service, 10, 5)

        assert audit.entries == []

    async def test_already_revoked_assignment_is_treated_as_missing(
        self, service: RbacService, assignments: FakeRoleAssignmentStore
    ) -> None:
        assignments.add(RoleAssignment(user_id=10, role_id=5, is_active=False))

        with pytest.raises(ValueError, match="Active role assignment not found"):
            await self._revoke(service, 10, 5)

    async def test_deactivates_the_assignment_rather_than_deleting_it(
        self,
        service: RbacService,
        roles: FakeRoleRepository,
        assignments: FakeRoleAssignmentStore,
    ) -> None:
        role = roles.add(make_role("EDITOR"))
        row = assignments.add(RoleAssignment(user_id=10, role_id=role.id))

        result = await self._revoke(service, 10, role.id)

        assert result == {"detail": "Role revoked"}
        assert assignments.rows[row.id].is_active is False
        assert assignments.rows[row.id].modified_by == ACTOR

    async def test_only_the_named_assignment_is_revoked(
        self,
        service: RbacService,
        roles: FakeRoleRepository,
        assignments: FakeRoleAssignmentStore,
    ) -> None:
        role = roles.add(make_role("EDITOR"))
        other_role = roles.add(make_role("VIEWER"))
        assignments.add(RoleAssignment(user_id=10, role_id=role.id))
        kept = assignments.add(RoleAssignment(user_id=10, role_id=other_role.id))
        other_user = assignments.add(RoleAssignment(user_id=11, role_id=role.id))

        await self._revoke(service, 10, role.id)

        assert assignments.rows[kept.id].is_active is True
        assert assignments.rows[other_user.id].is_active is True

    async def test_records_a_role_revoked_audit_entry_with_the_old_value(
        self,
        service: RbacService,
        roles: FakeRoleRepository,
        assignments: FakeRoleAssignmentStore,
        audit: FakeAuditLogRepository,
    ) -> None:
        role = roles.add(make_role("EDITOR"))
        assignments.add(RoleAssignment(user_id=10, role_id=role.id))

        await self._revoke(service, 10, role.id, tenant_id=4)

        (entry,) = audit.entries
        assert entry.action == "ROLE_REVOKED"
        assert entry.resource_type == "RoleAssignment"
        assert entry.resource_id == "10"
        assert entry.tenant_id == 4
        assert entry.new_value is None
        assert entry.old_value is not None
        assert json.loads(entry.old_value) == {
            "user_id": "10",
            "role_id": str(role.id),
            "role_code": "EDITOR",
        }

    async def test_audit_falls_back_to_the_id_when_the_role_row_is_gone(
        self,
        service: RbacService,
        assignments: FakeRoleAssignmentStore,
        audit: FakeAuditLogRepository,
    ) -> None:
        assignments.add(RoleAssignment(user_id=10, role_id=555))  # no such role row

        await self._revoke(service, 10, 555)

        (entry,) = audit.entries
        assert entry.old_value is not None
        assert json.loads(entry.old_value)["role_code"] == "555"


class TestMyMenuPermissions:
    async def test_asks_the_resolver_for_menu_scope_only(
        self, service: RbacService, resolver: FakePermissionResolver, current_user: User
    ) -> None:
        await service.get_my_menu_permissions(current_user)

        assert resolver.permission_calls == [(42, None, PermissionScope.MENU)]

    async def test_menu_keys_are_the_distinct_resources(
        self, service: RbacService, resolver: FakePermissionResolver, current_user: User
    ) -> None:
        resolver.permissions[42] = [
            make_permission("menu.users", scope=PermissionScope.MENU, resource="users"),
            make_permission("menu.users2", scope=PermissionScope.MENU, resource="users"),
            make_permission("menu.roles", scope=PermissionScope.MENU, resource="roles"),
            make_permission("users.list", scope=PermissionScope.API, resource="audit"),
        ]

        result = await service.get_my_menu_permissions(current_user)

        assert sorted(result["menu_keys"]) == ["roles", "users"]
        assert {p.code for p in result["permissions"]} == {
            "menu.users",
            "menu.users2",
            "menu.roles",
        }

    async def test_user_without_permissions_gets_empty_results(
        self, service: RbacService, current_user: User
    ) -> None:
        result = await service.get_my_menu_permissions(current_user)

        assert result == {"menu_keys": [], "permissions": []}


class TestMyApiPermissions:
    async def test_asks_the_resolver_for_api_scope_only(
        self, service: RbacService, resolver: FakePermissionResolver, current_user: User
    ) -> None:
        await service.get_my_api_permissions(current_user)

        assert resolver.permission_calls == [(42, None, PermissionScope.API)]

    async def test_codes_are_sorted_and_unique(
        self, service: RbacService, resolver: FakePermissionResolver, current_user: User
    ) -> None:
        resolver.permissions[42] = [
            make_permission("users.update", action=PermissionAction.UPDATE),
            make_permission("users.list", action=PermissionAction.READ),
            make_permission("users.list", action=PermissionAction.READ),
        ]

        result = await service.get_my_api_permissions(current_user)

        assert result["codes"] == ["users.list", "users.update"]

    async def test_resource_actions_group_actions_per_resource_without_duplicates(
        self, service: RbacService, resolver: FakePermissionResolver, current_user: User
    ) -> None:
        resolver.permissions[42] = [
            make_permission("users.list", resource="users", action=PermissionAction.READ),
            make_permission("users.list2", resource="users", action=PermissionAction.READ),
            make_permission("users.create", resource="users", action=PermissionAction.CREATE),
            make_permission("roles.list", resource="roles", action=PermissionAction.READ),
        ]

        result = await service.get_my_api_permissions(current_user)

        assert result["resource_actions"] == {
            "users": ["READ", "CREATE"],
            "roles": ["READ"],
        }
        assert len(result["permissions"]) == 4

    async def test_user_without_permissions_gets_empty_results(
        self, service: RbacService, current_user: User
    ) -> None:
        result = await service.get_my_api_permissions(current_user)

        assert result == {"codes": [], "resource_actions": {}, "permissions": []}


class TestMyAllPermissions:
    async def test_summarises_assignments_roles_and_effective_permissions(
        self,
        service: RbacService,
        roles: FakeRoleRepository,
        permissions: FakePermissionRepository,
        assignments: FakeRoleAssignmentStore,
        resolver: FakePermissionResolver,
        current_user: User,
    ) -> None:
        role = roles.add(make_role("EDITOR"))
        perm = permissions.add(
            make_permission(
                "users.list", resource="users", action=PermissionAction.READ
            )
        )
        roles.link(role.id, perm.id)
        assignments.add(RoleAssignment(user_id=42, role_id=role.id, tenant_id=7))
        resolver.permissions[42] = [perm]

        result = await service.get_my_all_permissions(current_user)

        summary = {
            "code": "users.list",
            "scope": "API",
            "resource": "users",
            "action": "READ",
        }
        assert result["user_id"] == 42
        assert result["username"] == "bob"
        assert result["role_assignments"] == [
            {"role_id": role.id, "is_active": True, "tenant_id": 7}
        ]
        assert result["assigned_roles"] == [
            {
                "id": role.id,
                "code": "EDITOR",
                "name": "Editor",
                "is_active": True,
                "permission_count": 1,
                "permissions": [summary],
            }
        ]
        assert result["total_effective_permissions"] == 1
        assert result["effective_permissions"] == [summary]

    async def test_inactive_assignments_are_still_listed(
        self,
        service: RbacService,
        roles: FakeRoleRepository,
        assignments: FakeRoleAssignmentStore,
        current_user: User,
    ) -> None:
        role = roles.add(make_role("EDITOR"))
        assignments.add(RoleAssignment(user_id=42, role_id=role.id, is_active=False))

        result = await service.get_my_all_permissions(current_user)

        assert [a["is_active"] for a in result["role_assignments"]] == [False]
        assert [r["code"] for r in result["assigned_roles"]] == ["EDITOR"]

    async def test_other_users_assignments_are_excluded(
        self,
        service: RbacService,
        roles: FakeRoleRepository,
        assignments: FakeRoleAssignmentStore,
        current_user: User,
    ) -> None:
        role = roles.add(make_role("EDITOR"))
        assignments.add(RoleAssignment(user_id=99, role_id=role.id))

        result = await service.get_my_all_permissions(current_user)

        assert result["role_assignments"] == []
        assert result["assigned_roles"] == []

    async def test_user_with_nothing_gets_empty_collections(
        self, service: RbacService, current_user: User
    ) -> None:
        result = await service.get_my_all_permissions(current_user)

        assert result["role_assignments"] == []
        assert result["assigned_roles"] == []
        assert result["total_effective_permissions"] == 0
        assert result["effective_permissions"] == []


class TestMyFieldPermissions:
    async def test_returns_the_resolvers_field_map_for_the_resource(
        self, service: RbacService, resolver: FakePermissionResolver, current_user: User
    ) -> None:
        resolver.fields[(42, "users")] = {"salary": ["READ"], "email": ["READ", "UPDATE"]}
        resolver.fields[(42, "orders")] = {"total": ["READ"]}

        result = await service.get_my_field_permissions(current_user, "users")

        assert result == {
            "resource": "users",
            "fields": {"salary": ["READ"], "email": ["READ", "UPDATE"]},
        }

    async def test_resource_without_field_rules_has_no_fields(
        self, service: RbacService, current_user: User
    ) -> None:
        result = await service.get_my_field_permissions(current_user, "users")

        assert result == {"resource": "users", "fields": {}}


class TestListAuditLogs:
    @staticmethod
    def _entry(
        action: str, actor: str, resource: str, minutes_ago: int = 0
    ) -> AuditLog:
        return AuditLog(
            actor_username=actor,
            action=action,
            resource_type=resource,
            created_at=datetime.now(UTC) - timedelta(minutes=minutes_ago),
        )

    async def test_returns_entries_newest_first_with_paging_echo(
        self, service: RbacService, audit: FakeAuditLogRepository
    ) -> None:
        audit.seed(self._entry(AuditAction.ROLE_CREATED, "alice", "Role", minutes_ago=30))
        audit.seed(self._entry(AuditAction.ROLE_UPDATED, "alice", "Role", minutes_ago=5))

        result = await service.list_audit_logs()

        assert [e.action for e in result["logs"]] == ["ROLE_UPDATED", "ROLE_CREATED"]
        assert (result["total"], result["skip"], result["limit"]) == (2, 0, 50)

    async def test_filters_combine_for_both_the_page_and_the_total(
        self, service: RbacService, audit: FakeAuditLogRepository
    ) -> None:
        audit.seed(self._entry(AuditAction.ROLE_CREATED, "alice", "Role"))
        audit.seed(self._entry(AuditAction.ROLE_CREATED, "bob", "Role"))
        audit.seed(self._entry(AuditAction.PERMISSION_CREATED, "alice", "Permission"))

        result = await service.list_audit_logs(
            action="ROLE_CREATED", actor_username="alice", resource_type="Role"
        )

        assert len(result["logs"]) == 1
        assert result["total"] == 1

    async def test_total_counts_all_matches_not_just_the_requested_page(
        self, service: RbacService, audit: FakeAuditLogRepository
    ) -> None:
        for minutes_ago in range(5):
            audit.seed(
                self._entry(AuditAction.ROLE_CREATED, "alice", "Role", minutes_ago)
            )

        result = await service.list_audit_logs(skip=1, limit=2)

        assert len(result["logs"]) == 2
        assert result["total"] == 5
        assert (result["skip"], result["limit"]) == (1, 2)
