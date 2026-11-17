"""
UserRepositoryImpl tests, against a real database session.

`users` is not a code-keyed master, so this repository is a standalone port with
its own small CRUD surface: get by id / username, create, update, delete, a
username existence check and an (unordered) paginated list. The tests pin down
that surface, including the entity <-> ORM mapping for every column.

Every username is made unique per call so the tests stay independent of whatever
else already sits in the test database.
"""

import secrets

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from src.domain.entities.user import User
from src.infrastructure.database.repositories.user_repository_impl import (
    UserRepositoryImpl,
)

_MISSING_ID = 999_999_999_999


def _user(**overrides: object) -> User:
    defaults: dict[str, object] = {
        "username": f"user-{secrets.token_hex(6)}",
        "password_hash": "hash-1",
        "created_by": "creator",
        "modified_by": "creator",
    }
    defaults.update(overrides)
    return User(**defaults)  # type: ignore[arg-type]


class TestCreateAndGet:
    async def test_create_assigns_a_database_id_and_round_trips_every_field(
        self, db_session: AsyncSession
    ) -> None:
        repo = UserRepositoryImpl(db_session)
        username = f"user-{secrets.token_hex(6)}"

        created = await repo.create(
            _user(
                username=username,
                password_hash="bcrypt-hash",
                is_active=False,
                is_blocked=True,
                is_validate_ad=False,
                created_by="alice",
                modified_by="bob",
            )
        )
        db_session.expire_all()  # force the read below to hit the row, not the identity map
        fetched = await repo.get_by_id(created.id)

        assert created.id > 0
        assert fetched is not None
        assert fetched.id == created.id
        assert fetched.username == username
        assert fetched.password_hash == "bcrypt-hash"
        assert fetched.is_active is False
        assert fetched.is_blocked is True
        assert fetched.is_validate_ad is False
        assert fetched.created_by == "alice"
        assert fetched.modified_by == "bob"
        assert fetched.created_date is not None
        assert fetched.modified_date is not None

    async def test_entity_defaults_are_persisted(self, db_session: AsyncSession) -> None:
        repo = UserRepositoryImpl(db_session)

        created = await repo.create(_user())
        db_session.expire_all()
        fetched = await repo.get_by_id(created.id)

        assert fetched is not None
        assert fetched.is_active is True
        assert fetched.is_blocked is False
        assert fetched.is_validate_ad is True

    async def test_get_by_id_returns_none_for_a_missing_id(
        self, db_session: AsyncSession
    ) -> None:
        repo = UserRepositoryImpl(db_session)

        assert await repo.get_by_id(_MISSING_ID) is None

    async def test_two_creates_get_distinct_ids(self, db_session: AsyncSession) -> None:
        repo = UserRepositoryImpl(db_session)

        first = await repo.create(_user())
        second = await repo.create(_user())

        assert first.id != second.id


class TestGetByUsername:
    async def test_finds_the_user(self, db_session: AsyncSession) -> None:
        repo = UserRepositoryImpl(db_session)
        created = await repo.create(_user(username=f"find-{secrets.token_hex(6)}"))

        fetched = await repo.get_by_username(created.username)

        assert fetched is not None
        assert fetched.id == created.id

    async def test_returns_none_when_no_user_has_that_username(
        self, db_session: AsyncSession
    ) -> None:
        repo = UserRepositoryImpl(db_session)

        assert await repo.get_by_username(f"nobody-{secrets.token_hex(6)}") is None

    async def test_match_is_exact_and_case_sensitive(
        self, db_session: AsyncSession
    ) -> None:
        """The lookup compares with `=`; folding case is the caller's job."""
        repo = UserRepositoryImpl(db_session)
        created = await repo.create(_user(username=f"MixedCase-{secrets.token_hex(6)}"))

        assert await repo.get_by_username(created.username.lower()) is None


class TestExistsByUsername:
    async def test_true_for_an_existing_username(self, db_session: AsyncSession) -> None:
        repo = UserRepositoryImpl(db_session)
        created = await repo.create(_user())

        assert await repo.exists_by_username(created.username) is True

    async def test_false_for_an_unused_username(self, db_session: AsyncSession) -> None:
        repo = UserRepositoryImpl(db_session)

        assert await repo.exists_by_username(f"free-{secrets.token_hex(6)}") is False


