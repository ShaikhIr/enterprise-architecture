"""
AuditLogRepositoryImpl tests, against a real database session.

`audit_logs` is append-only, so the port has no update or delete and neither do
these tests. They cover `add`, the filtered / paginated / newest-first `query`,
`count` mirroring the same filters, `latest_timestamp_by_actor`, and the entity <->
ORM mapping including the nullable columns.

Other tests in the suite may run with the automatic audit listener registered, and
a database may hold rows from earlier work, so nothing here assumes the table is
empty. Each test stamps its rows with identifiers no other row carries (a unique
`resource_type` / `actor_username` / `actor_id`), and the filters under test are
asserted either in combination with that identifier or as a before/after delta.
"""

import secrets
from datetime import UTC, datetime, timedelta

from sqlalchemy.ext.asyncio import AsyncSession

from src.domain.entities.audit_log import AuditAction, AuditLog
from src.infrastructure.database.repositories.audit_log_repository_impl import (
    AuditLogRepositoryImpl,
)

_BASE_TIME = datetime(2030, 1, 1, 12, 0, 0, tzinfo=UTC)
_ALL = 100_000


def _token() -> str:
    return secrets.token_hex(5).upper()


def _unique_actor_id() -> int:
    """A bigint no real user row is likely to share (actor_id has no foreign key)."""
    return 10_000_000_000 + secrets.randbelow(10**9)


def _entry(**overrides: object) -> AuditLog:
    defaults: dict[str, object] = {
        "actor_username": f"actor-{_token()}",
        "action": AuditAction.LOGIN_SUCCESS.value,
        "resource_type": f"Res{_token()}",
        "created_at": _BASE_TIME,
    }
    defaults.update(overrides)
    return AuditLog(**defaults)  # type: ignore[arg-type]


class TestAdd:
    async def test_add_round_trips_every_field(self, db_session: AsyncSession) -> None:
        repo = AuditLogRepositoryImpl(db_session)
        resource_type = f"Res{_token()}"
        actor_id = _unique_actor_id()

        await repo.add(
            AuditLog(
                actor_id=actor_id,
                actor_username="alice",
                action=AuditAction.ROLE_ASSIGNED.value,
                resource_type=resource_type,
                resource_id="42",
                tenant_id=7,
                old_value='{"is_active": "True"}',
                new_value='{"is_active": "False"}',
                ip_address="203.0.113.9",
                user_agent="pytest-agent/1.0",
                extra_data='{"changed_columns": ["is_active"]}',
                created_at=_BASE_TIME,
            )
        )
        db_session.expire_all()  # force the read below to hit the row, not the identity map
        [fetched] = await repo.query(resource_type=resource_type)

        assert fetched.id > 0
        assert fetched.actor_id == actor_id
        assert fetched.actor_username == "alice"
        assert fetched.action == AuditAction.ROLE_ASSIGNED.value
        assert fetched.resource_type == resource_type
        assert fetched.resource_id == "42"
        assert fetched.tenant_id == 7
        assert fetched.old_value == '{"is_active": "True"}'
        assert fetched.new_value == '{"is_active": "False"}'
        assert fetched.ip_address == "203.0.113.9"
        assert fetched.user_agent == "pytest-agent/1.0"
        assert fetched.extra_data == '{"changed_columns": ["is_active"]}'
        assert fetched.created_at == _BASE_TIME

    async def test_nullable_columns_round_trip_as_none(
        self, db_session: AsyncSession
    ) -> None:
        repo = AuditLogRepositoryImpl(db_session)
        resource_type = f"Res{_token()}"

        await repo.add(_entry(resource_type=resource_type))
        db_session.expire_all()
        [fetched] = await repo.query(resource_type=resource_type)

        assert fetched.actor_id is None
        assert fetched.tenant_id is None
        assert fetched.old_value is None
        assert fetched.new_value is None
        assert fetched.extra_data is None

    async def test_string_defaults_are_stored_as_empty_strings(
        self, db_session: AsyncSession
    ) -> None:
        repo = AuditLogRepositoryImpl(db_session)
        resource_type = f"Res{_token()}"

        await repo.add(_entry(resource_type=resource_type))
        db_session.expire_all()
        [fetched] = await repo.query(resource_type=resource_type)

        assert fetched.resource_id == ""
        assert fetched.ip_address == ""
        assert fetched.user_agent == ""

    async def test_each_entry_gets_its_own_database_id(
        self, db_session: AsyncSession
    ) -> None:
        repo = AuditLogRepositoryImpl(db_session)
        resource_type = f"Res{_token()}"
        await repo.add(_entry(resource_type=resource_type))
        await repo.add(_entry(resource_type=resource_type))

        rows = await repo.query(resource_type=resource_type)

        assert len(rows) == 2
        assert rows[0].id != rows[1].id


