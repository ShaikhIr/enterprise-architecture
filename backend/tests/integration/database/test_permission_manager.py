"""
PermissionManager tests, against a real database session.

`PermissionManager` is not written against a repository port — it queries
`RoleAssignmentModel`/`RoleModel` directly with `selectinload`, which is why it
takes an `AsyncSession` rather than an interface, unlike every application
service in `tests/unit/application/`. That makes an in-memory fake impractical
(there is no port to fake), so this suite seeds real rows through `db_session`
and calls the manager's methods directly — a repository-level integration test,
the same shape `tests/integration/database/` is reserved for.

Before this file, `PermissionManager` was only exercised indirectly through API
integration tests asserting 200/403, which cannot distinguish "resolved the
right permissions" from "resolved a merely-sufficient set".
"""

from uuid import uuid4

from sqlalchemy.ext.asyncio import AsyncSession

from src.domain.entities.role import PermissionScope
from src.infrastructure.database.models.role_model import (
    PermissionModel,
    RoleAssignmentModel,
    RoleModel,
    RolePermissionModel,
)
from src.infrastructure.database.models.tenant_model import TenantModel
from src.infrastructure.database.models.user_model import UserModel
from src.infrastructure.security.permission_manager import PermissionManager


async def _make_user(session: AsyncSession) -> UserModel:
    user = UserModel(
        id=uuid4(),
        username=f"user-{uuid4().hex[:8]}",
        password_hash="hash",
        is_active=True,
        is_blocked=False,
        is_validate_ad=False,
        created_by="test",
        modified_by="test",
    )
    session.add(user)
    await session.flush()
    return user


async def _make_role(
    session: AsyncSession,
    *,
    code: str,
    parent_role_id: object | None = None,
    tenant_id: object | None = None,
    is_active: bool = True,
) -> RoleModel:
    role = RoleModel(
        id=uuid4(),
        code=code,
        name=code,
        is_system=False,
        is_active=is_active,
        parent_role_id=parent_role_id,
        tenant_id=tenant_id,
        created_by="test",
        modified_by="test",
    )
    session.add(role)
    await session.flush()
    return role


async def _make_permission(
    session: AsyncSession,
    *,
    code: str,
    scope: str,
    resource: str,
    action: str,
    is_active: bool = True,
) -> PermissionModel:
    permission = PermissionModel(
        id=uuid4(),
        code=code,
        name=code,
        scope=scope,
        resource=resource,
        action=action,
        is_active=is_active,
        created_by="test",
        modified_by="test",
    )
    session.add(permission)
    await session.flush()
    return permission


async def _grant(session: AsyncSession, role: RoleModel, permission: PermissionModel) -> None:
    session.add(
        RolePermissionModel(
            id=uuid4(),
            role_id=role.id,
            permission_id=permission.id,
            created_by="test",
            modified_by="test",
        )
    )
    await session.flush()


async def _assign(
    session: AsyncSession,
    user: UserModel,
    role: RoleModel,
    *,
    tenant_id: object | None = None,
    is_active: bool = True,
) -> None:
    session.add(
        RoleAssignmentModel(
            id=uuid4(),
            user_id=user.id,
            role_id=role.id,
            tenant_id=tenant_id,
            is_active=is_active,
            created_by="test",
            modified_by="test",
        )
    )
    await session.flush()


