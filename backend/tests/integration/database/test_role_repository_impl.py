"""
RoleRepositoryImpl tests, against a real database session.

Covers the role CRUD surface (create / update / get by id and code), the list
queries (`list_active` with its tenant scoping and ordering, `list_by_ids`), the
role <-> permission link operations, and the entity <-> ORM mapping including the
nullable `tenant_id` / `parent_role_id` columns.

Permissions are loaded through a `selectin` relationship, which the session caches
on the role instance once loaded. Tests that grant or revoke a permission and then
read the role back call `db_session.expire_all()` first, so the read reflects the
database rather than a collection loaded earlier in the same session.

`list_active` returns every active role, so list assertions are made over the rows
a test created (identified by a per-test token), not over the whole result.
"""

import secrets

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from src.domain.entities.role import Permission, Role
from src.infrastructure.database.models.tenant_model import TenantModel
from src.infrastructure.database.repositories.permission_repository_impl import (
    PermissionRepositoryImpl,
)
from src.infrastructure.database.repositories.role_repository_impl import (
    RoleRepositoryImpl,
)

_MISSING_ID = 999_999_999_999


def _token() -> str:
    return secrets.token_hex(4).upper()


def _role(**overrides: object) -> Role:
    defaults: dict[str, object] = {
        "code": f"ROLE{_token()}",
        "name": f"Role {_token()}",
        "created_by": "test",
        "modified_by": "test",
    }
    defaults.update(overrides)
    return Role(**defaults)  # type: ignore[arg-type]


async def _make_tenant(session: AsyncSession) -> int:
    """Create a tenant row and return its id (roles.tenant_id is a foreign key)."""
    tenant = TenantModel(
        code=f"T{_token()}",
        name=f"Tenant {_token()}",
        created_by="test",
        modified_by="test",
    )
    session.add(tenant)
    await session.flush()
    return tenant.id


async def _make_permission(session: AsyncSession, **overrides: object) -> Permission:
    token = _token()
    defaults: dict[str, object] = {
        "code": f"perm.{token}",
        "name": f"Permission {token}",
        "scope": "API",
        "resource": f"res{token}",
        "action": "READ",
        "created_by": "test",
        "modified_by": "test",
    }
    defaults.update(overrides)
    return await PermissionRepositoryImpl(session).create(
        Permission(**defaults)  # type: ignore[arg-type]
    )


class TestCreateAndGet:
    async def test_create_round_trips_every_field(self, db_session: AsyncSession) -> None:
        repo = RoleRepositoryImpl(db_session)
        tenant_id = await _make_tenant(db_session)
        parent = await repo.create(_role())

        created = await repo.create(
            _role(
                description="Reviews things",
                is_system=True,
                is_active=False,
                tenant_id=tenant_id,
                parent_role_id=parent.id,
                created_by="alice",
                modified_by="bob",
            )
        )
        db_session.expire_all()  # force the read below to hit the row, not the identity map
        fetched = await repo.get_by_id(created.id)

        assert created.id > 0
        assert fetched is not None
        assert fetched.id == created.id
        assert fetched.code == created.code
        assert fetched.name == created.name
        assert fetched.description == "Reviews things"
        assert fetched.is_system is True
        assert fetched.is_active is False
        assert fetched.tenant_id == tenant_id
        assert fetched.parent_role_id == parent.id
        assert fetched.created_by == "alice"
        assert fetched.modified_by == "bob"
        assert fetched.created_date is not None
        assert fetched.modified_date is not None

    async def test_nullable_parent_columns_round_trip_as_none(
        self, db_session: AsyncSession
    ) -> None:
        repo = RoleRepositoryImpl(db_session)

        created = await repo.create(_role())
        db_session.expire_all()
        fetched = await repo.get_by_id(created.id)

        assert created.tenant_id is None
        assert created.parent_role_id is None
        assert fetched is not None
        assert fetched.tenant_id is None
        assert fetched.parent_role_id is None

    async def test_entity_defaults_are_persisted(self, db_session: AsyncSession) -> None:
        repo = RoleRepositoryImpl(db_session)

        created = await repo.create(_role())
        db_session.expire_all()
        fetched = await repo.get_by_id(created.id)

        assert fetched is not None
        assert fetched.description == ""
        assert fetched.is_system is False
        assert fetched.is_active is True

    async def test_create_returns_a_role_with_no_permissions(
        self, db_session: AsyncSession
    ) -> None:
        repo = RoleRepositoryImpl(db_session)

        created = await repo.create(_role())

        assert created.permissions == []

    async def test_get_by_id_returns_none_for_a_missing_id(
        self, db_session: AsyncSession
    ) -> None:
        repo = RoleRepositoryImpl(db_session)

        assert await repo.get_by_id(_MISSING_ID) is None

    async def test_get_by_code_finds_the_role(self, db_session: AsyncSession) -> None:
        repo = RoleRepositoryImpl(db_session)
        created = await repo.create(_role())

        fetched = await repo.get_by_code(created.code)

        assert fetched is not None
        assert fetched.id == created.id

    async def test_get_by_code_returns_none_for_an_unknown_code(
        self, db_session: AsyncSession
    ) -> None:
        repo = RoleRepositoryImpl(db_session)

        assert await repo.get_by_code(f"NOPE{_token()}") is None

    async def test_get_by_code_does_not_load_permissions(
        self, db_session: AsyncSession
    ) -> None:
        repo = RoleRepositoryImpl(db_session)
        role = await repo.create(_role())
        permission = await _make_permission(db_session)
        await repo.grant_permission(role.id, permission.id, "tester")
        db_session.expire_all()

        fetched = await repo.get_by_code(role.code)

        assert fetched is not None
        assert fetched.permissions == []


