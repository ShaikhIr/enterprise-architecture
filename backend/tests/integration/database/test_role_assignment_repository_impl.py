"""
RoleAssignmentRepositoryImpl tests, against a real database session.

`role_assignments` links a user to a role with an optional tenant. The tests cover
the lookups (active vs. all, per user), the join-backed
`list_active_user_ids_for_role` that filters out unusable accounts, the two
deactivation paths, and the entity <-> ORM mapping including the nullable
`tenant_id`.

Each test builds its own users and roles (unique per call) because both are
foreign keys of the assignment.
"""

import secrets

from sqlalchemy.ext.asyncio import AsyncSession

from src.domain.entities.role import Role, RoleAssignment
from src.domain.entities.user import User
from src.infrastructure.database.models.tenant_model import TenantModel
from src.infrastructure.database.repositories.role_assignment_repository_impl import (
    RoleAssignmentRepositoryImpl,
)
from src.infrastructure.database.repositories.role_repository_impl import (
    RoleRepositoryImpl,
)
from src.infrastructure.database.repositories.user_repository_impl import (
    UserRepositoryImpl,
)

_MISSING_ID = 999_999_999_999


def _token() -> str:
    return secrets.token_hex(4).upper()


async def _make_user(session: AsyncSession, **overrides: object) -> User:
    defaults: dict[str, object] = {
        "username": f"user-{_token()}",
        "password_hash": "x",
        "created_by": "test",
        "modified_by": "test",
    }
    defaults.update(overrides)
    return await UserRepositoryImpl(session).create(User(**defaults))  # type: ignore[arg-type]


async def _make_role(session: AsyncSession) -> Role:
    return await RoleRepositoryImpl(session).create(
        Role(
            code=f"ROLE{_token()}",
            name=f"Role {_token()}",
            created_by="test",
            modified_by="test",
        )
    )


async def _make_tenant(session: AsyncSession) -> int:
    tenant = TenantModel(
        code=f"T{_token()}",
        name=f"Tenant {_token()}",
        created_by="test",
        modified_by="test",
    )
    session.add(tenant)
    await session.flush()
    return tenant.id


def _assignment(user_id: int, role_id: int, **overrides: object) -> RoleAssignment:
    defaults: dict[str, object] = {
        "user_id": user_id,
        "role_id": role_id,
        "created_by": "test",
        "modified_by": "test",
    }
    defaults.update(overrides)
    return RoleAssignment(**defaults)  # type: ignore[arg-type]


class TestCreate:
    async def test_create_assigns_a_database_id_and_round_trips_every_field(
        self, db_session: AsyncSession
    ) -> None:
        repo = RoleAssignmentRepositoryImpl(db_session)
        user = await _make_user(db_session)
        role = await _make_role(db_session)
        tenant_id = await _make_tenant(db_session)

        created = await repo.create(
            _assignment(
                user.id,
                role.id,
                tenant_id=tenant_id,
                is_active=False,
                created_by="alice",
                modified_by="bob",
            )
        )
        db_session.expire_all()  # force the read below to hit the row, not the identity map
        [fetched] = await repo.list_for_user(user.id)

        assert created.id > 0
        assert fetched.id == created.id
        assert fetched.user_id == user.id
        assert fetched.role_id == role.id
        assert fetched.tenant_id == tenant_id
        assert fetched.is_active is False
        assert fetched.created_by == "alice"
        assert fetched.modified_by == "bob"
        assert fetched.created_date is not None
        assert fetched.modified_date is not None

    async def test_nullable_tenant_round_trips_as_none(
        self, db_session: AsyncSession
    ) -> None:
        repo = RoleAssignmentRepositoryImpl(db_session)
        user = await _make_user(db_session)
        role = await _make_role(db_session)

        created = await repo.create(_assignment(user.id, role.id))
        db_session.expire_all()
        [fetched] = await repo.list_for_user(user.id)

        assert created.tenant_id is None
        assert fetched.tenant_id is None

    async def test_new_assignments_are_active_by_default(
        self, db_session: AsyncSession
    ) -> None:
        repo = RoleAssignmentRepositoryImpl(db_session)
        user = await _make_user(db_session)
        role = await _make_role(db_session)

        created = await repo.create(_assignment(user.id, role.id))

        assert created.is_active is True


