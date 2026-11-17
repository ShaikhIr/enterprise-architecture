"""
WorkflowDefinitionRepositoryImpl tests, against a real database session.

The repository persists three related aggregates: the definition itself (code-keyed,
via `SqlAlchemyRepository`), its statuses and its transitions. The tests cover each,
plus what is specific to this repository: filtered/paginated/ordered listing and its
mirrored `count`, case-insensitive name uniqueness, status-code and transition
uniqueness scoped to a definition, the "initial status" lookup, the dependency counts
that guard status deletion, and the database cascade from definition/status deletes.

Unique values (codes, names, entity types) come from a per-call token so the tests do
not depend on, or collide with, anything else in the database. List and count
assertions are scoped by a unique `entity_type` for the same reason.
"""

import secrets

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from src.domain.entities.user import User
from src.domain.entities.workflow import (
    WorkflowDefinition,
    WorkflowStatus,
    WorkflowTransition,
)
from src.domain.enums.workflow_enums import WorkflowActionType
from src.infrastructure.database.models.workflow_model import WorkflowInstanceModel
from src.infrastructure.database.repositories.user_repository_impl import (
    UserRepositoryImpl,
)
from src.infrastructure.database.repositories.workflow_definition_repository_impl import (
    WorkflowDefinitionRepositoryImpl,
)

_MISSING_ID = 999_999_999_999


def _token() -> str:
    return secrets.token_hex(5).upper()


def _definition(**overrides: object) -> WorkflowDefinition:
    token = _token()
    defaults: dict[str, object] = {
        "code": f"WF{token}",
        "name": f"Workflow {token}",
        "entity_type": f"type_{token}",
        "created_by": "test",
        "modified_by": "test",
    }
    defaults.update(overrides)
    return WorkflowDefinition(**defaults)  # type: ignore[arg-type]


def _status(definition_id: int, **overrides: object) -> WorkflowStatus:
    token = _token()
    defaults: dict[str, object] = {
        "workflow_definition_id": definition_id,
        "code": f"S{token}",
        "name": f"Status {token}",
        "created_by": "test",
        "modified_by": "test",
    }
    defaults.update(overrides)
    return WorkflowStatus(**defaults)  # type: ignore[arg-type]


def _transition(
    definition_id: int, from_status_id: int, to_status_id: int, **overrides: object
) -> WorkflowTransition:
    defaults: dict[str, object] = {
        "workflow_definition_id": definition_id,
        "from_status_id": from_status_id,
        "to_status_id": to_status_id,
        "action_code": f"ACT{_token()}",
        "created_by": "test",
        "modified_by": "test",
    }
    defaults.update(overrides)
    return WorkflowTransition(**defaults)  # type: ignore[arg-type]


async def _make_user(session: AsyncSession) -> User:
    return await UserRepositoryImpl(session).create(
        User(username=f"user-{_token()}", password_hash="x", created_by="t", modified_by="t")
    )


async def _definition_with_two_statuses(
    repo: WorkflowDefinitionRepositoryImpl,
) -> tuple[WorkflowDefinition, WorkflowStatus, WorkflowStatus]:
    definition = await repo.create(_definition())
    start = await repo.create_status(_status(definition.id, is_initial=True, sequence=1))
    end = await repo.create_status(_status(definition.id, is_terminal=True, sequence=2))
    return definition, start, end