class TestGetByIdWithPermissions:
    async def test_permissions_are_omitted_unless_requested(
        self, db_session: AsyncSession
    ) -> None:
        repo = RoleRepositoryImpl(db_session)
        role = await repo.create(_role())
        permission = await _make_permission(db_session)
        await repo.grant_permission(role.id, permission.id, "tester")
        db_session.expire_all()

        without = await repo.get_by_id(role.id)
        db_session.expire_all()
        with_permissions = await repo.get_by_id(role.id, with_permissions=True)

        assert without is not None
        assert without.permissions == []
        assert with_permissions is not None
        assert [p.id for p in with_permissions.permissions] == [permission.id]

    async def test_loaded_permissions_carry_their_own_fields(
        self, db_session: AsyncSession
    ) -> None:
        repo = RoleRepositoryImpl(db_session)
        role = await repo.create(_role())
        permission = await _make_permission(
            db_session, scope="MENU", resource="dashboard", action="READ"
        )
        await repo.grant_permission(role.id, permission.id, "tester")
        db_session.expire_all()

        fetched = await repo.get_by_id(role.id, with_permissions=True)

        assert fetched is not None
        [loaded] = fetched.permissions
        assert loaded.code == permission.code
        assert loaded.scope == "MENU"
        assert loaded.resource == "dashboard"
        assert loaded.action == "READ"
        assert fetched.has_permission(permission.code) is True


class TestUpdate:
    async def test_update_persists_the_editable_fields(
        self, db_session: AsyncSession
    ) -> None:
        repo = RoleRepositoryImpl(db_session)
        parent = await repo.create(_role())
        created = await repo.create(_role())

        created.name = "Renamed"
        created.description = "New description"
        created.is_active = False
        created.parent_role_id = parent.id
        created.mark_modified("editor")
        updated = await repo.update(created)
        db_session.expire_all()
        fetched = await repo.get_by_id(created.id)

        assert updated.name == "Renamed"
        assert fetched is not None
        assert fetched.name == "Renamed"
        assert fetched.description == "New description"
        assert fetched.is_active is False
        assert fetched.parent_role_id == parent.id
        assert fetched.modified_by == "editor"

    async def test_update_can_clear_the_parent_role(self, db_session: AsyncSession) -> None:
        repo = RoleRepositoryImpl(db_session)
        parent = await repo.create(_role())
        created = await repo.create(_role(parent_role_id=parent.id))

        created.parent_role_id = None
        await repo.update(created)
        db_session.expire_all()
        fetched = await repo.get_by_id(created.id)

        assert fetched is not None
        assert fetched.parent_role_id is None

    async def test_update_leaves_code_system_flag_and_tenant_unchanged(
        self, db_session: AsyncSession
    ) -> None:
        """Those columns are fixed at creation; `update` must not forward them."""
        repo = RoleRepositoryImpl(db_session)
        tenant_id = await _make_tenant(db_session)
        created = await repo.create(_role(is_system=True, tenant_id=tenant_id))
        original_code = created.code

        created.code = f"CHANGED{_token()}"
        created.is_system = False
        created.tenant_id = None
        await repo.update(created)
        db_session.expire_all()
        fetched = await repo.get_by_id(created.id)

        assert fetched is not None
        assert fetched.code == original_code
        assert fetched.is_system is True
        assert fetched.tenant_id == tenant_id

    async def test_update_returns_the_role_with_its_permissions(
        self, db_session: AsyncSession
    ) -> None:
        repo = RoleRepositoryImpl(db_session)
        created = await repo.create(_role())
        permission = await _make_permission(db_session)
        await repo.grant_permission(created.id, permission.id, "tester")
        db_session.expire_all()

        created.name = "Renamed"
        updated = await repo.update(created)

        assert [p.id for p in updated.permissions] == [permission.id]

    async def test_update_of_a_missing_role_raises(self, db_session: AsyncSession) -> None:
        repo = RoleRepositoryImpl(db_session)

        with pytest.raises(ValueError, match="not found"):
            await repo.update(_role(id=_MISSING_ID))