class TestGetUserPermissions:
    async def test_resolves_permissions_from_an_assigned_role(
        self, db_session: AsyncSession
    ) -> None:
        manager = PermissionManager(db_session)
        user = await _make_user(db_session)
        role = await _make_role(db_session, code="VIEWER")
        permission = await _make_permission(
            db_session, code="countries.list", scope="API", resource="countries", action="READ"
        )
        await _grant(db_session, role, permission)
        await _assign(db_session, user, role)

        permissions = await manager.get_user_permissions(user.id)

        assert {p.code for p in permissions} == {"countries.list"}

    async def test_user_with_no_role_assignment_has_no_permissions(
        self, db_session: AsyncSession
    ) -> None:
        manager = PermissionManager(db_session)
        user = await _make_user(db_session)

        permissions = await manager.get_user_permissions(user.id)

        assert permissions == []

    async def test_permissions_from_multiple_roles_are_unioned(
        self, db_session: AsyncSession
    ) -> None:
        manager = PermissionManager(db_session)
        user = await _make_user(db_session)
        role_a = await _make_role(db_session, code="ROLE_A")
        role_b = await _make_role(db_session, code="ROLE_B")
        perm_a = await _make_permission(
            db_session, code="a.read", scope="API", resource="a", action="READ"
        )
        perm_b = await _make_permission(
            db_session, code="b.read", scope="API", resource="b", action="READ"
        )
        await _grant(db_session, role_a, perm_a)
        await _grant(db_session, role_b, perm_b)
        await _assign(db_session, user, role_a)
        await _assign(db_session, user, role_b)

        permissions = await manager.get_user_permissions(user.id)

        assert {p.code for p in permissions} == {"a.read", "b.read"}

    async def test_permission_shared_by_two_roles_is_not_duplicated(
        self, db_session: AsyncSession
    ) -> None:
        manager = PermissionManager(db_session)
        user = await _make_user(db_session)
        role_a = await _make_role(db_session, code="ROLE_A")
        role_b = await _make_role(db_session, code="ROLE_B")
        shared = await _make_permission(
            db_session, code="shared.read", scope="API", resource="shared", action="READ"
        )
        await _grant(db_session, role_a, shared)
        await _grant(db_session, role_b, shared)
        await _assign(db_session, user, role_a)
        await _assign(db_session, user, role_b)

        permissions = await manager.get_user_permissions(user.id)

        assert len(permissions) == 1

    async def test_inactive_role_assignment_is_ignored(self, db_session: AsyncSession) -> None:
        manager = PermissionManager(db_session)
        user = await _make_user(db_session)
        role = await _make_role(db_session, code="VIEWER")
        permission = await _make_permission(
            db_session, code="countries.list", scope="API", resource="countries", action="READ"
        )
        await _grant(db_session, role, permission)
        await _assign(db_session, user, role, is_active=False)

        permissions = await manager.get_user_permissions(user.id)

        assert permissions == []

    async def test_inactive_role_grants_nothing_even_if_assigned(
        self, db_session: AsyncSession
    ) -> None:
        manager = PermissionManager(db_session)
        user = await _make_user(db_session)
        role = await _make_role(db_session, code="RETIRED", is_active=False)
        permission = await _make_permission(
            db_session, code="countries.list", scope="API", resource="countries", action="READ"
        )
        await _grant(db_session, role, permission)
        await _assign(db_session, user, role)

        permissions = await manager.get_user_permissions(user.id)

        assert permissions == []

    async def test_inactive_permission_is_excluded(self, db_session: AsyncSession) -> None:
        manager = PermissionManager(db_session)
        user = await _make_user(db_session)
        role = await _make_role(db_session, code="VIEWER")
        permission = await _make_permission(
            db_session,
            code="countries.list",
            scope="API",
            resource="countries",
            action="READ",
            is_active=False,
        )
        await _grant(db_session, role, permission)
        await _assign(db_session, user, role)

        permissions = await manager.get_user_permissions(user.id)

        assert permissions == []

    async def test_scope_filter_narrows_the_result(self, db_session: AsyncSession) -> None:
        manager = PermissionManager(db_session)
        user = await _make_user(db_session)
        role = await _make_role(db_session, code="MIXED")
        menu_perm = await _make_permission(
            db_session, code="menu.users", scope="MENU", resource="users", action="READ"
        )
        api_perm = await _make_permission(
            db_session, code="users.list", scope="API", resource="users", action="READ"
        )
        await _grant(db_session, role, menu_perm)
        await _grant(db_session, role, api_perm)
        await _assign(db_session, user, role)

        menu_only = await manager.get_user_permissions(user.id, scope=PermissionScope.MENU)

        assert {p.code for p in menu_only} == {"menu.users"}

    async def test_parent_role_permissions_are_inherited(self, db_session: AsyncSession) -> None:
        manager = PermissionManager(db_session)
        user = await _make_user(db_session)
        parent = await _make_role(db_session, code="PARENT")
        parent_perm = await _make_permission(
            db_session, code="parent.read", scope="API", resource="parent", action="READ"
        )
        await _grant(db_session, parent, parent_perm)
        child = await _make_role(db_session, code="CHILD", parent_role_id=parent.id)
        child_perm = await _make_permission(
            db_session, code="child.read", scope="API", resource="child", action="READ"
        )
        await _grant(db_session, child, child_perm)
        await _assign(db_session, user, child)

        permissions = await manager.get_user_permissions(user.id)

        assert {p.code for p in permissions} == {"parent.read", "child.read"}

    async def test_inactive_parent_role_contributes_nothing(
        self, db_session: AsyncSession
    ) -> None:
        manager = PermissionManager(db_session)
        user = await _make_user(db_session)
        parent = await _make_role(db_session, code="PARENT", is_active=False)
        parent_perm = await _make_permission(
            db_session, code="parent.read", scope="API", resource="parent", action="READ"
        )
        await _grant(db_session, parent, parent_perm)
        child = await _make_role(db_session, code="CHILD", parent_role_id=parent.id)
        child_perm = await _make_permission(
            db_session, code="child.read", scope="API", resource="child", action="READ"
        )
        await _grant(db_session, child, child_perm)
        await _assign(db_session, user, child)

        permissions = await manager.get_user_permissions(user.id)

        assert {p.code for p in permissions} == {"child.read"}

    async def test_tenant_scoped_assignment_is_included_when_tenant_matches(
        self, db_session: AsyncSession
    ) -> None:
        manager = PermissionManager(db_session)
        user = await _make_user(db_session)
        tenant = TenantModel(
            id=uuid4(), code="acme", name="Acme", is_active=True,
            created_by="test", modified_by="test",
        )
        db_session.add(tenant)
        await db_session.flush()
        role = await _make_role(db_session, code="TENANT_ROLE")
        permission = await _make_permission(
            db_session, code="tenant.read", scope="API", resource="tenant", action="READ"
        )
        await _grant(db_session, role, permission)
        await _assign(db_session, user, role, tenant_id=tenant.id)

        permissions = await manager.get_user_permissions(user.id, tenant_id=tenant.id)

        assert {p.code for p in permissions} == {"tenant.read"}

    async def test_global_role_is_visible_alongside_a_tenant_filter(
        self, db_session: AsyncSession
    ) -> None:
        """A tenant_id filter must not hide the caller's global (tenant_id=NULL) roles."""
        manager = PermissionManager(db_session)
        user = await _make_user(db_session)
        tenant = TenantModel(
            id=uuid4(), code="acme", name="Acme", is_active=True,
            created_by="test", modified_by="test",
        )
        db_session.add(tenant)
        await db_session.flush()
        global_role = await _make_role(db_session, code="GLOBAL_ROLE")
        global_perm = await _make_permission(
            db_session, code="global.read", scope="API", resource="global", action="READ"
        )
        await _grant(db_session, global_role, global_perm)
        await _assign(db_session, user, global_role, tenant_id=None)

        permissions = await manager.get_user_permissions(user.id, tenant_id=tenant.id)

        assert {p.code for p in permissions} == {"global.read"}

    async def test_another_tenants_assignment_is_excluded(
        self, db_session: AsyncSession
    ) -> None:
        manager = PermissionManager(db_session)
        user = await _make_user(db_session)
        tenant_a = TenantModel(
            id=uuid4(), code="a", name="A", is_active=True,
            created_by="test", modified_by="test",
        )
        tenant_b = TenantModel(
            id=uuid4(), code="b", name="B", is_active=True,
            created_by="test", modified_by="test",
        )
        db_session.add_all([tenant_a, tenant_b])
        await db_session.flush()
        role = await _make_role(db_session, code="TENANT_ROLE")
        permission = await _make_permission(
            db_session, code="tenant.read", scope="API", resource="tenant", action="READ"
        )
        await _grant(db_session, role, permission)
        await _assign(db_session, user, role, tenant_id=tenant_a.id)

        permissions = await manager.get_user_permissions(user.id, tenant_id=tenant_b.id)

        assert permissions == []


