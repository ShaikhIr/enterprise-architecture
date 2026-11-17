"""
WorkflowInstanceRepositoryImpl tests, against a real database session.

Covers the instance CRUD surface (there is no delete on this port), the
filtered / paginated / newest-first `list_all` and its mirrored `count`,
`get_open_for_entity`, the append-only history trail, and the entity <-> ORM mapping,
including the nullable `due_date` / `completed_at` / `from_status_id` / `actor_id`
columns and the JSONB `extra_data` payloads.

An instance has foreign keys to a definition, a status and a user, so each test
builds those first through the real repositories. List and count assertions are
scoped by a unique `entity_type` (or definition) so they do not depend on whatever
else is in the test database.
"""

import secrets
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from src.domain.entities.user import User
from src.domain.entities.workflow import (
    WorkflowDefinition,
    WorkflowHistoryEntry,
    WorkflowInstance,
    WorkflowStatus,
)
from src.infrastructure.database.repositories.user_repository_impl import (
    UserRepositoryImpl,
)
from src.infrastructure.database.repositories.workflow_definition_repository_impl import (
    WorkflowDefinitionRepositoryImpl,
)
from src.infrastructure.database.repositories.workflow_instance_repository_impl import (
    WorkflowInstanceRepositoryImpl,
)

_MISSING_ID = 999_999_999_999
_BASE_TIME = datetime(2030, 1, 1, 12, 0, 0, tzinfo=UTC)


def _token() -> str:
    return secrets.token_hex(5).upper()


class _Scenario:
    """A definition with two statuses and a user: the parents every instance needs."""

    def __init__(
        self,
        definition: WorkflowDefinition,
        start: WorkflowStatus,
        end: WorkflowStatus,
        user: User,
    ) -> None:
        self.definition = definition
        self.start = start
        self.end = end
        self.user = user


async def _scenario(session: AsyncSession) -> _Scenario:
    definitions = WorkflowDefinitionRepositoryImpl(session)
    token = _token()
    definition = await definitions.create(
        WorkflowDefinition(
            code=f"WF{token}",
            name=f"Workflow {token}",
            entity_type=f"type_{token}",
            created_by="test",
            modified_by="test",
        )
    )
    start = await definitions.create_status(
        WorkflowStatus(
            workflow_definition_id=definition.id,
            code="START",
            name="Start",
            is_initial=True,
            created_by="test",
            modified_by="test",
        )
    )
    end = await definitions.create_status(
        WorkflowStatus(
            workflow_definition_id=definition.id,
            code="END",
            name="End",
            is_terminal=True,
            sequence=1,
            created_by="test",
            modified_by="test",
        )
    )
    user = await UserRepositoryImpl(session).create(
        User(username=f"user-{token}", password_hash="x", created_by="t", modified_by="t")
    )
    return _Scenario(definition, start, end, user)


def _instance(scenario: _Scenario, **overrides: object) -> WorkflowInstance:
    defaults: dict[str, object] = {
        "workflow_definition_id": scenario.definition.id,
        "entity_type": scenario.definition.entity_type,
        "entity_id": 1,
        "current_status_id": scenario.start.id,
        "initiated_by": scenario.user.id,
        "started_at": _BASE_TIME,
        "created_by": "test",
        "modified_by": "test",
    }
    defaults.update(overrides)
    return WorkflowInstance(**defaults)  # type: ignore[arg-type]


