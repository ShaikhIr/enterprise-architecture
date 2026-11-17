"""
Integration tests for RefreshTokenRepositoryImpl against a real database.

`mark_used` is the load-bearing one: it is one conditional UPDATE, and of two concurrent refreshes
of the same token exactly one may win. That is SQL behaviour, so it is tested here, not faked.
"""

import uuid
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from src.domain.entities.refresh_token import RefreshToken
from src.domain.entities.user import User
from src.infrastructure.database.repositories.refresh_token_repository_impl import (
    RefreshTokenRepositoryImpl,
)
from src.infrastructure.database.repositories.user_repository_impl import UserRepositoryImpl

NOW = datetime(2026, 11, 16, 12, 0, tzinfo=UTC)


def _token(user_id: int, *, family: str | None = None, **overrides: object) -> RefreshToken:
    fields: dict[str, object] = {
        "jti": uuid.uuid4().hex,
        "family_id": family or uuid.uuid4().hex,
        "user_id": user_id,
        "expires_at": NOW + timedelta(days=7),
    }
    fields.update(overrides)
    return RefreshToken(**fields)  # type: ignore[arg-type]


@pytest.fixture
async def user(db_session: AsyncSession) -> User:
    return await UserRepositoryImpl(db_session).create(
        User(username=f"rt-{uuid.uuid4().hex[:12]}", password_hash="x", is_validate_ad=False)
    )


@pytest.fixture
def repo(db_session: AsyncSession) -> RefreshTokenRepositoryImpl:
    return RefreshTokenRepositoryImpl(db_session)


class TestCreateAndGet:
    async def test_create_assigns_the_database_id(
        self, repo: RefreshTokenRepositoryImpl, user: User
    ) -> None:
        created = await repo.create(_token(user.id))

        assert created.id > 0

    async def test_every_field_round_trips(
        self, repo: RefreshTokenRepositoryImpl, user: User
    ) -> None:
        created = await repo.create(_token(user.id, jti="j-1", family_id="f-1"))

        loaded = await repo.get_by_jti("j-1")

        assert loaded is not None
        assert loaded.id == created.id
        assert loaded.jti == "j-1"
        assert loaded.family_id == "f-1"
        assert loaded.user_id == user.id
        assert loaded.expires_at == NOW + timedelta(days=7)

    async def test_unused_and_unrevoked_come_back_as_none(
        self, repo: RefreshTokenRepositoryImpl, user: User
    ) -> None:
        await repo.create(_token(user.id, jti="j-2"))

        loaded = await repo.get_by_jti("j-2")

        assert loaded is not None
        assert loaded.used_at is None
        assert loaded.revoked_at is None

    async def test_used_and_revoked_timestamps_round_trip(
        self, repo: RefreshTokenRepositoryImpl, user: User
    ) -> None:
        await repo.create(_token(user.id, jti="j-3", used_at=NOW, revoked_at=NOW))

        loaded = await repo.get_by_jti("j-3")

        assert loaded is not None
        assert loaded.used_at == NOW
        assert loaded.revoked_at == NOW

    async def test_an_unknown_jti_is_none(self, repo: RefreshTokenRepositoryImpl) -> None:
        assert await repo.get_by_jti("nope") is None