class TestGetActive:
    async def test_finds_the_active_assignment_for_the_pair(
        self, db_session: AsyncSession
    ) -> None:
        repo = RoleAssignmentRepositoryImpl(db_session)
        user = await _make_user(db_session)
        role = await _make_role(db_session)
        created = await repo.create(_assignment(user.id, role.id))

        fetched = await repo.get_active(user.id, role.id)

        assert fetched is not None
        assert fetched.id == created.id

    async def test_ignores_an_inactive_assignment(self, db_session: AsyncSession) -> None:
        repo = RoleAssignmentRepositoryImpl(db_session)
        user = await _make_user(db_session)
        role = await _make_role(db_session)
        await repo.create(_assignment(user.id, role.id, is_active=False))

        assert await repo.get_active(user.id, role.id) is None

    async def test_is_specific_to_the_user_and_role_pair(
        self, db_session: AsyncSession
    ) -> None:
        repo = RoleAssignmentRepositoryImpl(db_session)
        user = await _make_user(db_session)
        other_user = await _make_user(db_session)
        role = await _make_role(db_session)
        other_role = await _make_role(db_session)
        await repo.create(_assignment(user.id, role.id))

        assert await repo.get_active(other_user.id, role.id) is None
        assert await repo.get_active(user.id, other_role.id) is None

    async def test_returns_the_active_row_when_an_older_one_was_deactivated(
        self, db_session: AsyncSession
    ) -> None:
        repo = RoleAssignmentRepositoryImpl(db_session)
        user = await _make_user(db_session)
        role = await _make_role(db_session)
        old = await repo.create(_assignment(user.id, role.id, is_active=False))
        current = await repo.create(_assignment(user.id, role.id))

        fetched = await repo.get_active(user.id, role.id)

        assert fetched is not None
        assert fetched.id == current.id
        assert fetched.id != old.id


class TestListForUser:
    async def test_includes_active_and_inactive_assignments(
        self, db_session: AsyncSession
    ) -> None:
        repo = RoleAssignmentRepositoryImpl(db_session)
        user = await _make_user(db_session)
        active = await repo.create(_assignment(user.id, (await _make_role(db_session)).id))
        inactive = await repo.create(
            _assignment(user.id, (await _make_role(db_session)).id, is_active=False)
        )

        rows = await repo.list_for_user(user.id)

        assert {r.id for r in rows} == {active.id, inactive.id}

    async def test_excludes_other_users_assignments(self, db_session: AsyncSession) -> None:
        repo = RoleAssignmentRepositoryImpl(db_session)
        user = await _make_user(db_session)
        other = await _make_user(db_session)
        role = await _make_role(db_session)
        mine = await repo.create(_assignment(user.id, role.id))
        await repo.create(_assignment(other.id, role.id))

        rows = await repo.list_for_user(user.id)

        assert [r.id for r in rows] == [mine.id]

    async def test_returns_an_empty_list_for_a_user_with_no_assignments(
        self, db_session: AsyncSession
    ) -> None:
        repo = RoleAssignmentRepositoryImpl(db_session)
        user = await _make_user(db_session)

        assert await repo.list_for_user(user.id) == []


class TestListActiveForUser:
    async def test_returns_only_active_assignments(self, db_session: AsyncSession) -> None:
        repo = RoleAssignmentRepositoryImpl(db_session)
        user = await _make_user(db_session)
        active = await repo.create(_assignment(user.id, (await _make_role(db_session)).id))
        await repo.create(
            _assignment(user.id, (await _make_role(db_session)).id, is_active=False)
        )

        rows = await repo.list_active_for_user(user.id)

        assert [r.id for r in rows] == [active.id]

    async def test_excludes_other_users_assignments(self, db_session: AsyncSession) -> None:
        repo = RoleAssignmentRepositoryImpl(db_session)
        user = await _make_user(db_session)
        other = await _make_user(db_session)
        role = await _make_role(db_session)
        await repo.create(_assignment(other.id, role.id))

        assert await repo.list_active_for_user(user.id) == []