class TestCreateAndGet:
    async def test_create_round_trips_every_field(self, db_session: AsyncSession) -> None:
        repo = WorkflowInstanceRepositoryImpl(db_session)
        scenario = await _scenario(db_session)
        due = _BASE_TIME + timedelta(days=3)
        completed = _BASE_TIME + timedelta(days=2)

        created = await repo.create(
            _instance(
                scenario,
                entity_id=77,
                priority=5,
                due_date=due,
                completed_at=completed,
                extra_data={"amount": 1200, "tags": ["a", "b"], "nested": {"ok": True}},
                approval_level=2,
                created_by="alice",
                modified_by="bob",
            )
        )
        db_session.expire_all()  # force the read below to hit the row, not the identity map
        fetched = await repo.get_by_id(created.id)

        assert created.id > 0
        assert fetched is not None
        assert fetched.id == created.id
        assert fetched.workflow_definition_id == scenario.definition.id
        assert fetched.entity_type == scenario.definition.entity_type
        assert fetched.entity_id == 77
        assert fetched.current_status_id == scenario.start.id
        assert fetched.initiated_by == scenario.user.id
        assert fetched.priority == 5
        assert fetched.due_date == due
        assert fetched.started_at == _BASE_TIME
        assert fetched.completed_at == completed
        assert fetched.extra_data == {"amount": 1200, "tags": ["a", "b"], "nested": {"ok": True}}
        assert fetched.approval_level == 2
        assert fetched.created_by == "alice"
        assert fetched.modified_by == "bob"
        assert fetched.created_date is not None
        assert fetched.modified_date is not None

    async def test_nullable_columns_and_defaults_round_trip(
        self, db_session: AsyncSession
    ) -> None:
        repo = WorkflowInstanceRepositoryImpl(db_session)
        scenario = await _scenario(db_session)

        created = await repo.create(_instance(scenario))
        db_session.expire_all()
        fetched = await repo.get_by_id(created.id)

        assert fetched is not None
        assert fetched.due_date is None
        assert fetched.completed_at is None
        assert fetched.is_completed is False
        assert fetched.priority == 0
        assert fetched.approval_level == 0
        assert fetched.is_awaiting_approval is False
        assert fetched.extra_data == {}

    async def test_get_by_id_returns_none_for_a_missing_id(
        self, db_session: AsyncSession
    ) -> None:
        repo = WorkflowInstanceRepositoryImpl(db_session)

        assert await repo.get_by_id(_MISSING_ID) is None


class TestUpdate:
    async def test_update_persists_the_mutable_fields(self, db_session: AsyncSession) -> None:
        repo = WorkflowInstanceRepositoryImpl(db_session)
        scenario = await _scenario(db_session)
        created = await repo.create(_instance(scenario))
        due = _BASE_TIME + timedelta(days=9)
        completed = _BASE_TIME + timedelta(days=4)

        created.current_status_id = scenario.end.id
        created.priority = 8
        created.due_date = due
        created.completed_at = completed
        created.extra_data = {"decision": "approved", "level": 3}
        created.approval_level = 3
        created.mark_modified("editor")
        updated = await repo.update(created)
        db_session.expire_all()
        fetched = await repo.get_by_id(created.id)

        assert updated.current_status_id == scenario.end.id
        assert fetched is not None
        assert fetched.current_status_id == scenario.end.id
        assert fetched.priority == 8
        assert fetched.due_date == due
        assert fetched.completed_at == completed
        assert fetched.is_completed is True
        assert fetched.extra_data == {"decision": "approved", "level": 3}
        assert fetched.approval_level == 3
        assert fetched.modified_by == "editor"

    async def test_update_can_clear_nullable_columns(self, db_session: AsyncSession) -> None:
        repo = WorkflowInstanceRepositoryImpl(db_session)
        scenario = await _scenario(db_session)
        created = await repo.create(
            _instance(
                scenario,
                due_date=_BASE_TIME + timedelta(days=1),
                completed_at=_BASE_TIME + timedelta(days=2),
            )
        )

        created.due_date = None
        created.completed_at = None
        await repo.update(created)
        db_session.expire_all()
        fetched = await repo.get_by_id(created.id)

        assert fetched is not None
        assert fetched.due_date is None
        assert fetched.completed_at is None

    async def test_update_does_not_change_identity_columns(
        self, db_session: AsyncSession
    ) -> None:
        """The definition, entity reference and initiator are fixed at creation."""
        repo = WorkflowInstanceRepositoryImpl(db_session)
        scenario = await _scenario(db_session)
        other = await _scenario(db_session)
        created = await repo.create(_instance(scenario, entity_id=10))

        created.workflow_definition_id = other.definition.id
        created.entity_type = "tampered"
        created.entity_id = 999
        created.initiated_by = other.user.id
        await repo.update(created)
        db_session.expire_all()
        fetched = await repo.get_by_id(created.id)

        assert fetched is not None
        assert fetched.workflow_definition_id == scenario.definition.id
        assert fetched.entity_type == scenario.definition.entity_type
        assert fetched.entity_id == 10
        assert fetched.initiated_by == scenario.user.id

    async def test_update_of_a_missing_instance_raises(
        self, db_session: AsyncSession
    ) -> None:
        repo = WorkflowInstanceRepositoryImpl(db_session)
        scenario = await _scenario(db_session)

        with pytest.raises(ValueError, match="not found"):
            await repo.update(_instance(scenario, id=_MISSING_ID))