class TestListActive:
    async def test_excludes_inactive_roles(self, db_session: AsyncSession) -> None:
        repo = RoleRepositoryImpl(db_session)
        active = await repo.create(_role())
        inactive = await repo.create(_role(is_active=False))

        listed_ids = {r.id for r in await repo.list_active()}

        assert active.id in listed_ids
        assert inactive.id not in listed_ids

    async def test_is_ordered_by_code(self, db_session: AsyncSession) -> None:
        repo = RoleRepositoryImpl(db_session)
        token = _token()
        # Created out of order. Codes differ only in the last character, so the expected
        # order does not depend on the database collation.
        created = [
            await repo.create(_role(code=f"R{token}C")),
            await repo.create(_role(code=f"R{token}A")),
            await repo.create(_role(code=f"R{token}B")),
        ]
        mine = {r.id for r in created}

        listed = [r.code for r in await repo.list_active() if r.id in mine]

        assert listed == [f"R{token}A", f"R{token}B", f"R{token}C"]

    async def test_without_a_tenant_returns_roles_of_every_tenant(
        self, db_session: AsyncSession
    ) -> None:
        repo = RoleRepositoryImpl(db_session)
        tenant_id = await _make_tenant(db_session)
        global_role = await repo.create(_role())
        tenant_role = await repo.create(_role(tenant_id=tenant_id))

        listed_ids = {r.id for r in await repo.list_active()}

        assert {global_role.id, tenant_role.id} <= listed_ids

    async def test_tenant_filter_returns_that_tenants_roles_plus_global_ones(
        self, db_session: AsyncSession
    ) -> None:
        repo = RoleRepositoryImpl(db_session)
        tenant_a = await _make_tenant(db_session)
        tenant_b = await _make_tenant(db_session)
        global_role = await repo.create(_role())
        role_a = await repo.create(_role(tenant_id=tenant_a))
        role_b = await repo.create(_role(tenant_id=tenant_b))

        listed_ids = {r.id for r in await repo.list_active(tenant_id=tenant_a)}

        assert global_role.id in listed_ids
        assert role_a.id in listed_ids
        assert role_b.id not in listed_ids

    async def test_tenant_filter_still_excludes_inactive_roles(
        self, db_session: AsyncSession
    ) -> None:
        repo = RoleRepositoryImpl(db_session)
        tenant_id = await _make_tenant(db_session)
        inactive = await repo.create(_role(tenant_id=tenant_id, is_active=False))

        listed_ids = {r.id for r in await repo.list_active(tenant_id=tenant_id)}

        assert inactive.id not in listed_ids

    async def test_listed_roles_carry_their_permissions(
        self, db_session: AsyncSession
    ) -> None:
        repo = RoleRepositoryImpl(db_session)
        role = await repo.create(_role())
        permission = await _make_permission(db_session)
        await repo.grant_permission(role.id, permission.id, "tester")
        db_session.expire_all()

        [listed] = [r for r in await repo.list_active() if r.id == role.id]

        assert [p.id for p in listed.permissions] == [permission.id]


class TestListByIds:
    async def test_empty_input_returns_an_empty_list(self, db_session: AsyncSession) -> None:
        repo = RoleRepositoryImpl(db_session)

        assert await repo.list_by_ids([]) == []

    async def test_returns_only_the_requested_roles(self, db_session: AsyncSession) -> None:
        repo = RoleRepositoryImpl(db_session)
        wanted_a = await repo.create(_role())
        wanted_b = await repo.create(_role())
        other = await repo.create(_role())

        listed = await repo.list_by_ids([wanted_a.id, wanted_b.id])

        listed_ids = {r.id for r in listed}
        assert listed_ids == {wanted_a.id, wanted_b.id}
        assert other.id not in listed_ids

    async def test_includes_inactive_roles(self, db_session: AsyncSession) -> None:
        """Unlike `list_active`, lookup by id does not filter on `is_active`."""
        repo = RoleRepositoryImpl(db_session)
        inactive = await repo.create(_role(is_active=False))

        listed = await repo.list_by_ids([inactive.id])

        assert [r.id for r in listed] == [inactive.id]

    async def test_unknown_ids_are_ignored(self, db_session: AsyncSession) -> None:
        repo = RoleRepositoryImpl(db_session)
        role = await repo.create(_role())

        listed = await repo.list_by_ids([role.id, _MISSING_ID])

        assert [r.id for r in listed] == [role.id]

    async def test_listed_roles_carry_their_permissions(
        self, db_session: AsyncSession
    ) -> None:
        repo = RoleRepositoryImpl(db_session)
        role = await repo.create(_role())
        permission = await _make_permission(db_session)
        await repo.grant_permission(role.id, permission.id, "tester")
        db_session.expire_all()

        [listed] = await repo.list_by_ids([role.id])

        assert [p.id for p in listed.permissions] == [permission.id]