class TestMarkUsed:
    async def test_the_first_caller_wins(
        self, repo: RefreshTokenRepositoryImpl, user: User
    ) -> None:
        await repo.create(_token(user.id, jti="j-10"))

        assert await repo.mark_used("j-10", NOW) is True

    async def test_the_second_caller_loses(
        self, repo: RefreshTokenRepositoryImpl, user: User
    ) -> None:
        """The compare-and-set that tells a racing tab from a single refresh."""
        await repo.create(_token(user.id, jti="j-11"))

        first = await repo.mark_used("j-11", NOW)
        second = await repo.mark_used("j-11", NOW + timedelta(seconds=1))

        assert (first, second) == (True, False)

    async def test_the_winning_timestamp_is_kept(
        self, repo: RefreshTokenRepositoryImpl, user: User, db_session: AsyncSession
    ) -> None:
        await repo.create(_token(user.id, jti="j-12"))
        await repo.mark_used("j-12", NOW)
        await repo.mark_used("j-12", NOW + timedelta(hours=1))
        db_session.expire_all()

        loaded = await repo.get_by_jti("j-12")

        assert loaded is not None
        assert loaded.used_at == NOW

    async def test_a_revoked_token_cannot_be_spent(
        self, repo: RefreshTokenRepositoryImpl, user: User
    ) -> None:
        await repo.create(_token(user.id, jti="j-13", family_id="f-13"))
        await repo.revoke_family("f-13", NOW)

        assert await repo.mark_used("j-13", NOW) is False

    async def test_an_unknown_token_cannot_be_spent(self, repo: RefreshTokenRepositoryImpl) -> None:
        assert await repo.mark_used("nope", NOW) is False

    async def test_spending_one_token_leaves_its_siblings_unspent(
        self, repo: RefreshTokenRepositoryImpl, user: User, db_session: AsyncSession
    ) -> None:
        await repo.create(_token(user.id, jti="j-14a", family_id="f-14"))
        await repo.create(_token(user.id, jti="j-14b", family_id="f-14"))

        await repo.mark_used("j-14a", NOW)
        db_session.expire_all()

        sibling = await repo.get_by_jti("j-14b")
        assert sibling is not None
        assert sibling.used_at is None


class TestRevokeFamily:
    async def test_revokes_every_token_of_the_family(
        self, repo: RefreshTokenRepositoryImpl, user: User, db_session: AsyncSession
    ) -> None:
        await repo.create(_token(user.id, jti="j-20a", family_id="f-20"))
        await repo.create(_token(user.id, jti="j-20b", family_id="f-20"))

        await repo.revoke_family("f-20", NOW)
        db_session.expire_all()

        for jti in ("j-20a", "j-20b"):
            loaded = await repo.get_by_jti(jti)
            assert loaded is not None
            assert loaded.revoked_at == NOW

    async def test_leaves_other_families_alone(
        self, repo: RefreshTokenRepositoryImpl, user: User, db_session: AsyncSession
    ) -> None:
        await repo.create(_token(user.id, jti="j-21a", family_id="f-21a"))
        await repo.create(_token(user.id, jti="j-21b", family_id="f-21b"))

        await repo.revoke_family("f-21a", NOW)
        db_session.expire_all()

        other = await repo.get_by_jti("j-21b")
        assert other is not None
        assert other.revoked_at is None

    async def test_does_not_overwrite_an_earlier_revocation(
        self, repo: RefreshTokenRepositoryImpl, user: User, db_session: AsyncSession
    ) -> None:
        await repo.create(_token(user.id, jti="j-22", family_id="f-22"))
        await repo.revoke_family("f-22", NOW)

        await repo.revoke_family("f-22", NOW + timedelta(hours=1))
        db_session.expire_all()

        loaded = await repo.get_by_jti("j-22")
        assert loaded is not None
        assert loaded.revoked_at == NOW

    async def test_an_unknown_family_is_not_an_error(
        self, repo: RefreshTokenRepositoryImpl
    ) -> None:
        await repo.revoke_family("no-such-family", NOW)


class TestDeleteExpired:
    async def test_removes_only_tokens_expired_before_the_cutoff(
        self, repo: RefreshTokenRepositoryImpl, user: User
    ) -> None:
        await repo.create(_token(user.id, jti="old", expires_at=NOW - timedelta(days=3)))
        await repo.create(_token(user.id, jti="recent", expires_at=NOW - timedelta(hours=1)))
        await repo.create(_token(user.id, jti="live", expires_at=NOW + timedelta(days=1)))

        removed = await repo.delete_expired(NOW - timedelta(days=1))

        assert removed == 1
        assert await repo.get_by_jti("old") is None
        assert await repo.get_by_jti("recent") is not None
        assert await repo.get_by_jti("live") is not None

    async def test_returns_zero_when_nothing_expired(
        self, repo: RefreshTokenRepositoryImpl, user: User
    ) -> None:
        await repo.create(_token(user.id))

        assert await repo.delete_expired(NOW - timedelta(days=30)) == 0


class TestUserDeletion:
    async def test_deleting_a_user_removes_their_tokens(
        self, repo: RefreshTokenRepositoryImpl, user: User, db_session: AsyncSession
    ) -> None:
        await repo.create(_token(user.id, jti="j-30"))

        await UserRepositoryImpl(db_session).delete(user.id)
        db_session.expire_all()

        assert await repo.get_by_jti("j-30") is None