class TestListAllAndCount:
    async def test_list_all_is_ordered_newest_started_first(
        self, db_session: AsyncSession
    ) -> None:
        repo = WorkflowInstanceRepositoryImpl(db_session)
        scenario = await _scenario(db_session)
        # Created out of chronological order.
        for entity_id, minutes in ((2, 5), (1, 0), (3, 10)):
            await repo.create(
                _instance(
                    scenario,
                    entity_id=entity_id,
                    started_at=_BASE_TIME + timedelta(minutes=minutes),
                )
            )

        rows = await repo.list_all(definition_id=scenario.definition.id)

        assert [r.entity_id for r in rows] == [3, 2, 1]

    async def test_pagination_and_count(self, db_session: AsyncSession) -> None:
        repo = WorkflowInstanceRepositoryImpl(db_session)
        scenario = await _scenario(db_session)
        for entity_id in range(1, 6):
            await repo.create(
                _instance(
                    scenario,
                    entity_id=entity_id,
                    started_at=_BASE_TIME + timedelta(minutes=entity_id),
                )
            )

        page = await repo.list_all(skip=1, limit=2, definition_id=scenario.definition.id)
        total = await repo.count(definition_id=scenario.definition.id)

        assert [r.entity_id for r in page] == [4, 3]
        assert total == 5  # count ignores pagination

    async def test_entity_type_filter(self, db_session: AsyncSession) -> None:
        repo = WorkflowInstanceRepositoryImpl(db_session)
        scenario = await _scenario(db_session)
        other = await _scenario(db_session)
        mine = await repo.create(_instance(scenario))
        await repo.create(_instance(other))

        rows = await repo.list_all(entity_type=scenario.definition.entity_type)

        assert [r.id for r in rows] == [mine.id]
        assert await repo.count(entity_type=scenario.definition.entity_type) == 1

    async def test_entity_id_filter_including_zero_is_not_treated_as_unset(
        self, db_session: AsyncSession
    ) -> None:
        repo = WorkflowInstanceRepositoryImpl(db_session)
        scenario = await _scenario(db_session)
        target = await repo.create(_instance(scenario, entity_id=42))
        await repo.create(_instance(scenario, entity_id=43))
        zero = await repo.create(_instance(scenario, entity_id=0))
        entity_type = scenario.definition.entity_type

        rows = await repo.list_all(entity_type=entity_type, entity_id=42)
        zero_rows = await repo.list_all(entity_type=entity_type, entity_id=0)

        assert [r.id for r in rows] == [target.id]
        assert await repo.count(entity_type=entity_type, entity_id=42) == 1
        assert [r.id for r in zero_rows] == [zero.id]

    async def test_definition_filter(self, db_session: AsyncSession) -> None:
        repo = WorkflowInstanceRepositoryImpl(db_session)
        scenario = await _scenario(db_session)
        other = await _scenario(db_session)
        mine = await repo.create(_instance(scenario))
        await repo.create(_instance(other))

        rows = await repo.list_all(definition_id=scenario.definition.id)

        assert [r.id for r in rows] == [mine.id]
        assert await repo.count(definition_id=scenario.definition.id) == 1

    async def test_status_filter(self, db_session: AsyncSession) -> None:
        repo = WorkflowInstanceRepositoryImpl(db_session)
        scenario = await _scenario(db_session)
        at_start = await repo.create(_instance(scenario, entity_id=1))
        at_end = await repo.create(
            _instance(scenario, entity_id=2, current_status_id=scenario.end.id)
        )
        definition_id = scenario.definition.id

        start_rows = await repo.list_all(
            definition_id=definition_id, status_id=scenario.start.id
        )
        end_rows = await repo.list_all(definition_id=definition_id, status_id=scenario.end.id)

        assert [r.id for r in start_rows] == [at_start.id]
        assert [r.id for r in end_rows] == [at_end.id]
        assert (
            await repo.count(definition_id=definition_id, status_id=scenario.end.id) == 1
        )

    async def test_initiated_by_filter(self, db_session: AsyncSession) -> None:
        repo = WorkflowInstanceRepositoryImpl(db_session)
        scenario = await _scenario(db_session)
        other_user = await UserRepositoryImpl(db_session).create(
            User(username=f"user-{_token()}", password_hash="x", created_by="t", modified_by="t")
        )
        mine = await repo.create(_instance(scenario, entity_id=1))
        await repo.create(_instance(scenario, entity_id=2, initiated_by=other_user.id))

        rows = await repo.list_all(
            definition_id=scenario.definition.id, initiated_by=scenario.user.id
        )

        assert [r.id for r in rows] == [mine.id]
        assert (
            await repo.count(
                definition_id=scenario.definition.id, initiated_by=scenario.user.id
            )
            == 1
        )

    async def test_is_completed_filter_is_derived_from_the_completion_timestamp(
        self, db_session: AsyncSession
    ) -> None:
        repo = WorkflowInstanceRepositoryImpl(db_session)
        scenario = await _scenario(db_session)
        open_one = await repo.create(_instance(scenario, entity_id=1))
        done = await repo.create(
            _instance(scenario, entity_id=2, completed_at=_BASE_TIME + timedelta(hours=1))
        )
        definition_id = scenario.definition.id

        completed_rows = await repo.list_all(definition_id=definition_id, is_completed=True)
        open_rows = await repo.list_all(definition_id=definition_id, is_completed=False)
        all_rows = await repo.list_all(definition_id=definition_id)

        assert [r.id for r in completed_rows] == [done.id]
        assert [r.id for r in open_rows] == [open_one.id]
        assert len(all_rows) == 2
        assert await repo.count(definition_id=definition_id, is_completed=True) == 1
        assert await repo.count(definition_id=definition_id, is_completed=False) == 1
        assert await repo.count(definition_id=definition_id) == 2

    async def test_filters_combine_with_and_and_count_mirrors_them(
        self, db_session: AsyncSession
    ) -> None:
        repo = WorkflowInstanceRepositoryImpl(db_session)
        scenario = await _scenario(db_session)
        match = await repo.create(_instance(scenario, entity_id=1))
        await repo.create(  # right status, but completed
            _instance(scenario, entity_id=2, completed_at=_BASE_TIME + timedelta(hours=1))
        )
        await repo.create(  # open, but in the wrong status
            _instance(scenario, entity_id=3, current_status_id=scenario.end.id)
        )
        filters = {
            "definition_id": scenario.definition.id,
            "status_id": scenario.start.id,
            "is_completed": False,
        }

        rows = await repo.list_all(**filters)  # type: ignore[arg-type]
        total = await repo.count(**filters)  # type: ignore[arg-type]

        assert [r.id for r in rows] == [match.id]
        assert total == 1

    async def test_no_match_gives_an_empty_list_and_a_zero_count(
        self, db_session: AsyncSession
    ) -> None:
        repo = WorkflowInstanceRepositoryImpl(db_session)

        assert await repo.list_all(entity_type=f"never_{_token()}") == []
        assert await repo.count(entity_type=f"never_{_token()}") == 0