class TestUpdate:
    async def test_update_persists_every_mutable_field(
        self, db_session: AsyncSession
    ) -> None:
        repo = UserRepositoryImpl(db_session)
        created = await repo.create(_user())
        new_username = f"renamed-{secrets.token_hex(6)}"

        created.username = new_username
        created.password_hash = "hash-2"
        created.is_active = False
        created.is_blocked = True
        created.is_validate_ad = False
        created.mark_modified("editor")
        updated = await repo.update(created)
        db_session.expire_all()
        fetched = await repo.get_by_id(created.id)

        assert updated.username == new_username
        assert fetched is not None
        assert fetched.username == new_username
        assert fetched.password_hash == "hash-2"
        assert fetched.is_active is False
        assert fetched.is_blocked is True
        assert fetched.is_validate_ad is False
        assert fetched.modified_by == "editor"

    async def test_update_does_not_touch_created_by(self, db_session: AsyncSession) -> None:
        repo = UserRepositoryImpl(db_session)
        created = await repo.create(_user(created_by="original"))

        created.created_by = "tampered"
        created.mark_modified("editor")
        await repo.update(created)
        db_session.expire_all()
        fetched = await repo.get_by_id(created.id)

        assert fetched is not None
        assert fetched.created_by == "original"

    async def test_update_of_a_missing_user_raises(self, db_session: AsyncSession) -> None:
        repo = UserRepositoryImpl(db_session)

        with pytest.raises(ValueError, match="not found"):
            await repo.update(_user(id=_MISSING_ID))

    async def test_update_is_visible_to_username_lookups(
        self, db_session: AsyncSession
    ) -> None:
        repo = UserRepositoryImpl(db_session)
        created = await repo.create(_user())
        old_username = created.username
        created.username = f"renamed-{secrets.token_hex(6)}"
        await repo.update(created)

        assert await repo.exists_by_username(old_username) is False
        assert await repo.exists_by_username(created.username) is True


class TestDelete:
    async def test_delete_removes_the_row(self, db_session: AsyncSession) -> None:
        repo = UserRepositoryImpl(db_session)
        created = await repo.create(_user())

        await repo.delete(created.id)

        assert await repo.get_by_id(created.id) is None
        assert await repo.exists_by_username(created.username) is False

    async def test_delete_of_a_missing_user_is_silent(
        self, db_session: AsyncSession
    ) -> None:
        repo = UserRepositoryImpl(db_session)

        await repo.delete(_MISSING_ID)  # must not raise

    async def test_delete_leaves_other_users_alone(self, db_session: AsyncSession) -> None:
        repo = UserRepositoryImpl(db_session)
        keep = await repo.create(_user())
        drop = await repo.create(_user())

        await repo.delete(drop.id)

        assert await repo.get_by_id(keep.id) is not None


class TestListAll:
    """`list_all` has no ORDER BY, so these assert membership and sizes, not order."""

    async def test_returns_created_users(self, db_session: AsyncSession) -> None:
        repo = UserRepositoryImpl(db_session)
        created = [await repo.create(_user()) for _ in range(3)]

        rows = await repo.list_all(limit=100_000)

        listed_ids = {u.id for u in rows}
        assert {u.id for u in created} <= listed_ids

    async def test_limit_caps_the_page_size(self, db_session: AsyncSession) -> None:
        repo = UserRepositoryImpl(db_session)
        for _ in range(3):
            await repo.create(_user())

        rows = await repo.list_all(skip=0, limit=2)

        assert len(rows) == 2

    async def test_skip_pages_past_the_earlier_rows(self, db_session: AsyncSession) -> None:
        repo = UserRepositoryImpl(db_session)
        for _ in range(3):
            await repo.create(_user())
        everything = await repo.list_all(limit=100_000)

        first_page = await repo.list_all(skip=0, limit=2)
        second_page = await repo.list_all(skip=2, limit=100_000)

        assert {u.id for u in first_page}.isdisjoint({u.id for u in second_page})
        assert len(first_page) + len(second_page) == len(everything)

    async def test_skip_beyond_the_end_returns_nothing(
        self, db_session: AsyncSession
    ) -> None:
        repo = UserRepositoryImpl(db_session)
        await repo.create(_user())
        everything = await repo.list_all(limit=100_000)

        assert await repo.list_all(skip=len(everything), limit=10) == []
