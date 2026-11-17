"""
PermissionRepositoryImpl tests, against a real database session.

The repository only creates and reads (there is no update or delete on the port),
so the tests cover: id / code lookup, `list_active` with its scope filter and
`(scope, resource)` ordering, and the entity <-> ORM mapping for every column.

`list_active` returns every active permission in the table, so assertions about
list contents are made over the rows this test created (identified by a per-test
token) rather than over the whole result.
"""

import secrets

from sqlalchemy.ext.asyncio import AsyncSession

from src.domain.entities.role import Permission
from src.infrastructure.database.repositories.permission_repository_impl import (
    PermissionRepositoryImpl,
)

_MISSING_ID = 999_999_999_999


def _token() -> str:
    return secrets.token_hex(5).upper()


def _permission(**overrides: object) -> Permission:
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
    return Permission(**defaults)  # type: ignore[arg-type]


class TestCreateAndGet:
    async def test_create_assigns_a_database_id_and_round_trips_every_field(
        self, db_session: AsyncSession
    ) -> None:
        repo = PermissionRepositoryImpl(db_session)

        created = await repo.create(
            _permission(
                code=f"users.salary.read.{_token()}",
                name="Read salary",
                description="Allows reading the salary field",
                scope="FIELD",
                resource="users.salary",
                action="UPDATE",
                is_active=False,
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
        assert fetched.name == "Read salary"
        assert fetched.description == "Allows reading the salary field"
        assert fetched.scope == "FIELD"
        assert fetched.resource == "users.salary"
        assert fetched.action == "UPDATE"
        assert fetched.is_active is False
        assert fetched.created_by == "alice"
        assert fetched.modified_by == "bob"
        assert fetched.created_date is not None
        assert fetched.modified_date is not None

    async def test_entity_defaults_are_persisted(self, db_session: AsyncSession) -> None:
        repo = PermissionRepositoryImpl(db_session)

        created = await repo.create(_permission())
        db_session.expire_all()
        fetched = await repo.get_by_id(created.id)

        assert fetched is not None
        assert fetched.description == ""
        assert fetched.is_active is True

    async def test_get_by_id_returns_none_for_a_missing_id(
        self, db_session: AsyncSession
    ) -> None:
        repo = PermissionRepositoryImpl(db_session)

        assert await repo.get_by_id(_MISSING_ID) is None


class TestGetByCode:
    async def test_finds_the_permission(self, db_session: AsyncSession) -> None:
        repo = PermissionRepositoryImpl(db_session)
        created = await repo.create(_permission())

        fetched = await repo.get_by_code(created.code)

        assert fetched is not None
        assert fetched.id == created.id

    async def test_returns_none_for_an_unknown_code(self, db_session: AsyncSession) -> None:
        repo = PermissionRepositoryImpl(db_session)

        assert await repo.get_by_code(f"missing.{_token()}") is None

    async def test_returns_inactive_permissions_too(self, db_session: AsyncSession) -> None:
        """Code lookup is for existence/grant checks, so it must not hide inactive rows."""
        repo = PermissionRepositoryImpl(db_session)
        created = await repo.create(_permission(is_active=False))

        fetched = await repo.get_by_code(created.code)

        assert fetched is not None
        assert fetched.is_active is False


class TestListActive:
    async def test_excludes_inactive_permissions(self, db_session: AsyncSession) -> None:
        repo = PermissionRepositoryImpl(db_session)
        active = await repo.create(_permission())
        inactive = await repo.create(_permission(is_active=False))

        listed_ids = {p.id for p in await repo.list_active()}

        assert active.id in listed_ids
        assert inactive.id not in listed_ids

    async def test_scope_filter_narrows_to_one_scope(self, db_session: AsyncSession) -> None:
        repo = PermissionRepositoryImpl(db_session)
        menu = await repo.create(_permission(scope="MENU"))
        api = await repo.create(_permission(scope="API"))
        field = await repo.create(_permission(scope="FIELD"))

        listed = await repo.list_active(scope="MENU")

        listed_ids = {p.id for p in listed}
        assert menu.id in listed_ids
        assert api.id not in listed_ids
        assert field.id not in listed_ids
        assert all(p.scope == "MENU" for p in listed)

    async def test_scope_filter_still_excludes_inactive(
        self, db_session: AsyncSession
    ) -> None:
        repo = PermissionRepositoryImpl(db_session)
        inactive = await repo.create(_permission(scope="MENU", is_active=False))

        listed_ids = {p.id for p in await repo.list_active(scope="MENU")}

        assert inactive.id not in listed_ids

    async def test_unknown_scope_returns_nothing(self, db_session: AsyncSession) -> None:
        repo = PermissionRepositoryImpl(db_session)
        await repo.create(_permission())

        assert await repo.list_active(scope="NOT_A_SCOPE") == []

    async def test_is_ordered_by_scope_then_resource(
        self, db_session: AsyncSession
    ) -> None:
        repo = PermissionRepositoryImpl(db_session)
        token = _token()
        # Created deliberately out of order. Resources differ at the first character so the
        # expected order does not depend on the database collation.
        created = [
            await repo.create(_permission(scope="MENU", resource=f"a{token}")),
            await repo.create(_permission(scope="API", resource=f"b{token}")),
            await repo.create(_permission(scope="API", resource=f"a{token}")),
            await repo.create(_permission(scope="FIELD", resource=f"c{token}")),
        ]
        mine = {p.id for p in created}

        listed = [p for p in await repo.list_active() if p.id in mine]

        assert [(p.scope, p.resource) for p in listed] == [
            ("API", f"a{token}"),
            ("API", f"b{token}"),
            ("FIELD", f"c{token}"),
            ("MENU", f"a{token}"),
        ]