class TestGetOpenForEntity:
    async def test_returns_the_open_instance_for_the_record(
        self, db_session: AsyncSession
    ) -> None:
        repo = WorkflowInstanceRepositoryImpl(db_session)
        scenario = await _scenario(db_session)
        created = await repo.create(_instance(scenario, entity_id=5))

        found = await repo.get_open_for_entity(scenario.definition.entity_type, 5)

        assert found is not None
        assert found.id == created.id

    async def test_ignores_completed_instances(self, db_session: AsyncSession) -> None:
        repo = WorkflowInstanceRepositoryImpl(db_session)
        scenario = await _scenario(db_session)
        await repo.create(
            _instance(scenario, entity_id=5, completed_at=_BASE_TIME + timedelta(hours=1))
        )

        assert await repo.get_open_for_entity(scenario.definition.entity_type, 5) is None

    async def test_returns_the_open_one_when_an_earlier_run_completed(
        self, db_session: AsyncSession
    ) -> None:
        repo = WorkflowInstanceRepositoryImpl(db_session)
        scenario = await _scenario(db_session)
        await repo.create(
            _instance(
                scenario,
                entity_id=5,
                started_at=_BASE_TIME,
                completed_at=_BASE_TIME + timedelta(hours=1),
            )
        )
        reopened = await repo.create(
            _instance(scenario, entity_id=5, started_at=_BASE_TIME + timedelta(days=1))
        )

        found = await repo.get_open_for_entity(scenario.definition.entity_type, 5)

        assert found is not None
        assert found.id == reopened.id

    async def test_prefers_the_most_recently_started_open_instance(
        self, db_session: AsyncSession
    ) -> None:
        repo = WorkflowInstanceRepositoryImpl(db_session)
        scenario = await _scenario(db_session)
        await repo.create(_instance(scenario, entity_id=5, started_at=_BASE_TIME))
        latest = await repo.create(
            _instance(scenario, entity_id=5, started_at=_BASE_TIME + timedelta(days=2))
        )

        found = await repo.get_open_for_entity(scenario.definition.entity_type, 5)

        assert found is not None
        assert found.id == latest.id

    async def test_is_specific_to_entity_type_and_id(self, db_session: AsyncSession) -> None:
        repo = WorkflowInstanceRepositoryImpl(db_session)
        scenario = await _scenario(db_session)
        await repo.create(_instance(scenario, entity_id=5))

        assert await repo.get_open_for_entity(scenario.definition.entity_type, 6) is None
        assert await repo.get_open_for_entity(f"other_{_token()}", 5) is None