class TestDefinitionCrud:
    async def test_create_round_trips_every_field(self, db_session: AsyncSession) -> None:
        repo = WorkflowDefinitionRepositoryImpl(db_session)

        created = await repo.create(
            _definition(
                description="Approval flow",
                version=3,
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
        assert fetched.name == created.name
        assert fetched.entity_type == created.entity_type
        assert fetched.description == "Approval flow"
        assert fetched.version == 3
        assert fetched.is_active is False
        assert fetched.created_by == "alice"
        assert fetched.modified_by == "bob"
        assert fetched.created_date is not None
        assert fetched.modified_date is not None

    async def test_entity_defaults_are_persisted(self, db_session: AsyncSession) -> None:
        repo = WorkflowDefinitionRepositoryImpl(db_session)

        created = await repo.create(_definition())
        db_session.expire_all()
        fetched = await repo.get_by_id(created.id)

        assert fetched is not None
        assert fetched.description == ""
        assert fetched.version == 1
        assert fetched.is_active is True

    async def test_get_by_id_returns_none_for_a_missing_id(
        self, db_session: AsyncSession
    ) -> None:
        repo = WorkflowDefinitionRepositoryImpl(db_session)

        assert await repo.get_by_id(_MISSING_ID) is None

    async def test_get_by_code_finds_the_definition(self, db_session: AsyncSession) -> None:
        repo = WorkflowDefinitionRepositoryImpl(db_session)
        created = await repo.create(_definition())

        fetched = await repo.get_by_code(created.code)

        assert fetched is not None
        assert fetched.id == created.id
        assert await repo.get_by_code(f"MISSING{_token()}") is None

    async def test_update_persists_every_editable_field(
        self, db_session: AsyncSession
    ) -> None:
        repo = WorkflowDefinitionRepositoryImpl(db_session)
        created = await repo.create(_definition())
        token = _token()

        created.code = f"NEW{token}"
        created.name = f"Renamed {token}"
        created.description = "Edited"
        created.entity_type = f"newtype_{token}"
        created.version = 2
        created.is_active = False
        created.mark_modified("editor")
        updated = await repo.update(created)
        db_session.expire_all()
        fetched = await repo.get_by_id(created.id)

        assert updated.code == f"NEW{token}"
        assert fetched is not None
        assert fetched.code == f"NEW{token}"
        assert fetched.name == f"Renamed {token}"
        assert fetched.description == "Edited"
        assert fetched.entity_type == f"newtype_{token}"
        assert fetched.version == 2
        assert fetched.is_active is False
        assert fetched.modified_by == "editor"

    async def test_update_of_a_missing_definition_raises(
        self, db_session: AsyncSession
    ) -> None:
        repo = WorkflowDefinitionRepositoryImpl(db_session)

        with pytest.raises(ValueError, match="not found"):
            await repo.update(_definition(id=_MISSING_ID))

    async def test_delete_removes_the_row(self, db_session: AsyncSession) -> None:
        repo = WorkflowDefinitionRepositoryImpl(db_session)
        created = await repo.create(_definition())

        await repo.delete(created.id)

        assert await repo.get_by_id(created.id) is None

    async def test_delete_of_a_missing_definition_is_silent(
        self, db_session: AsyncSession
    ) -> None:
        repo = WorkflowDefinitionRepositoryImpl(db_session)

        await repo.delete(_MISSING_ID)  # must not raise

    async def test_deleting_a_definition_cascades_to_its_statuses_and_transitions(
        self, db_session: AsyncSession
    ) -> None:
        repo = WorkflowDefinitionRepositoryImpl(db_session)
        definition, start, end = await _definition_with_two_statuses(repo)
        await repo.create_transition(_transition(definition.id, start.id, end.id))

        await repo.delete(definition.id)

        assert await repo.list_statuses(definition.id) == []
        assert await repo.list_transitions(definition.id) == []
        assert await repo.get_status(start.id) is None


class TestExistsByCode:
    async def test_true_for_an_existing_code_and_false_otherwise(
        self, db_session: AsyncSession
    ) -> None:
        repo = WorkflowDefinitionRepositoryImpl(db_session)
        created = await repo.create(_definition())

        assert await repo.exists_by_code(created.code) is True
        assert await repo.exists_by_code(f"MISSING{_token()}") is False

    async def test_exclude_id_ignores_the_row_being_edited(
        self, db_session: AsyncSession
    ) -> None:
        repo = WorkflowDefinitionRepositoryImpl(db_session)
        created = await repo.create(_definition())
        other = await repo.create(_definition())

        assert await repo.exists_by_code(created.code, exclude_id=created.id) is False
        assert await repo.exists_by_code(created.code, exclude_id=other.id) is True


class TestExistsByName:
    async def test_true_for_an_existing_name(self, db_session: AsyncSession) -> None:
        repo = WorkflowDefinitionRepositoryImpl(db_session)
        created = await repo.create(_definition())

        assert await repo.exists_by_name(created.name) is True
        assert await repo.exists_by_name(f"No such workflow {_token()}") is False

    async def test_match_is_case_insensitive(self, db_session: AsyncSession) -> None:
        repo = WorkflowDefinitionRepositoryImpl(db_session)
        created = await repo.create(_definition(name=f"Mixed Case {_token()}"))

        assert await repo.exists_by_name(created.name.upper()) is True
        assert await repo.exists_by_name(created.name.lower()) is True

    async def test_exclude_id_ignores_the_row_being_edited(
        self, db_session: AsyncSession
    ) -> None:
        repo = WorkflowDefinitionRepositoryImpl(db_session)
        created = await repo.create(_definition())
        other = await repo.create(_definition())

        assert await repo.exists_by_name(created.name, exclude_id=created.id) is False
        assert await repo.exists_by_name(created.name, exclude_id=other.id) is True


class TestListAndCount:
    async def test_list_all_is_ordered_by_code(self, db_session: AsyncSession) -> None:
        repo = WorkflowDefinitionRepositoryImpl(db_session)
        token = _token()
        entity_type = f"type_{token}"
        # Created out of order. Codes differ only in the last character, so the expected
        # order does not depend on the database collation.
        for suffix in ("C", "A", "B"):
            await repo.create(_definition(code=f"WF{token}{suffix}", entity_type=entity_type))

        rows = await repo.list_all(entity_type=entity_type)

        assert [r.code for r in rows] == [f"WF{token}A", f"WF{token}B", f"WF{token}C"]

    async def test_pagination_skips_and_limits_in_code_order(
        self, db_session: AsyncSession
    ) -> None:
        repo = WorkflowDefinitionRepositoryImpl(db_session)
        token = _token()
        entity_type = f"type_{token}"
        for suffix in "ABCDE":
            await repo.create(_definition(code=f"WF{token}{suffix}", entity_type=entity_type))

        page = await repo.list_all(skip=1, limit=2, entity_type=entity_type)
        total = await repo.count(entity_type=entity_type)

        assert [r.code for r in page] == [f"WF{token}B", f"WF{token}C"]
        assert total == 5  # count ignores pagination

    async def test_entity_type_filter_is_an_exact_match(
        self, db_session: AsyncSession
    ) -> None:
        repo = WorkflowDefinitionRepositoryImpl(db_session)
        entity_type = f"type_{_token()}"
        mine = await repo.create(_definition(entity_type=entity_type))
        await repo.create(_definition(entity_type=f"{entity_type}_other"))

        rows = await repo.list_all(entity_type=entity_type)

        assert [r.id for r in rows] == [mine.id]
        assert await repo.count(entity_type=entity_type) == 1

    async def test_is_active_filter(self, db_session: AsyncSession) -> None:
        repo = WorkflowDefinitionRepositoryImpl(db_session)
        entity_type = f"type_{_token()}"
        active = await repo.create(_definition(entity_type=entity_type))
        inactive = await repo.create(_definition(entity_type=entity_type, is_active=False))

        active_rows = await repo.list_all(entity_type=entity_type, is_active=True)
        inactive_rows = await repo.list_all(entity_type=entity_type, is_active=False)
        all_rows = await repo.list_all(entity_type=entity_type)

        assert [r.id for r in active_rows] == [active.id]
        assert [r.id for r in inactive_rows] == [inactive.id]
        assert len(all_rows) == 2
        assert await repo.count(entity_type=entity_type, is_active=True) == 1
        assert await repo.count(entity_type=entity_type, is_active=False) == 1
        assert await repo.count(entity_type=entity_type) == 2

    async def test_search_matches_code_name_and_entity_type_case_insensitively(
        self, db_session: AsyncSession
    ) -> None:
        repo = WorkflowDefinitionRepositoryImpl(db_session)
        needle = _token()
        by_code = await repo.create(_definition(code=f"CODE{needle}X"))
        by_name = await repo.create(_definition(name=f"Named {needle.lower()} flow"))
        by_type = await repo.create(_definition(entity_type=f"kind_{needle}"))
        await repo.create(_definition())  # matches nothing

        rows = await repo.list_all(search=needle)

        assert {r.id for r in rows} == {by_code.id, by_name.id, by_type.id}
        assert await repo.count(search=needle) == 3

    async def test_search_ignores_surrounding_whitespace(
        self, db_session: AsyncSession
    ) -> None:
        repo = WorkflowDefinitionRepositoryImpl(db_session)
        needle = _token()
        created = await repo.create(_definition(code=f"CODE{needle}"))

        rows = await repo.list_all(search=f"  {needle}  ")

        assert [r.id for r in rows] == [created.id]

    async def test_filters_combine_with_and_and_count_mirrors_them(
        self, db_session: AsyncSession
    ) -> None:
        repo = WorkflowDefinitionRepositoryImpl(db_session)
        needle = _token()
        entity_type = f"type_{needle}"
        match = await repo.create(_definition(code=f"A{needle}", entity_type=entity_type))
        await repo.create(
            _definition(code=f"B{needle}", entity_type=entity_type, is_active=False)
        )
        await repo.create(_definition(code=f"C{needle}", entity_type=f"other_{needle}"))

        rows = await repo.list_all(search=needle, is_active=True, entity_type=entity_type)
        total = await repo.count(search=needle, is_active=True, entity_type=entity_type)

        assert [r.id for r in rows] == [match.id]
        assert total == 1

    async def test_no_match_gives_an_empty_list_and_a_zero_count(
        self, db_session: AsyncSession
    ) -> None:
        repo = WorkflowDefinitionRepositoryImpl(db_session)

        assert await repo.list_all(search=f"nothing-{_token()}") == []
        assert await repo.count(search=f"nothing-{_token()}") == 0


class TestGetDefinitionsByIds:
    async def test_empty_input_returns_an_empty_list(self, db_session: AsyncSession) -> None:
        repo = WorkflowDefinitionRepositoryImpl(db_session)

        assert await repo.get_definitions_by_ids([]) == []

    async def test_returns_only_the_requested_definitions(
        self, db_session: AsyncSession
    ) -> None:
        repo = WorkflowDefinitionRepositoryImpl(db_session)
        wanted_a = await repo.create(_definition())
        wanted_b = await repo.create(_definition())
        other = await repo.create(_definition())

        rows = await repo.get_definitions_by_ids([wanted_a.id, wanted_b.id])

        assert {r.id for r in rows} == {wanted_a.id, wanted_b.id}
        assert other.id not in {r.id for r in rows}

    async def test_duplicate_and_unknown_ids_are_tolerated(
        self, db_session: AsyncSession
    ) -> None:
        repo = WorkflowDefinitionRepositoryImpl(db_session)
        created = await repo.create(_definition())

        rows = await repo.get_definitions_by_ids([created.id, created.id, _MISSING_ID])

        assert [r.id for r in rows] == [created.id]


class TestStatuses:
    async def test_create_status_round_trips_every_field(
        self, db_session: AsyncSession
    ) -> None:
        repo = WorkflowDefinitionRepositoryImpl(db_session)
        definition = await repo.create(_definition())

        created = await repo.create_status(
            _status(
                definition.id,
                code="DRAFT",
                name="Draft",
                is_initial=True,
                is_terminal=True,
                sequence=7,
                created_by="alice",
                modified_by="bob",
            )
        )
        db_session.expire_all()
        fetched = await repo.get_status(created.id)

        assert created.id > 0
        assert fetched is not None
        assert fetched.id == created.id
        assert fetched.workflow_definition_id == definition.id
        assert fetched.code == "DRAFT"
        assert fetched.name == "Draft"
        assert fetched.is_initial is True
        assert fetched.is_terminal is True
        assert fetched.sequence == 7
        assert fetched.created_by == "alice"
        assert fetched.modified_by == "bob"
        assert fetched.created_date is not None

    async def test_status_defaults_are_persisted(self, db_session: AsyncSession) -> None:
        repo = WorkflowDefinitionRepositoryImpl(db_session)
        definition = await repo.create(_definition())

        created = await repo.create_status(_status(definition.id))
        db_session.expire_all()
        fetched = await repo.get_status(created.id)

        assert fetched is not None
        assert fetched.is_initial is False
        assert fetched.is_terminal is False
        assert fetched.sequence == 0

    async def test_get_status_returns_none_for_a_missing_id(
        self, db_session: AsyncSession
    ) -> None:
        repo = WorkflowDefinitionRepositoryImpl(db_session)

        assert await repo.get_status(_MISSING_ID) is None

    async def test_list_statuses_is_ordered_by_sequence_then_code(
        self, db_session: AsyncSession
    ) -> None:
        repo = WorkflowDefinitionRepositoryImpl(db_session)
        definition = await repo.create(_definition())
        await repo.create_status(_status(definition.id, code="LATE", sequence=5))
        await repo.create_status(_status(definition.id, code="TIE_B", sequence=2))
        await repo.create_status(_status(definition.id, code="EARLY", sequence=1))
        await repo.create_status(_status(definition.id, code="TIE_A", sequence=2))

        rows = await repo.list_statuses(definition.id)

        assert [r.code for r in rows] == ["EARLY", "TIE_A", "TIE_B", "LATE"]

    async def test_list_statuses_is_scoped_to_the_definition(
        self, db_session: AsyncSession
    ) -> None:
        repo = WorkflowDefinitionRepositoryImpl(db_session)
        first = await repo.create(_definition())
        second = await repo.create(_definition())
        mine = await repo.create_status(_status(first.id))
        await repo.create_status(_status(second.id))

        rows = await repo.list_statuses(first.id)

        assert [r.id for r in rows] == [mine.id]

    async def test_get_statuses_by_ids(self, db_session: AsyncSession) -> None:
        repo = WorkflowDefinitionRepositoryImpl(db_session)
        definition = await repo.create(_definition())
        wanted_a = await repo.create_status(_status(definition.id))
        wanted_b = await repo.create_status(_status(definition.id))
        other = await repo.create_status(_status(definition.id))

        rows = await repo.get_statuses_by_ids([wanted_a.id, wanted_b.id, wanted_a.id])

        assert {r.id for r in rows} == {wanted_a.id, wanted_b.id}
        assert other.id not in {r.id for r in rows}
        assert await repo.get_statuses_by_ids([]) == []

    async def test_update_status_persists_every_editable_field(
        self, db_session: AsyncSession
    ) -> None:
        repo = WorkflowDefinitionRepositoryImpl(db_session)
        definition = await repo.create(_definition())
        created = await repo.create_status(_status(definition.id))

        created.code = "RENAMED"
        created.name = "Renamed"
        created.is_initial = True
        created.is_terminal = True
        created.sequence = 9
        created.mark_modified("editor")
        updated = await repo.update_status(created)
        db_session.expire_all()
        fetched = await repo.get_status(created.id)

        assert updated.code == "RENAMED"
        assert fetched is not None
        assert fetched.code == "RENAMED"
        assert fetched.name == "Renamed"
        assert fetched.is_initial is True
        assert fetched.is_terminal is True
        assert fetched.sequence == 9
        assert fetched.modified_by == "editor"
        assert fetched.workflow_definition_id == definition.id

    async def test_update_status_of_a_missing_status_raises(
        self, db_session: AsyncSession
    ) -> None:
        repo = WorkflowDefinitionRepositoryImpl(db_session)
        definition = await repo.create(_definition())

        with pytest.raises(ValueError, match="not found"):
            await repo.update_status(_status(definition.id, id=_MISSING_ID))

    async def test_delete_status_removes_it_and_leaves_siblings(
        self, db_session: AsyncSession
    ) -> None:
        repo = WorkflowDefinitionRepositoryImpl(db_session)
        definition = await repo.create(_definition())
        dropped = await repo.create_status(_status(definition.id))
        kept = await repo.create_status(_status(definition.id))

        await repo.delete_status(dropped.id)

        assert await repo.get_status(dropped.id) is None
        assert await repo.get_status(kept.id) is not None

    async def test_delete_status_of_a_missing_status_is_silent(
        self, db_session: AsyncSession
    ) -> None:
        repo = WorkflowDefinitionRepositoryImpl(db_session)

        await repo.delete_status(_MISSING_ID)  # must not raise

    async def test_deleting_a_status_cascades_to_transitions_touching_it(
        self, db_session: AsyncSession
    ) -> None:
        repo = WorkflowDefinitionRepositoryImpl(db_session)
        definition, start, end = await _definition_with_two_statuses(repo)
        transition = await repo.create_transition(_transition(definition.id, start.id, end.id))

        await repo.delete_status(end.id)

        assert await repo.get_transition(transition.id) is None


class TestExistsStatusCode:
    async def test_is_scoped_to_the_definition(self, db_session: AsyncSession) -> None:
        repo = WorkflowDefinitionRepositoryImpl(db_session)
        first = await repo.create(_definition())
        second = await repo.create(_definition())
        await repo.create_status(_status(first.id, code="OPEN"))

        assert await repo.exists_status_code(first.id, "OPEN") is True
        assert await repo.exists_status_code(second.id, "OPEN") is False
        assert await repo.exists_status_code(first.id, "CLOSED") is False

    async def test_exclude_id_ignores_the_row_being_edited(
        self, db_session: AsyncSession
    ) -> None:
        repo = WorkflowDefinitionRepositoryImpl(db_session)
        definition = await repo.create(_definition())
        open_status = await repo.create_status(_status(definition.id, code="OPEN"))
        other = await repo.create_status(_status(definition.id, code="OTHER"))

        assert (
            await repo.exists_status_code(definition.id, "OPEN", exclude_id=open_status.id)
            is False
        )
        assert (
            await repo.exists_status_code(definition.id, "OPEN", exclude_id=other.id) is True
        )


class TestGetInitialStatus:
    async def test_returns_the_initial_status(self, db_session: AsyncSession) -> None:
        repo = WorkflowDefinitionRepositoryImpl(db_session)
        definition, start, _end = await _definition_with_two_statuses(repo)

        initial = await repo.get_initial_status(definition.id)

        assert initial is not None
        assert initial.id == start.id

    async def test_returns_none_when_no_status_is_initial(
        self, db_session: AsyncSession
    ) -> None:
        repo = WorkflowDefinitionRepositoryImpl(db_session)
        definition = await repo.create(_definition())
        await repo.create_status(_status(definition.id))

        assert await repo.get_initial_status(definition.id) is None

    async def test_returns_the_lowest_sequence_when_several_are_initial(
        self, db_session: AsyncSession
    ) -> None:
        repo = WorkflowDefinitionRepositoryImpl(db_session)
        definition = await repo.create(_definition())
        await repo.create_status(_status(definition.id, is_initial=True, sequence=5))
        first = await repo.create_status(_status(definition.id, is_initial=True, sequence=1))
        await repo.create_status(_status(definition.id, is_initial=True, sequence=3))

        initial = await repo.get_initial_status(definition.id)

        assert initial is not None
        assert initial.id == first.id

    async def test_ignores_initial_statuses_of_other_definitions(
        self, db_session: AsyncSession
    ) -> None:
        repo = WorkflowDefinitionRepositoryImpl(db_session)
        definition = await repo.create(_definition())
        other = await repo.create(_definition())
        await repo.create_status(_status(other.id, is_initial=True))

        assert await repo.get_initial_status(definition.id) is None


class TestTransitions:
    async def test_create_transition_round_trips_every_field(
        self, db_session: AsyncSession
    ) -> None:
        repo = WorkflowDefinitionRepositoryImpl(db_session)
        definition, start, end = await _definition_with_two_statuses(repo)

        created = await repo.create_transition(
            _transition(
                definition.id,
                start.id,
                end.id,
                action_code="APPROVE",
                action_type=WorkflowActionType.APPROVE,
                guard_expression="amount > 100",
                requires_comment=True,
                auto_execute=True,
                priority=4,
                created_by="alice",
                modified_by="bob",
            )
        )
        db_session.expire_all()
        fetched = await repo.get_transition(created.id)

        assert created.id > 0
        assert fetched is not None
        assert fetched.id == created.id
        assert fetched.workflow_definition_id == definition.id
        assert fetched.from_status_id == start.id
        assert fetched.to_status_id == end.id
        assert fetched.action_code == "APPROVE"
        assert fetched.action_type is WorkflowActionType.APPROVE
        assert fetched.guard_expression == "amount > 100"
        assert fetched.requires_comment is True
        assert fetched.auto_execute is True
        assert fetched.priority == 4
        assert fetched.created_by == "alice"
        assert fetched.modified_by == "bob"
        assert fetched.created_date is not None

    async def test_transition_defaults_and_null_guard_round_trip(
        self, db_session: AsyncSession
    ) -> None:
        repo = WorkflowDefinitionRepositoryImpl(db_session)
        definition, start, end = await _definition_with_two_statuses(repo)

        created = await repo.create_transition(_transition(definition.id, start.id, end.id))
        db_session.expire_all()
        fetched = await repo.get_transition(created.id)

        assert fetched is not None
        assert fetched.guard_expression is None
        assert fetched.action_type is WorkflowActionType.CUSTOM
        assert fetched.requires_comment is False
        assert fetched.auto_execute is False
        assert fetched.priority == 0

    @pytest.mark.parametrize("action_type", list(WorkflowActionType))
    async def test_every_action_type_round_trips_as_its_enum(
        self, db_session: AsyncSession, action_type: WorkflowActionType
    ) -> None:
        repo = WorkflowDefinitionRepositoryImpl(db_session)
        definition, start, end = await _definition_with_two_statuses(repo)

        created = await repo.create_transition(
            _transition(definition.id, start.id, end.id, action_type=action_type)
        )
        db_session.expire_all()
        fetched = await repo.get_transition(created.id)

        assert fetched is not None
        assert fetched.action_type is action_type

    async def test_get_transition_returns_none_for_a_missing_id(
        self, db_session: AsyncSession
    ) -> None:
        repo = WorkflowDefinitionRepositoryImpl(db_session)

        assert await repo.get_transition(_MISSING_ID) is None

    async def test_list_transitions_is_ordered_by_priority_then_action_code(
        self, db_session: AsyncSession
    ) -> None:
        repo = WorkflowDefinitionRepositoryImpl(db_session)
        definition, start, end = await _definition_with_two_statuses(repo)
        for code, priority in (("LATE", 9), ("TIE_B", 3), ("EARLY", 1), ("TIE_A", 3)):
            await repo.create_transition(
                _transition(
                    definition.id, start.id, end.id, action_code=code, priority=priority
                )
            )

        rows = await repo.list_transitions(definition.id)

        assert [r.action_code for r in rows] == ["EARLY", "TIE_A", "TIE_B", "LATE"]

    async def test_list_transitions_is_scoped_to_the_definition(
        self, db_session: AsyncSession
    ) -> None:
        repo = WorkflowDefinitionRepositoryImpl(db_session)
        definition, start, end = await _definition_with_two_statuses(repo)
        other, other_start, other_end = await _definition_with_two_statuses(repo)
        mine = await repo.create_transition(_transition(definition.id, start.id, end.id))
        await repo.create_transition(_transition(other.id, other_start.id, other_end.id))

        rows = await repo.list_transitions(definition.id)

        assert [r.id for r in rows] == [mine.id]

    async def test_list_transitions_from_narrows_to_one_source_status(
        self, db_session: AsyncSession
    ) -> None:
        repo = WorkflowDefinitionRepositoryImpl(db_session)
        definition, start, end = await _definition_with_two_statuses(repo)
        outgoing = await repo.create_transition(
            _transition(definition.id, start.id, end.id, action_code="GO")
        )
        await repo.create_transition(
            _transition(definition.id, end.id, start.id, action_code="BACK")
        )

        rows = await repo.list_transitions_from(definition.id, start.id)

        assert [r.id for r in rows] == [outgoing.id]

    async def test_list_transitions_from_is_ordered_by_priority_then_action_code(
        self, db_session: AsyncSession
    ) -> None:
        repo = WorkflowDefinitionRepositoryImpl(db_session)
        definition, start, end = await _definition_with_two_statuses(repo)
        for code, priority in (("B", 2), ("C", 1), ("A", 2)):
            await repo.create_transition(
                _transition(
                    definition.id, start.id, end.id, action_code=code, priority=priority
                )
            )

        rows = await repo.list_transitions_from(definition.id, start.id)

        assert [r.action_code for r in rows] == ["C", "A", "B"]

    async def test_find_transition_matches_on_definition_source_and_action(
        self, db_session: AsyncSession
    ) -> None:
        repo = WorkflowDefinitionRepositoryImpl(db_session)
        definition, start, end = await _definition_with_two_statuses(repo)
        created = await repo.create_transition(
            _transition(definition.id, start.id, end.id, action_code="SUBMIT")
        )

        found = await repo.find_transition(definition.id, start.id, "SUBMIT")

        assert found is not None
        assert found.id == created.id
        assert await repo.find_transition(definition.id, start.id, "NOPE") is None
        assert await repo.find_transition(definition.id, end.id, "SUBMIT") is None

    async def test_exists_transition_is_scoped_by_definition_source_and_action(
        self, db_session: AsyncSession
    ) -> None:
        repo = WorkflowDefinitionRepositoryImpl(db_session)
        definition, start, end = await _definition_with_two_statuses(repo)
        other, _other_start, _other_end = await _definition_with_two_statuses(repo)
        await repo.create_transition(
            _transition(definition.id, start.id, end.id, action_code="SUBMIT")
        )

        assert await repo.exists_transition(definition.id, start.id, "SUBMIT") is True
        assert await repo.exists_transition(definition.id, start.id, "OTHER") is False
        assert await repo.exists_transition(definition.id, end.id, "SUBMIT") is False
        assert await repo.exists_transition(other.id, start.id, "SUBMIT") is False

    async def test_the_same_action_code_is_allowed_from_different_statuses(
        self, db_session: AsyncSession
    ) -> None:
        repo = WorkflowDefinitionRepositoryImpl(db_session)
        definition, start, end = await _definition_with_two_statuses(repo)

        await repo.create_transition(
            _transition(definition.id, start.id, end.id, action_code="NEXT")
        )
        await repo.create_transition(
            _transition(definition.id, end.id, start.id, action_code="NEXT")
        )

        assert len(await repo.list_transitions(definition.id)) == 2

    async def test_delete_transition_removes_only_that_transition(
        self, db_session: AsyncSession
    ) -> None:
        repo = WorkflowDefinitionRepositoryImpl(db_session)
        definition, start, end = await _definition_with_two_statuses(repo)
        dropped = await repo.create_transition(_transition(definition.id, start.id, end.id))
        kept = await repo.create_transition(_transition(definition.id, end.id, start.id))

        await repo.delete_transition(dropped.id)

        assert await repo.get_transition(dropped.id) is None
        assert await repo.get_transition(kept.id) is not None

    async def test_delete_transition_of_a_missing_id_is_silent(
        self, db_session: AsyncSession
    ) -> None:
        repo = WorkflowDefinitionRepositoryImpl(db_session)

        await repo.delete_transition(_MISSING_ID)  # must not raise


class TestStatusDependencyCounts:
    async def test_transition_count_covers_both_source_and_target(
        self, db_session: AsyncSession
    ) -> None:
        repo = WorkflowDefinitionRepositoryImpl(db_session)
        definition, start, end = await _definition_with_two_statuses(repo)
        extra = await repo.create_status(_status(definition.id))
        await repo.create_transition(
            _transition(definition.id, start.id, end.id, action_code="FORWARD")
        )
        await repo.create_transition(
            _transition(definition.id, end.id, start.id, action_code="BACK")
        )
        await repo.create_transition(
            _transition(definition.id, start.id, start.id, action_code="STAY")
        )

        assert await repo.count_transitions_touching_status(start.id) == 3
        assert await repo.count_transitions_touching_status(end.id) == 2
        assert await repo.count_transitions_touching_status(extra.id) == 0

    async def test_instance_count_counts_instances_sitting_in_the_status(
        self, db_session: AsyncSession
    ) -> None:
        repo = WorkflowDefinitionRepositoryImpl(db_session)
        definition, start, end = await _definition_with_two_statuses(repo)
        user = await _make_user(db_session)
        for entity_id in (1, 2):
            db_session.add(
                WorkflowInstanceModel(
                    workflow_definition_id=definition.id,
                    entity_type=definition.entity_type,
                    entity_id=entity_id,
                    current_status_id=start.id,
                    initiated_by=user.id,
                    created_by="test",
                    modified_by="test",
                )
            )
        await db_session.flush()

        assert await repo.count_instances_in_status(start.id) == 2
        assert await repo.count_instances_in_status(end.id) == 0