class TestHasPermission:
    async def test_true_when_the_code_is_granted(self, db_session: AsyncSession) -> None:
        manager = PermissionManager(db_session)
        user = await _make_user(db_session)
        role = await _make_role(db_session, code="VIEWER")
        permission = await _make_permission(
            db_session, code="countries.list", scope="API", resource="countries", action="READ"
        )
        await _grant(db_session, role, permission)
        await _assign(db_session, user, role)

        assert await manager.has_permission(user.id, "countries.list") is True

    async def test_false_when_the_code_is_not_granted(self, db_session: AsyncSession) -> None:
        manager = PermissionManager(db_session)
        user = await _make_user(db_session)

        assert await manager.has_permission(user.id, "countries.list") is False


class TestHasApiAccess:
    async def test_true_for_the_granted_resource_action_pair(
        self, db_session: AsyncSession
    ) -> None:
        manager = PermissionManager(db_session)
        user = await _make_user(db_session)
        role = await _make_role(db_session, code="EDITOR")
        permission = await _make_permission(
            db_session, code="countries.create", scope="API", resource="countries", action="CREATE"
        )
        await _grant(db_session, role, permission)
        await _assign(db_session, user, role)

        assert await manager.has_api_access(user.id, "countries", "CREATE") is True

    async def test_false_for_a_different_action_on_the_same_resource(
        self, db_session: AsyncSession
    ) -> None:
        manager = PermissionManager(db_session)
        user = await _make_user(db_session)
        role = await _make_role(db_session, code="VIEWER")
        permission = await _make_permission(
            db_session, code="countries.list", scope="API", resource="countries", action="READ"
        )
        await _grant(db_session, role, permission)
        await _assign(db_session, user, role)

        assert await manager.has_api_access(user.id, "countries", "DELETE") is False

    async def test_menu_scope_permissions_do_not_grant_api_access(
        self, db_session: AsyncSession
    ) -> None:
        """A MENU permission on the same resource string must not leak into API checks."""
        manager = PermissionManager(db_session)
        user = await _make_user(db_session)
        role = await _make_role(db_session, code="VIEWER")
        permission = await _make_permission(
            db_session, code="menu.countries", scope="MENU", resource="countries", action="READ"
        )
        await _grant(db_session, role, permission)
        await _assign(db_session, user, role)

        assert await manager.has_api_access(user.id, "countries", "READ") is False