class TestPermissionLinks:
    async def test_is_permission_granted_is_false_before_a_grant(
        self, db_session: AsyncSession
    ) -> None:
        repo = RoleRepositoryImpl(db_session)
        role = await repo.create(_role())
        permission = await _make_permission(db_session)

        assert await repo.is_permission_granted(role.id, permission.id) is False

    async def test_grant_then_is_permission_granted(self, db_session: AsyncSession) -> None:
        repo = RoleRepositoryImpl(db_session)
        role = await repo.create(_role())
        permission = await _make_permission(db_session)

        await repo.grant_permission(role.id, permission.id, "tester")

        assert await repo.is_permission_granted(role.id, permission.id) is True

    async def test_a_grant_is_specific_to_its_role_and_permission(
        self, db_session: AsyncSession
    ) -> None:
        repo = RoleRepositoryImpl(db_session)
        role = await repo.create(_role())
        other_role = await repo.create(_role())
        permission = await _make_permission(db_session)
        other_permission = await _make_permission(db_session)

        await repo.grant_permission(role.id, permission.id, "tester")

        assert await repo.is_permission_granted(other_role.id, permission.id) is False
        assert await repo.is_permission_granted(role.id, other_permission.id) is False

    async def test_granted_permissions_appear_on_the_role(
        self, db_session: AsyncSession
    ) -> None:
        repo = RoleRepositoryImpl(db_session)
        role = await repo.create(_role())
        first = await _make_permission(db_session)
        second = await _make_permission(db_session)
        await repo.grant_permission(role.id, first.id, "tester")
        await repo.grant_permission(role.id, second.id, "tester")
        db_session.expire_all()

        fetched = await repo.get_by_id(role.id, with_permissions=True)

        assert fetched is not None
        assert {p.id for p in fetched.permissions} == {first.id, second.id}

    async def test_revoke_removes_an_existing_grant_and_reports_true(
        self, db_session: AsyncSession
    ) -> None:
        repo = RoleRepositoryImpl(db_session)
        role = await repo.create(_role())
        permission = await _make_permission(db_session)
        await repo.grant_permission(role.id, permission.id, "tester")

        revoked = await repo.revoke_permission(role.id, permission.id)
        db_session.expire_all()
        fetched = await repo.get_by_id(role.id, with_permissions=True)

        assert revoked is True
        assert await repo.is_permission_granted(role.id, permission.id) is False
        assert fetched is not None
        assert fetched.permissions == []

    async def test_revoke_without_a_grant_reports_false(
        self, db_session: AsyncSession
    ) -> None:
        repo = RoleRepositoryImpl(db_session)
        role = await repo.create(_role())
        permission = await _make_permission(db_session)

        assert await repo.revoke_permission(role.id, permission.id) is False

    async def test_revoke_leaves_other_grants_in_place(
        self, db_session: AsyncSession
    ) -> None:
        repo = RoleRepositoryImpl(db_session)
        role = await repo.create(_role())
        kept = await _make_permission(db_session)
        dropped = await _make_permission(db_session)
        await repo.grant_permission(role.id, kept.id, "tester")
        await repo.grant_permission(role.id, dropped.id, "tester")

        await repo.revoke_permission(role.id, dropped.id)

        assert await repo.is_permission_granted(role.id, kept.id) is True
        assert await repo.is_permission_granted(role.id, dropped.id) is False

    async def test_a_permission_can_be_regranted_after_revocation(
        self, db_session: AsyncSession
    ) -> None:
        repo = RoleRepositoryImpl(db_session)
        role = await repo.create(_role())
        permission = await _make_permission(db_session)
        await repo.grant_permission(role.id, permission.id, "tester")
        await repo.revoke_permission(role.id, permission.id)

        await repo.grant_permission(role.id, permission.id, "tester")

        assert await repo.is_permission_granted(role.id, permission.id) is True