class TestQueryFilters:
    async def test_resource_type_filter(self, db_session: AsyncSession) -> None:
        repo = AuditLogRepositoryImpl(db_session)
        wanted = f"Res{_token()}"
        await repo.add(_entry(resource_type=wanted, resource_id="1"))
        await repo.add(_entry(resource_type=f"Other{_token()}", resource_id="2"))

        rows = await repo.query(resource_type=wanted)

        assert [r.resource_id for r in rows] == ["1"]

    async def test_actor_username_filter_is_an_exact_match(
        self, db_session: AsyncSession
    ) -> None:
        repo = AuditLogRepositoryImpl(db_session)
        username = f"actor-{_token()}"
        await repo.add(_entry(actor_username=username, resource_id="1"))
        await repo.add(_entry(actor_username=f"{username}-suffix", resource_id="2"))

        rows = await repo.query(actor_username=username)

        assert [r.resource_id for r in rows] == ["1"]

    async def test_actor_id_filter(self, db_session: AsyncSession) -> None:
        repo = AuditLogRepositoryImpl(db_session)
        actor_id = _unique_actor_id()
        await repo.add(_entry(actor_id=actor_id, resource_id="1"))
        await repo.add(_entry(actor_id=actor_id + 1, resource_id="2"))
        await repo.add(_entry(actor_id=None, resource_id="3"))

        rows = await repo.query(actor_id=actor_id)

        assert [r.resource_id for r in rows] == ["1"]

    async def test_action_filter(self, db_session: AsyncSession) -> None:
        repo = AuditLogRepositoryImpl(db_session)
        username = f"actor-{_token()}"
        await repo.add(
            _entry(actor_username=username, action=AuditAction.LOGIN_FAILED.value, resource_id="1")
        )
        await repo.add(
            _entry(actor_username=username, action=AuditAction.LOGIN_SUCCESS.value, resource_id="2")
        )

        everything = await repo.query(actor_username=username)
        failed_only = await repo.query(
            action=AuditAction.LOGIN_FAILED.value, actor_username=username
        )
        failed_anywhere = await repo.query(
            action=AuditAction.LOGIN_FAILED.value, limit=_ALL
        )

        assert len(everything) == 2
        assert [r.resource_id for r in failed_only] == ["1"]
        assert all(r.action == AuditAction.LOGIN_FAILED.value for r in failed_anywhere)
        assert {r.id for r in failed_only} <= {r.id for r in failed_anywhere}

    async def test_filters_combine_with_and(self, db_session: AsyncSession) -> None:
        repo = AuditLogRepositoryImpl(db_session)
        resource_type = f"Res{_token()}"
        await repo.add(
            _entry(
                resource_type=resource_type,
                action=AuditAction.INSERT.value,
                actor_username="alice",
                resource_id="match",
            )
        )
        await repo.add(
            _entry(
                resource_type=resource_type,
                action=AuditAction.UPDATE.value,
                actor_username="alice",
                resource_id="wrong-action",
            )
        )
        await repo.add(
            _entry(
                resource_type=resource_type,
                action=AuditAction.INSERT.value,
                actor_username="bob",
                resource_id="wrong-actor",
            )
        )

        rows = await repo.query(
            resource_type=resource_type,
            action=AuditAction.INSERT.value,
            actor_username="alice",
        )

        assert [r.resource_id for r in rows] == ["match"]

    async def test_no_match_returns_an_empty_list(self, db_session: AsyncSession) -> None:
        repo = AuditLogRepositoryImpl(db_session)

        assert await repo.query(resource_type=f"Never{_token()}") == []