class TestHistory:
    @staticmethod
    def _entry(instance_id: int, to_status_id: int, **overrides: object) -> WorkflowHistoryEntry:
        defaults: dict[str, object] = {
            "instance_id": instance_id,
            "to_status_id": to_status_id,
            "action_code": "SUBMIT",
            "created_at": _BASE_TIME,
        }
        defaults.update(overrides)
        return WorkflowHistoryEntry(**defaults)  # type: ignore[arg-type]

    async def test_add_history_round_trips_every_field(
        self, db_session: AsyncSession
    ) -> None:
        repo = WorkflowInstanceRepositoryImpl(db_session)
        scenario = await _scenario(db_session)
        instance = await repo.create(_instance(scenario))

        added = await repo.add_history(
            self._entry(
                instance.id,
                scenario.end.id,
                from_status_id=scenario.start.id,
                action_code="APPROVE",
                actor_id=scenario.user.id,
                actor_username="alice",
                comments="Looks good",
                extra_data={"level": 2, "flags": ["x"]},
                ip_address="203.0.113.9",
            )
        )
        db_session.expire_all()
        [fetched] = await repo.list_history(instance.id)

        assert added.id > 0
        assert fetched.id == added.id
        assert fetched.instance_id == instance.id
        assert fetched.from_status_id == scenario.start.id
        assert fetched.to_status_id == scenario.end.id
        assert fetched.action_code == "APPROVE"
        assert fetched.actor_id == scenario.user.id
        assert fetched.actor_username == "alice"
        assert fetched.comments == "Looks good"
        assert fetched.extra_data == {"level": 2, "flags": ["x"]}
        assert fetched.ip_address == "203.0.113.9"
        assert fetched.created_at == _BASE_TIME

    async def test_nullable_columns_and_defaults_round_trip(
        self, db_session: AsyncSession
    ) -> None:
        repo = WorkflowInstanceRepositoryImpl(db_session)
        scenario = await _scenario(db_session)
        instance = await repo.create(_instance(scenario))

        await repo.add_history(self._entry(instance.id, scenario.start.id))
        db_session.expire_all()
        [fetched] = await repo.list_history(instance.id)

        assert fetched.from_status_id is None
        assert fetched.actor_id is None
        assert fetched.actor_username == ""
        assert fetched.comments == ""
        assert fetched.extra_data == {}
        assert fetched.ip_address == ""

    async def test_list_history_is_newest_first(self, db_session: AsyncSession) -> None:
        repo = WorkflowInstanceRepositoryImpl(db_session)
        scenario = await _scenario(db_session)
        instance = await repo.create(_instance(scenario))
        # Recorded out of chronological order.
        for action, minutes in (("SECOND", 5), ("FIRST", 0), ("THIRD", 10)):
            await repo.add_history(
                self._entry(
                    instance.id,
                    scenario.end.id,
                    action_code=action,
                    created_at=_BASE_TIME + timedelta(minutes=minutes),
                )
            )

        rows = await repo.list_history(instance.id)

        assert [r.action_code for r in rows] == ["THIRD", "SECOND", "FIRST"]

    async def test_list_history_is_scoped_to_the_instance(
        self, db_session: AsyncSession
    ) -> None:
        repo = WorkflowInstanceRepositoryImpl(db_session)
        scenario = await _scenario(db_session)
        first = await repo.create(_instance(scenario, entity_id=1))
        second = await repo.create(_instance(scenario, entity_id=2))
        await repo.add_history(self._entry(first.id, scenario.end.id, action_code="ONE"))
        await repo.add_history(self._entry(second.id, scenario.end.id, action_code="TWO"))

        rows = await repo.list_history(first.id)

        assert [r.action_code for r in rows] == ["ONE"]

    async def test_list_history_is_empty_for_an_instance_with_no_history(
        self, db_session: AsyncSession
    ) -> None:
        repo = WorkflowInstanceRepositoryImpl(db_session)
        scenario = await _scenario(db_session)
        instance = await repo.create(_instance(scenario))

        assert await repo.list_history(instance.id) == []
