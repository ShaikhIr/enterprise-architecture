"""
Integration tests for UserDetailsRepositoryImpl.get_by_email, against a real DB.

The AuthManager unit tests pin down the Microsoft-SSO resolution logic against a
fake; this test pins down the SQL — specifically the case-insensitive email
lookup that links a Microsoft identity to the employee profile imported from the
Darwin AD service. Uses the `db_session` fixture (a transaction rolled back after
each test). Each test creates a throwaway `users` row to satisfy the
`user_details.user_id` foreign key.
"""

from uuid import uuid4

from sqlalchemy.ext.asyncio import AsyncSession

from src.domain.entities.user import User
from src.domain.entities.user_details import UserDetails
from src.infrastructure.database.repositories.user_details_repository_impl import (
    UserDetailsRepositoryImpl,
)
from src.infrastructure.database.repositories.user_repository_impl import (
    UserRepositoryImpl,
)


async def _make_user(db_session: AsyncSession) -> User:
    """Create a throwaway user to satisfy the user_details.user_id FK."""
    return await UserRepositoryImpl(db_session).create(
        User(
            username=f"emp-{uuid4().hex[:12]}",
            password_hash="x",
            created_by="t",
            modified_by="t",
        )
    )


class TestGetByEmail:
    async def test_finds_the_profile_carrying_that_email(
        self, db_session: AsyncSession
    ) -> None:
        repo = UserDetailsRepositoryImpl(db_session)
        user = await _make_user(db_session)
        await repo.create(
            UserDetails(
                user_id=user.id,
                employee_id="E1001",
                email="ada@example.com",
                created_by="t",
                modified_by="t",
            )
        )

        fetched = await repo.get_by_email("ada@example.com")

        assert fetched is not None
        assert fetched.user_id == user.id
        assert fetched.employee_id == "E1001"

    async def test_match_is_case_insensitive(self, db_session: AsyncSession) -> None:
        """Microsoft Graph may return a differently-cased mail than AD stored."""
        repo = UserDetailsRepositoryImpl(db_session)
        user = await _make_user(db_session)
        await repo.create(
            UserDetails(
                user_id=user.id,
                employee_id="E1001",
                email="Ada@Example.com",
                created_by="t",
                modified_by="t",
            )
        )

        assert await repo.get_by_email("ada@example.com") is not None
        assert await repo.get_by_email("ADA@EXAMPLE.COM") is not None

    async def test_leading_trailing_whitespace_is_ignored(
        self, db_session: AsyncSession
    ) -> None:
        repo = UserDetailsRepositoryImpl(db_session)
        user = await _make_user(db_session)
        await repo.create(
            UserDetails(
                user_id=user.id,
                employee_id="E1001",
                email="ada@example.com",
                created_by="t",
                modified_by="t",
            )
        )

        fetched = await repo.get_by_email("  ada@example.com  ")

        assert fetched is not None
        assert fetched.user_id == user.id

    async def test_returns_none_when_no_profile_has_that_email(
        self, db_session: AsyncSession
    ) -> None:
        repo = UserDetailsRepositoryImpl(db_session)
        user = await _make_user(db_session)
        await repo.create(
            UserDetails(
                user_id=user.id,
                employee_id="E1001",
                email="ada@example.com",
                created_by="t",
                modified_by="t",
            )
        )

        assert await repo.get_by_email("nobody@example.com") is None

    async def test_empty_email_returns_none_without_matching_blank_rows(
        self, db_session: AsyncSession
    ) -> None:
        """A blank query must not match profiles whose email was never set."""
        repo = UserDetailsRepositoryImpl(db_session)
        user = await _make_user(db_session)
        # employee_id only; email keeps its "" default.
        await repo.create(
            UserDetails(
                user_id=user.id, employee_id="E2002", created_by="t", modified_by="t"
            )
        )

        assert await repo.get_by_email("") is None
        assert await repo.get_by_email("   ") is None