class TestListActiveUserIdsForRole:
    async def test_returns_users_with_an_active_assignment(
        self, db_session: AsyncSession
    ) -> None:
        repo = RoleAssignmentRepositoryImpl(db_session)
        role = await _make_role(db_session)
        user = await _make_user(db_session)
        await repo.create(_assignment(user.id, role.id))

        assert await repo.list_active_user_ids_for_role(role.id) == [user.id]

    async def test_excludes_inactive_assignments(self, db_session: AsyncSession) -> None:
        repo = RoleAssignmentRepositoryImpl(db_session)
        role = await _make_role(db_session)
        user = await _make_user(db_session)
        await repo.create(_assignment(user.id, role.id, is_active=False))

        assert await repo.list_active_user_ids_for_role(role.id) == []

    async def test_excludes_deactivated_user_accounts(
        self, db_session: AsyncSession
    ) -> None:
        """An active assignment on a deactivated account must not be handed approvals."""
        repo = RoleAssignmentRepositoryImpl(db_session)
        role = await _make_role(db_session)
        usable = await _make_user(db_session)
        deactivated = await _make_user(db_session, is_active=False)
        await repo.create(_assignment(usable.id, role.id))
        await repo.create(_assignment(deactivated.id, role.id))

        assert await repo.list_active_user_ids_for_role(role.id) == [usable.id]

    async def test_excludes_blocked_user_accounts(self, db_session: AsyncSession) -> None:
        repo = RoleAssignmentRepositoryImpl(db_session)
        role = await _make_role(db_session)
        usable = await _make_user(db_session)
        blocked = await _make_user(db_session, is_blocked=True)
        await repo.create(_assignment(usable.id, role.id))
        await repo.create(_assignment(blocked.id, role.id))

        assert await repo.list_active_user_ids_for_role(role.id) == [usable.id]

    async def test_excludes_users_assigned_to_other_roles(
        self, db_session: AsyncSession
    ) -> None:
        repo = RoleAssignmentRepositoryImpl(db_session)
        role = await _make_role(db_session)
        other_role = await _make_role(db_session)
        member = await _make_user(db_session)
        outsider = await _make_user(db_session)
        await repo.create(_assignment(member.id, role.id))
        await repo.create(_assignment(outsider.id, other_role.id))

        assert await repo.list_active_user_ids_for_role(role.id) == [member.id]

    async def test_is_ordered_by_username(self, db_session: AsyncSession) -> None:
        repo = RoleAssignmentRepositoryImpl(db_session)
        role = await _make_role(db_session)
        token = _token()
        # Created out of order; usernames differ at the first character so the expected
        # order does not depend on the database collation.
        charlie = await _make_user(db_session, username=f"c-{token}")
        alpha = await _make_user(db_session, username=f"a-{token}")
        bravo = await _make_user(db_session, username=f"b-{token}")
        for user in (charlie, alpha, bravo):
            await repo.create(_assignment(user.id, role.id))

        assert await repo.list_active_user_ids_for_role(role.id) == [
            alpha.id,
            bravo.id,
            charlie.id,
        ]

    async def test_returns_an_empty_list_for_a_role_nobody_holds(
        self, db_session: AsyncSession
    ) -> None:
        repo = RoleAssignmentRepositoryImpl(db_session)
        role = await _make_role(db_session)

        assert await repo.list_active_user_ids_for_role(role.id) == []