class TestQueryOrderingAndPagination:
    async def test_results_are_newest_first(self, db_session: AsyncSession) -> None:
        repo = AuditLogRepositoryImpl(db_session)
        resource_type = f"Res{_token()}"
        # Added out of chronological order.
        for minutes, label in ((5, "middle"), (0, "oldest"), (10, "newest")):
            await repo.add(
                _entry(
                    resource_type=resource_type,
                    resource_id=label,
                    created_at=_BASE_TIME + timedelta(minutes=minutes),
                )
            )

        rows = await repo.query(resource_type=resource_type)

        assert [r.resource_id for r in rows] == ["newest", "middle", "oldest"]

    async def test_limit_and_skip_page_through_the_ordered_results(
        self, db_session: AsyncSession
    ) -> None:
        repo = AuditLogRepositoryImpl(db_session)
        resource_type = f"Res{_token()}"
        for minute in range(5):
            await repo.add(
                _entry(
                    resource_type=resource_type,
                    resource_id=str(minute),
                    created_at=_BASE_TIME + timedelta(minutes=minute),
                )
            )

        first_page = await repo.query(resource_type=resource_type, skip=0, limit=2)
        second_page = await repo.query(resource_type=resource_type, skip=2, limit=2)
        last_page = await repo.query(resource_type=resource_type, skip=4, limit=2)

        assert [r.resource_id for r in first_page] == ["4", "3"]
        assert [r.resource_id for r in second_page] == ["2", "1"]
        assert [r.resource_id for r in last_page] == ["0"]

    async def test_skip_beyond_the_end_returns_nothing(
        self, db_session: AsyncSession
    ) -> None:
        repo = AuditLogRepositoryImpl(db_session)
        resource_type = f"Res{_token()}"
        await repo.add(_entry(resource_type=resource_type))

        assert await repo.query(resource_type=resource_type, skip=1) == []

    async def test_default_limit_is_fifty(self, db_session: AsyncSession) -> None:
        repo = AuditLogRepositoryImpl(db_session)
        resource_type = f"Res{_token()}"
        for index in range(51):
            await repo.add(
                _entry(
                    resource_type=resource_type,
                    resource_id=str(index),
                    created_at=_BASE_TIME + timedelta(seconds=index),
                )
            )

        rows = await repo.query(resource_type=resource_type)

        assert len(rows) == 50


class TestCount:
    async def test_count_mirrors_the_resource_type_filter(
        self, db_session: AsyncSession
    ) -> None:
        repo = AuditLogRepositoryImpl(db_session)
        resource_type = f"Res{_token()}"
        for _ in range(3):
            await repo.add(_entry(resource_type=resource_type))
        await repo.add(_entry(resource_type=f"Other{_token()}"))

        assert await repo.count(resource_type=resource_type) == 3

    async def test_count_mirrors_the_actor_username_filter(
        self, db_session: AsyncSession
    ) -> None:
        repo = AuditLogRepositoryImpl(db_session)
        username = f"actor-{_token()}"
        await repo.add(_entry(actor_username=username))
        await repo.add(_entry(actor_username=username))
        await repo.add(_entry())

        assert await repo.count(actor_username=username) == 2

    async def test_count_mirrors_the_actor_id_filter(self, db_session: AsyncSession) -> None:
        repo = AuditLogRepositoryImpl(db_session)
        actor_id = _unique_actor_id()
        await repo.add(_entry(actor_id=actor_id))
        await repo.add(_entry(actor_id=actor_id + 1))

        assert await repo.count(actor_id=actor_id) == 1

    async def test_count_mirrors_the_action_filter_as_a_delta(
        self, db_session: AsyncSession
    ) -> None:
        repo = AuditLogRepositoryImpl(db_session)
        before = await repo.count(action=AuditAction.TOKEN_REFRESHED.value)
        await repo.add(_entry(action=AuditAction.TOKEN_REFRESHED.value))
        await repo.add(_entry(action=AuditAction.TOKEN_REFRESHED.value))
        await repo.add(_entry(action=AuditAction.LOGIN_LOCKED.value))

        after = await repo.count(action=AuditAction.TOKEN_REFRESHED.value)

        assert after - before == 2

    async def test_count_combines_filters_like_query_does(
        self, db_session: AsyncSession
    ) -> None:
        repo = AuditLogRepositoryImpl(db_session)
        resource_type = f"Res{_token()}"
        await repo.add(_entry(resource_type=resource_type, action=AuditAction.INSERT.value))
        await repo.add(_entry(resource_type=resource_type, action=AuditAction.INSERT.value))
        await repo.add(_entry(resource_type=resource_type, action=AuditAction.DELETE.value))

        rows = await repo.query(resource_type=resource_type, action=AuditAction.INSERT.value)
        total = await repo.count(resource_type=resource_type, action=AuditAction.INSERT.value)

        assert total == len(rows) == 2

    async def test_count_ignores_pagination_and_is_zero_for_no_match(
        self, db_session: AsyncSession
    ) -> None:
        repo = AuditLogRepositoryImpl(db_session)
        resource_type = f"Res{_token()}"
        for _ in range(3):
            await repo.add(_entry(resource_type=resource_type))

        assert await repo.count(resource_type=resource_type) == 3
        assert await repo.count(resource_type=f"Never{_token()}") == 0