class TestGetMenuPermissions:
    async def test_returns_distinct_resource_keys(self, db_session: AsyncSession) -> None:
        manager = PermissionManager(db_session)
        user = await _make_user(db_session)
        role = await _make_role(db_session, code="VIEWER")
        dashboard = await _make_permission(
            db_session, code="menu.dashboard", scope="MENU", resource="dashboard", action="READ"
        )
        users_menu = await _make_permission(
            db_session, code="menu.users", scope="MENU", resource="users", action="READ"
        )
        await _grant(db_session, role, dashboard)
        await _grant(db_session, role, users_menu)
        await _assign(db_session, user, role)

        menu_keys = await manager.get_menu_permissions(user.id)

        assert set(menu_keys) == {"dashboard", "users"}

    async def test_api_scope_permissions_are_excluded(self, db_session: AsyncSession) -> None:
        manager = PermissionManager(db_session)
        user = await _make_user(db_session)
        role = await _make_role(db_session, code="VIEWER")
        api_perm = await _make_permission(
            db_session, code="users.list", scope="API", resource="users", action="READ"
        )
        await _grant(db_session, role, api_perm)
        await _assign(db_session, user, role)

        menu_keys = await manager.get_menu_permissions(user.id)

        assert menu_keys == []


class TestGetFieldPermissions:
    async def test_splits_the_dotted_resource_into_field_name(
        self, db_session: AsyncSession
    ) -> None:
        manager = PermissionManager(db_session)
        user = await _make_user(db_session)
        role = await _make_role(db_session, code="HR")
        salary_read = await _make_permission(
            db_session,
            code="users.salary.read",
            scope="FIELD",
            resource="users.salary",
            action="READ",
        )
        await _grant(db_session, role, salary_read)
        await _assign(db_session, user, role)

        fields = await manager.get_field_permissions(user.id, "users")

        assert fields == {"salary": ["READ"]}

    async def test_a_field_can_carry_multiple_actions(self, db_session: AsyncSession) -> None:
        manager = PermissionManager(db_session)
        user = await _make_user(db_session)
        role = await _make_role(db_session, code="HR")
        read_perm = await _make_permission(
            db_session,
            code="users.email.read",
            scope="FIELD",
            resource="users.email",
            action="READ",
        )
        update_perm = await _make_permission(
            db_session,
            code="users.email.update",
            scope="FIELD",
            resource="users.email",
            action="UPDATE",
        )
        await _grant(db_session, role, read_perm)
        await _grant(db_session, role, update_perm)
        await _assign(db_session, user, role)

        fields = await manager.get_field_permissions(user.id, "users")

        assert set(fields["email"]) == {"READ", "UPDATE"}

    async def test_a_different_resources_field_permissions_are_not_returned(
        self, db_session: AsyncSession
    ) -> None:
        manager = PermissionManager(db_session)
        user = await _make_user(db_session)
        role = await _make_role(db_session, code="HR")
        other_resource = await _make_permission(
            db_session,
            code="employees.salary.read",
            scope="FIELD",
            resource="employees.salary",
            action="READ",
        )
        await _grant(db_session, role, other_resource)
        await _assign(db_session, user, role)

        fields = await manager.get_field_permissions(user.id, "users")

        assert fields == {}

    async def test_no_grants_returns_an_empty_mapping(self, db_session: AsyncSession) -> None:
        manager = PermissionManager(db_session)
        user = await _make_user(db_session)

        fields = await manager.get_field_permissions(user.id, "users")

        assert fields == {}