class TestDeactivate:
    async def test_deactivate_turns_the_assignment_off_and_records_who(
        self, db_session: AsyncSession
    ) -> None:
        repo = RoleAssignmentRepositoryImpl(db_session)
        user = await _make_user(db_session)
        role = await _make_role(db_session)
        created = await repo.create(_assignment(user.id, role.id))

        await repo.deactivate(created.id, "revoker")
        db_session.expire_all()
        [fetched] = await repo.list_for_user(user.id)

        assert fetched.is_active is False
        assert fetched.modified_by == "revoker"
        assert await repo.get_active(user.id, role.id) is None

    async def test_deactivate_keeps_the_row(self, db_session: AsyncSession) -> None:
        """Revocation is a soft delete: the history stays queryable."""
        repo = RoleAssignmentRepositoryImpl(db_session)
        user = await _make_user(db_session)
        role = await _make_role(db_session)
        created = await repo.create(_assignment(user.id, role.id))

        await repo.deactivate(created.id, "revoker")

        assert [r.id for r in await repo.list_for_user(user.id)] == [created.id]

    async def test_deactivate_leaves_other_assignments_active(
        self, db_session: AsyncSession
    ) -> None:
        repo = RoleAssignmentRepositoryImpl(db_session)
        user = await _make_user(db_session)
        revoked = await repo.create(_assignment(user.id, (await _make_role(db_session)).id))
        kept = await repo.create(_assignment(user.id, (await _make_role(db_session)).id))

        await repo.deactivate(revoked.id, "revoker")

        assert [r.id for r in await repo.list_active_for_user(user.id)] == [kept.id]

    async def test_deactivate_of_a_missing_assignment_is_silent(
        self, db_session: AsyncSession
    ) -> None:
        repo = RoleAssignmentRepositoryImpl(db_session)

        await repo.deactivate(_MISSING_ID, "revoker")  # must not raise


class TestDeactivateAllForUser:
    async def test_deactivates_every_active_assignment_and_reports_the_count(
        self, db_session: AsyncSession
    ) -> None:
        repo = RoleAssignmentRepositoryImpl(db_session)
        user = await _make_user(db_session)
        await repo.create(_assignment(user.id, (await _make_role(db_session)).id))
        await repo.create(_assignment(user.id, (await _make_role(db_session)).id))

        count = await repo.deactivate_all_for_user(user.id, "offboarding")
        db_session.expire_all()
        rows = await repo.list_for_user(user.id)

        assert count == 2
        assert await repo.list_active_for_user(user.id) == []
        assert len(rows) == 2
        assert all(r.is_active is False for r in rows)
        assert all(r.modified_by == "offboarding" for r in rows)

    async def test_does_not_count_or_touch_already_inactive_assignments(
        self, db_session: AsyncSession
    ) -> None:
        repo = RoleAssignmentRepositoryImpl(db_session)
        user = await _make_user(db_session)
        await repo.create(_assignment(user.id, (await _make_role(db_session)).id))
        already_off = await repo.create(
            _assignment(
                user.id,
                (await _make_role(db_session)).id,
                is_active=False,
                modified_by="earlier",
            )
        )

        count = await repo.deactivate_all_for_user(user.id, "offboarding")
        db_session.expire_all()
        rows = {r.id: r for r in await repo.list_for_user(user.id)}

        assert count == 1
        assert rows[already_off.id].modified_by == "earlier"

    async def test_only_affects_the_given_user(self, db_session: AsyncSession) -> None:
        repo = RoleAssignmentRepositoryImpl(db_session)
        user = await _make_user(db_session)
        other = await _make_user(db_session)
        role = await _make_role(db_session)
        await repo.create(_assignment(user.id, role.id))
        untouched = await repo.create(_assignment(other.id, role.id))

        await repo.deactivate_all_for_user(user.id, "offboarding")

        assert [r.id for r in await repo.list_active_for_user(other.id)] == [untouched.id]

    async def test_returns_zero_when_the_user_has_nothing_active(
        self, db_session: AsyncSession
    ) -> None:
        repo = RoleAssignmentRepositoryImpl(db_session)
        user = await _make_user(db_session)

        assert await repo.deactivate_all_for_user(user.id, "offboarding") == 0


class TestCascadeOnUserDelete:
    async def test_deleting_the_user_removes_their_assignments(
        self, db_session: AsyncSession
    ) -> None:
        repo = RoleAssignmentRepositoryImpl(db_session)
        user = await _make_user(db_session)
        role = await _make_role(db_session)
        await repo.create(_assignment(user.id, role.id))

        await UserRepositoryImpl(db_session).delete(user.id)

        assert await repo.list_for_user(user.id) == []