class TestLatestTimestampByActor:
    async def test_returns_the_most_recent_matching_timestamp_per_actor(
        self, db_session: AsyncSession
    ) -> None:
        repo = AuditLogRepositoryImpl(db_session)
        actor_a = _unique_actor_id()
        actor_b = actor_a + 1
        action = AuditAction.LOGIN_SUCCESS.value
        for actor, minutes in ((actor_a, 1), (actor_a, 30), (actor_a, 10), (actor_b, 5)):
            await repo.add(
                _entry(
                    actor_id=actor,
                    action=action,
                    created_at=_BASE_TIME + timedelta(minutes=minutes),
                )
            )

        latest = await repo.latest_timestamp_by_actor(action, [actor_a, actor_b])

        assert latest == {
            actor_a: _BASE_TIME + timedelta(minutes=30),
            actor_b: _BASE_TIME + timedelta(minutes=5),
        }

    async def test_only_considers_the_requested_action(
        self, db_session: AsyncSession
    ) -> None:
        repo = AuditLogRepositoryImpl(db_session)
        actor = _unique_actor_id()
        await repo.add(
            _entry(
                actor_id=actor,
                action=AuditAction.LOGIN_SUCCESS.value,
                created_at=_BASE_TIME,
            )
        )
        await repo.add(
            _entry(
                actor_id=actor,
                action=AuditAction.LOGIN_FAILED.value,
                created_at=_BASE_TIME + timedelta(hours=1),
            )
        )

        latest = await repo.latest_timestamp_by_actor(
            AuditAction.LOGIN_SUCCESS.value, [actor]
        )

        assert latest == {actor: _BASE_TIME}

    async def test_only_includes_the_requested_actors(
        self, db_session: AsyncSession
    ) -> None:
        repo = AuditLogRepositoryImpl(db_session)
        wanted = _unique_actor_id()
        other = wanted + 1
        action = AuditAction.LOGIN_SUCCESS.value
        await repo.add(_entry(actor_id=wanted, action=action))
        await repo.add(_entry(actor_id=other, action=action))

        latest = await repo.latest_timestamp_by_actor(action, [wanted])

        assert set(latest) == {wanted}

    async def test_actors_with_no_matching_entries_are_omitted(
        self, db_session: AsyncSession
    ) -> None:
        repo = AuditLogRepositoryImpl(db_session)
        silent = _unique_actor_id()

        latest = await repo.latest_timestamp_by_actor(
            AuditAction.LOGIN_SUCCESS.value, [silent]
        )

        assert latest == {}

    async def test_entries_without_an_actor_are_never_reported(
        self, db_session: AsyncSession
    ) -> None:
        repo = AuditLogRepositoryImpl(db_session)
        actor = _unique_actor_id()
        action = AuditAction.LOGIN_SUCCESS.value
        await repo.add(_entry(actor_id=None, action=action))
        await repo.add(_entry(actor_id=actor, action=action))

        latest = await repo.latest_timestamp_by_actor(action, [actor])

        assert set(latest) == {actor}

    async def test_empty_actor_list_returns_an_empty_dict(
        self, db_session: AsyncSession
    ) -> None:
        repo = AuditLogRepositoryImpl(db_session)

        assert await repo.latest_timestamp_by_actor(AuditAction.LOGIN_SUCCESS.value, []) == {}
