"""
Workflow service tests.

`WorkflowService` does two jobs. The configuration half (definitions, states,
transitions) enforces the rules that give callers a 409 with a reason instead of a
database constraint error: uniqueness, at most one initial state, no state that is both
initial and terminal, delete guards, and transition endpoints that must belong to the
same definition. The runtime half maps what `WorkflowEngine` returns into response DTOs
and resolves definitions and states in batches. The repositories only run queries, so
these tests pin both halves down against the shared in-memory fakes.
"""

from datetime import UTC, datetime, timedelta
from typing import Any

import pytest
from workflow_fakes import (
    FakeApprovalMatrixRepository,
    FakeRoleAssignmentRepository,
    FakeWorkflowDefinitionRepository,
    FakeWorkflowInstanceRepository,
    WorkflowScenario,
)

from src.api.v1.schemas.workflow_schema import (
    WorkflowActionRequest,
    WorkflowDefinitionCreate,
    WorkflowDefinitionResponse,
    WorkflowDefinitionUpdate,
    WorkflowStartRequest,
    WorkflowStatusCreate,
    WorkflowStatusResponse,
    WorkflowStatusUpdate,
    WorkflowTransitionCreate,
    WorkflowTransitionResponse,
)
from src.application.services.workflow_service import WorkflowService
from src.domain.entities.user import User
from src.domain.entities.workflow import WorkflowHistoryEntry, WorkflowInstance
from src.domain.enums.workflow_enums import ApprovalTaskStatus, WorkflowActionType
from src.domain.exceptions.domain_exceptions import (
    BusinessRuleViolationError,
    DuplicateEntityError,
    EntityNotFoundError,
)

# ─────────────────────────── Fixtures and helpers ───────────────────────────


@pytest.fixture
def definitions() -> FakeWorkflowDefinitionRepository:
    return FakeWorkflowDefinitionRepository()


@pytest.fixture
def instances() -> FakeWorkflowInstanceRepository:
    return FakeWorkflowInstanceRepository()


@pytest.fixture
def service(
    definitions: FakeWorkflowDefinitionRepository,
    instances: FakeWorkflowInstanceRepository,
) -> WorkflowService:
    """A service over empty fakes, for the configuration tests."""
    return WorkflowService(
        definitions,
        instances,
        FakeApprovalMatrixRepository(),
        FakeRoleAssignmentRepository(),
    )


@pytest.fixture
def actor() -> User:
    return User(id=1, username="alice")


@pytest.fixture
def runtime(scenario: WorkflowScenario) -> WorkflowService:
    """A service over the seeded compliance approval workflow, for runtime tests."""
    return WorkflowService(
        scenario.definitions, scenario.instances, scenario.matrices, scenario.roles
    )


@pytest.fixture
def maker(scenario: WorkflowScenario) -> User:
    return User(id=scenario.maker, username="maker")


async def new_definition(
    service: WorkflowService,
    actor: User,
    *,
    code: str = "WF_ONE",
    name: str | None = None,
    entity_type: str = "task",
    **extra: Any,
) -> WorkflowDefinitionResponse:
    return await service.create_definition(
        WorkflowDefinitionCreate(
            code=code,
            name=name or f"Workflow {code}",
            entity_type=entity_type,
            **extra,
        ),
        actor,
    )


async def new_status(
    service: WorkflowService,
    actor: User,
    definition_id: int,
    code: str,
    *,
    initial: bool = False,
    terminal: bool = False,
    sequence: int = 0,
) -> WorkflowStatusResponse:
    return await service.create_status(
        definition_id,
        WorkflowStatusCreate(
            code=code,
            name=code.title(),
            is_initial=initial,
            is_terminal=terminal,
            sequence=sequence,
        ),
        actor,
    )


async def new_transition(
    service: WorkflowService,
    actor: User,
    definition_id: int,
    from_status_id: int,
    to_status_id: int,
    action_code: str = "GO",
    **extra: Any,
) -> WorkflowTransitionResponse:
    return await service.create_transition(
        definition_id,
        WorkflowTransitionCreate(
            from_status_id=from_status_id,
            to_status_id=to_status_id,
            action_code=action_code,
            **extra,
        ),
        actor,
    )


# ═══════════════════════════ Definitions ═══════════════════════════


class TestCreateDefinition:
    async def test_creates_version_one_with_actor_audit_fields(
        self,
        service: WorkflowService,
        definitions: FakeWorkflowDefinitionRepository,
        actor: User,
    ) -> None:
        response = await new_definition(
            service, actor, code="RETURN_FILING", description="Maker-checker"
        )

        assert response.id != 0
        assert response.code == "RETURN_FILING"
        assert response.version == 1
        assert response.description == "Maker-checker"
        assert response.is_active is True
        assert response.created_by == "alice"
        assert response.modified_by == "alice"
        assert response.id in definitions.definitions

    async def test_is_active_false_is_honoured(
        self, service: WorkflowService, actor: User
    ) -> None:
        response = await new_definition(service, actor, is_active=False)

        assert response.is_active is False

    async def test_duplicate_code_is_rejected(
        self,
        service: WorkflowService,
        definitions: FakeWorkflowDefinitionRepository,
        actor: User,
    ) -> None:
        await new_definition(service, actor, code="WF_ONE", name="First")

        with pytest.raises(DuplicateEntityError) as exc_info:
            await new_definition(service, actor, code="WF_ONE", name="Second")

        assert (exc_info.value.entity, exc_info.value.field) == (
            "WorkflowDefinition",
            "code",
        )
        assert len(definitions.definitions) == 1

    async def test_duplicate_name_is_rejected(
        self,
        service: WorkflowService,
        definitions: FakeWorkflowDefinitionRepository,
        actor: User,
    ) -> None:
        await new_definition(service, actor, code="WF_ONE", name="Same name")

        with pytest.raises(DuplicateEntityError) as exc_info:
            await new_definition(service, actor, code="WF_TWO", name="Same name")

        assert (exc_info.value.entity, exc_info.value.field) == (
            "WorkflowDefinition",
            "name",
        )
        assert len(definitions.definitions) == 1


class TestGetDefinition:
    async def test_returns_the_definition(
        self, service: WorkflowService, actor: User
    ) -> None:
        created = await new_definition(service, actor)

        response = await service.get_definition(created.id)

        assert response.id == created.id
        assert response.code == "WF_ONE"

    async def test_unknown_definition_is_rejected(self, service: WorkflowService) -> None:
        with pytest.raises(EntityNotFoundError, match="WorkflowDefinition '999999'"):
            await service.get_definition(999_999)


class TestGetDefinitionDetail:
    async def test_returns_the_definition_with_its_states_and_transitions(
        self, service: WorkflowService, actor: User
    ) -> None:
        definition = await new_definition(service, actor)
        draft = await new_status(
            service, actor, definition.id, "DRAFT", initial=True, sequence=10
        )
        done = await new_status(
            service, actor, definition.id, "DONE", terminal=True, sequence=20
        )
        await new_transition(service, actor, definition.id, draft.id, done.id, "FINISH")

        detail = await service.get_definition_detail(definition.id)

        assert detail.definition.id == definition.id
        assert [s.code for s in detail.statuses] == ["DRAFT", "DONE"]
        assert [t.action_code for t in detail.transitions] == ["FINISH"]

    async def test_other_definitions_states_are_not_included(
        self, service: WorkflowService, actor: User
    ) -> None:
        mine = await new_definition(service, actor, code="MINE")
        theirs = await new_definition(service, actor, code="THEIRS")
        await new_status(service, actor, theirs.id, "THEIR_STATE")

        detail = await service.get_definition_detail(mine.id)

        assert detail.statuses == []
        assert detail.transitions == []

    async def test_unknown_definition_is_rejected(self, service: WorkflowService) -> None:
        with pytest.raises(EntityNotFoundError):
            await service.get_definition_detail(999_999)


class TestListDefinitions:
    async def test_returns_definitions_ordered_by_code_with_paging_echo(
        self, service: WorkflowService, actor: User
    ) -> None:
        await new_definition(service, actor, code="BETA")
        await new_definition(service, actor, code="ALPHA")

        result = await service.list_definitions()

        assert [d.code for d in result.definitions] == ["ALPHA", "BETA"]
        assert (result.total, result.skip, result.limit) == (2, 0, 100)

    async def test_total_counts_all_matches_not_just_the_page(
        self, service: WorkflowService, actor: User
    ) -> None:
        for code in ("A1", "A2", "A3", "A4"):
            await new_definition(service, actor, code=code)

        result = await service.list_definitions(skip=1, limit=2)

        assert [d.code for d in result.definitions] == ["A2", "A3"]
        assert result.total == 4

    async def test_search_filter_reaches_the_repository(
        self, service: WorkflowService, actor: User
    ) -> None:
        await new_definition(service, actor, code="ALPHA")
        await new_definition(service, actor, code="BETA")

        result = await service.list_definitions(search="alp")

        assert [d.code for d in result.definitions] == ["ALPHA"]
        assert result.total == 1

    async def test_is_active_filter_reaches_the_repository(
        self, service: WorkflowService, actor: User
    ) -> None:
        await new_definition(service, actor, code="ON")
        await new_definition(service, actor, code="OFF", is_active=False)

        result = await service.list_definitions(is_active=False)

        assert [d.code for d in result.definitions] == ["OFF"]
        assert result.total == 1

    async def test_entity_type_filter_reaches_the_repository(
        self, service: WorkflowService, actor: User
    ) -> None:
        await new_definition(service, actor, code="TASKS", entity_type="task")
        await new_definition(service, actor, code="INVOICES", entity_type="invoice")

        result = await service.list_definitions(entity_type="invoice")

        assert [d.code for d in result.definitions] == ["INVOICES"]
        assert result.total == 1


class TestUpdateDefinition:
    async def test_unknown_definition_is_rejected(
        self, service: WorkflowService, actor: User
    ) -> None:
        with pytest.raises(EntityNotFoundError):
            await service.update_definition(
                999_999, WorkflowDefinitionUpdate(name="Whatever"), actor
            )

    async def test_code_alone_changes_only_the_code(
        self, service: WorkflowService, actor: User
    ) -> None:
        created = await new_definition(
            service, actor, name="Original", entity_type="invoice", description="d"
        )

        response = await service.update_definition(
            created.id, WorkflowDefinitionUpdate(code="NEW_CODE"), actor
        )

        assert response.code == "NEW_CODE"
        assert response.name == "Original"
        assert response.entity_type == "invoice"
        assert response.description == "d"
        assert response.is_active is True

    async def test_renaming_the_code_onto_another_definitions_code_is_rejected(
        self, service: WorkflowService, actor: User
    ) -> None:
        await new_definition(service, actor, code="TAKEN")
        mine = await new_definition(service, actor, code="MINE")

        with pytest.raises(DuplicateEntityError) as exc_info:
            await service.update_definition(
                mine.id, WorkflowDefinitionUpdate(code="TAKEN"), actor
            )

        assert exc_info.value.field == "code"
        assert (await service.get_definition(mine.id)).code == "MINE"

    async def test_resubmitting_the_current_code_is_not_a_conflict(
        self, service: WorkflowService, actor: User
    ) -> None:
        mine = await new_definition(service, actor, code="MINE")

        response = await service.update_definition(
            mine.id, WorkflowDefinitionUpdate(code="MINE", description="edited"), actor
        )

        assert response.code == "MINE"
        assert response.description == "edited"

    async def test_name_alone_changes_only_the_name(
        self, service: WorkflowService, actor: User
    ) -> None:
        created = await new_definition(service, actor, code="WF_ONE", entity_type="invoice")

        response = await service.update_definition(
            created.id, WorkflowDefinitionUpdate(name="New name"), actor
        )

        assert response.name == "New name"
        assert response.code == "WF_ONE"
        assert response.entity_type == "invoice"

    async def test_renaming_onto_another_definitions_name_is_rejected(
        self, service: WorkflowService, actor: User
    ) -> None:
        await new_definition(service, actor, code="OTHER", name="Taken name")
        mine = await new_definition(service, actor, code="MINE", name="My name")

        with pytest.raises(DuplicateEntityError) as exc_info:
            await service.update_definition(
                mine.id, WorkflowDefinitionUpdate(name="Taken name"), actor
            )

        assert exc_info.value.field == "name"
        assert (await service.get_definition(mine.id)).name == "My name"

    async def test_resubmitting_the_current_name_is_not_a_conflict(
        self, service: WorkflowService, actor: User
    ) -> None:
        mine = await new_definition(service, actor, code="MINE", name="My name")

        response = await service.update_definition(
            mine.id, WorkflowDefinitionUpdate(name="My name"), actor
        )

        assert response.name == "My name"

    async def test_entity_type_alone_changes_only_the_entity_type(
        self, service: WorkflowService, actor: User
    ) -> None:
        created = await new_definition(service, actor, name="Original")

        response = await service.update_definition(
            created.id, WorkflowDefinitionUpdate(entity_type="invoice"), actor
        )

        assert response.entity_type == "invoice"
        assert response.name == "Original"
        assert response.code == "WF_ONE"

    async def test_description_alone_changes_only_the_description(
        self, service: WorkflowService, actor: User
    ) -> None:
        created = await new_definition(service, actor, description="old")

        response = await service.update_definition(
            created.id, WorkflowDefinitionUpdate(description="new"), actor
        )

        assert response.description == "new"
        assert response.code == "WF_ONE"

    async def test_empty_description_is_applied_not_mistaken_for_omitted(
        self, service: WorkflowService, actor: User
    ) -> None:
        created = await new_definition(service, actor, description="something")

        response = await service.update_definition(
            created.id, WorkflowDefinitionUpdate(description=""), actor
        )

        assert response.description == ""

    async def test_is_active_false_deactivates_without_touching_other_fields(
        self, service: WorkflowService, actor: User
    ) -> None:
        created = await new_definition(service, actor, name="Original")

        response = await service.update_definition(
            created.id, WorkflowDefinitionUpdate(is_active=False), actor
        )

        assert response.is_active is False
        assert response.name == "Original"

    async def test_update_is_persisted_and_stamps_the_actor(
        self,
        service: WorkflowService,
        definitions: FakeWorkflowDefinitionRepository,
        actor: User,
    ) -> None:
        created = await new_definition(service, actor)

        await service.update_definition(
            created.id, WorkflowDefinitionUpdate(is_active=False), User(id=2, username="bob")
        )

        stored = definitions.definitions[created.id]
        assert stored.is_active is False
        assert stored.modified_by == "bob"
        assert stored.version == 1


class TestDeleteDefinition:
    async def test_deletes_a_definition_without_instances(
        self,
        service: WorkflowService,
        definitions: FakeWorkflowDefinitionRepository,
        actor: User,
    ) -> None:
        created = await new_definition(service, actor)

        await service.delete_definition(created.id)

        assert created.id not in definitions.definitions

    async def test_unknown_definition_is_rejected(self, service: WorkflowService) -> None:
        with pytest.raises(EntityNotFoundError):
            await service.delete_definition(999_999)

    async def test_definition_with_instances_cannot_be_deleted(
        self,
        service: WorkflowService,
        definitions: FakeWorkflowDefinitionRepository,
        instances: FakeWorkflowInstanceRepository,
        actor: User,
    ) -> None:
        created = await new_definition(service, actor)
        draft = await new_status(service, actor, created.id, "DRAFT", initial=True)
        await instances.create(
            WorkflowInstance(
                workflow_definition_id=created.id,
                entity_type="task",
                entity_id=1,
                current_status_id=draft.id,
                initiated_by=actor.id,
            )
        )

        with pytest.raises(BusinessRuleViolationError, match=r"1 instance\(s\) reference it"):
            await service.delete_definition(created.id)

        assert created.id in definitions.definitions

    async def test_instances_of_another_definition_do_not_block_deletion(
        self,
        service: WorkflowService,
        definitions: FakeWorkflowDefinitionRepository,
        instances: FakeWorkflowInstanceRepository,
        actor: User,
    ) -> None:
        mine = await new_definition(service, actor, code="MINE")
        theirs = await new_definition(service, actor, code="THEIRS")
        await instances.create(
            WorkflowInstance(
                workflow_definition_id=theirs.id,
                entity_type="task",
                entity_id=1,
                current_status_id=1,
                initiated_by=actor.id,
            )
        )

        await service.delete_definition(mine.id)

        assert mine.id not in definitions.definitions

    async def test_completed_instances_still_block_deletion(
        self,
        service: WorkflowService,
        instances: FakeWorkflowInstanceRepository,
        actor: User,
    ) -> None:
        created = await new_definition(service, actor)
        await instances.create(
            WorkflowInstance(
                workflow_definition_id=created.id,
                entity_type="task",
                entity_id=1,
                current_status_id=1,
                initiated_by=actor.id,
                completed_at=datetime.now(UTC),
            )
        )

        with pytest.raises(BusinessRuleViolationError, match="Deactivate it instead"):
            await service.delete_definition(created.id)


# ═══════════════════════════ Statuses ═══════════════════════════


class TestListStatuses:
    async def test_returns_the_definitions_states_ordered_by_sequence(
        self, service: WorkflowService, actor: User
    ) -> None:
        definition = await new_definition(service, actor)
        await new_status(service, actor, definition.id, "SECOND", sequence=20)
        await new_status(service, actor, definition.id, "FIRST", sequence=10)

        result = await service.list_statuses(definition.id)

        assert [s.code for s in result] == ["FIRST", "SECOND"]

    async def test_unknown_definition_is_rejected(self, service: WorkflowService) -> None:
        with pytest.raises(EntityNotFoundError):
            await service.list_statuses(999_999)


class TestCreateStatus:
    async def test_creates_a_state_with_actor_audit_fields(
        self,
        service: WorkflowService,
        definitions: FakeWorkflowDefinitionRepository,
        actor: User,
    ) -> None:
        definition = await new_definition(service, actor)

        response = await new_status(
            service, actor, definition.id, "REVIEW", sequence=30
        )

        assert response.id != 0
        assert response.workflow_definition_id == definition.id
        assert (response.code, response.name, response.sequence) == ("REVIEW", "Review", 30)
        assert (response.is_initial, response.is_terminal) == (False, False)
        assert definitions.statuses[response.id].created_by == "alice"

    async def test_unknown_definition_is_rejected(
        self, service: WorkflowService, actor: User
    ) -> None:
        with pytest.raises(EntityNotFoundError):
            await new_status(service, actor, 999_999, "DRAFT")

    async def test_a_state_cannot_be_both_initial_and_terminal(
        self,
        service: WorkflowService,
        definitions: FakeWorkflowDefinitionRepository,
        actor: User,
    ) -> None:
        definition = await new_definition(service, actor)

        with pytest.raises(
            BusinessRuleViolationError, match="cannot be both initial and terminal"
        ):
            await new_status(
                service, actor, definition.id, "ODD", initial=True, terminal=True
            )

        assert definitions.statuses == {}

    async def test_duplicate_code_within_a_definition_is_rejected(
        self, service: WorkflowService, actor: User
    ) -> None:
        definition = await new_definition(service, actor)
        await new_status(service, actor, definition.id, "REVIEW")

        with pytest.raises(DuplicateEntityError) as exc_info:
            await new_status(service, actor, definition.id, "REVIEW")

        assert (exc_info.value.entity, exc_info.value.field) == ("WorkflowStatus", "code")

    async def test_the_same_code_is_allowed_in_a_different_definition(
        self, service: WorkflowService, actor: User
    ) -> None:
        first = await new_definition(service, actor, code="FIRST")
        second = await new_definition(service, actor, code="SECOND")
        await new_status(service, actor, first.id, "REVIEW")

        created = await new_status(service, actor, second.id, "REVIEW")

        assert created.workflow_definition_id == second.id

    async def test_the_first_initial_state_is_accepted(
        self, service: WorkflowService, actor: User
    ) -> None:
        definition = await new_definition(service, actor)

        created = await new_status(service, actor, definition.id, "DRAFT", initial=True)

        assert created.is_initial is True

    async def test_a_second_initial_state_is_rejected_naming_the_existing_one(
        self,
        service: WorkflowService,
        definitions: FakeWorkflowDefinitionRepository,
        actor: User,
    ) -> None:
        definition = await new_definition(service, actor)
        await new_status(service, actor, definition.id, "DRAFT", initial=True)

        with pytest.raises(
            BusinessRuleViolationError, match="already has an initial state \\('DRAFT'\\)"
        ):
            await new_status(service, actor, definition.id, "START", initial=True)

        assert len(definitions.statuses) == 1

    async def test_an_initial_state_in_another_definition_does_not_conflict(
        self, service: WorkflowService, actor: User
    ) -> None:
        first = await new_definition(service, actor, code="FIRST")
        second = await new_definition(service, actor, code="SECOND")
        await new_status(service, actor, first.id, "DRAFT", initial=True)

        created = await new_status(service, actor, second.id, "DRAFT", initial=True)

        assert created.is_initial is True

    async def test_non_initial_states_can_be_added_after_the_initial_one(
        self, service: WorkflowService, actor: User
    ) -> None:
        definition = await new_definition(service, actor)
        await new_status(service, actor, definition.id, "DRAFT", initial=True)

        review = await new_status(service, actor, definition.id, "REVIEW")
        done = await new_status(service, actor, definition.id, "DONE", terminal=True)

        assert review.is_initial is False
        assert done.is_terminal is True


class TestUpdateStatus:
    async def _setup(
        self, service: WorkflowService, actor: User
    ) -> tuple[WorkflowDefinitionResponse, WorkflowStatusResponse]:
        definition = await new_definition(service, actor)
        status = await new_status(
            service, actor, definition.id, "REVIEW", sequence=20
        )
        return definition, status

    async def test_unknown_status_is_rejected(
        self, service: WorkflowService, actor: User
    ) -> None:
        with pytest.raises(EntityNotFoundError, match="WorkflowStatus"):
            await service.update_status(999_999, WorkflowStatusUpdate(name="X"), actor)

    async def test_name_alone_changes_only_the_name(
        self, service: WorkflowService, actor: User
    ) -> None:
        _, status = await self._setup(service, actor)

        response = await service.update_status(
            status.id, WorkflowStatusUpdate(name="In review"), actor
        )

        assert response.name == "In review"
        assert response.code == "REVIEW"
        assert response.sequence == 20
        assert (response.is_initial, response.is_terminal) == (False, False)

    async def test_sequence_alone_changes_only_the_sequence(
        self, service: WorkflowService, actor: User
    ) -> None:
        _, status = await self._setup(service, actor)

        response = await service.update_status(
            status.id, WorkflowStatusUpdate(sequence=5), actor
        )

        assert response.sequence == 5
        assert response.name == "Review"

    async def test_sequence_zero_is_applied_not_mistaken_for_omitted(
        self, service: WorkflowService, actor: User
    ) -> None:
        _, status = await self._setup(service, actor)

        response = await service.update_status(
            status.id, WorkflowStatusUpdate(sequence=0), actor
        )

        assert response.sequence == 0

    async def test_code_alone_changes_only_the_code(
        self, service: WorkflowService, actor: User
    ) -> None:
        _, status = await self._setup(service, actor)

        response = await service.update_status(
            status.id, WorkflowStatusUpdate(code="CHECKING"), actor
        )

        assert response.code == "CHECKING"
        assert response.name == "Review"
        assert response.sequence == 20

    async def test_code_clashing_with_a_sibling_state_is_rejected(
        self, service: WorkflowService, actor: User
    ) -> None:
        definition, status = await self._setup(service, actor)
        await new_status(service, actor, definition.id, "DONE")

        with pytest.raises(DuplicateEntityError) as exc_info:
            await service.update_status(status.id, WorkflowStatusUpdate(code="DONE"), actor)

        assert (exc_info.value.entity, exc_info.value.field) == ("WorkflowStatus", "code")

    async def test_code_clash_is_scoped_to_the_same_definition(
        self, service: WorkflowService, actor: User
    ) -> None:
        _, status = await self._setup(service, actor)
        other = await new_definition(service, actor, code="OTHER")
        await new_status(service, actor, other.id, "DONE")

        response = await service.update_status(
            status.id, WorkflowStatusUpdate(code="DONE"), actor
        )

        assert response.code == "DONE"

    async def test_resubmitting_the_current_code_is_not_a_conflict(
        self, service: WorkflowService, actor: User
    ) -> None:
        _, status = await self._setup(service, actor)

        response = await service.update_status(
            status.id, WorkflowStatusUpdate(code="REVIEW", name="Renamed"), actor
        )

        assert response.code == "REVIEW"
        assert response.name == "Renamed"

    async def test_is_terminal_alone_marks_a_state_terminal(
        self, service: WorkflowService, actor: User
    ) -> None:
        _, status = await self._setup(service, actor)

        response = await service.update_status(
            status.id, WorkflowStatusUpdate(is_terminal=True), actor
        )

        assert response.is_terminal is True
        assert response.is_initial is False

    async def test_is_initial_alone_promotes_a_state_when_none_exists(
        self, service: WorkflowService, actor: User
    ) -> None:
        _, status = await self._setup(service, actor)

        response = await service.update_status(
            status.id, WorkflowStatusUpdate(is_initial=True), actor
        )

        assert response.is_initial is True

    async def test_promoting_a_state_while_another_is_initial_is_rejected(
        self, service: WorkflowService, actor: User
    ) -> None:
        definition, status = await self._setup(service, actor)
        await new_status(service, actor, definition.id, "DRAFT", initial=True)

        with pytest.raises(
            BusinessRuleViolationError, match="already has an initial state \\('DRAFT'\\)"
        ):
            await service.update_status(
                status.id, WorkflowStatusUpdate(is_initial=True), actor
            )

        stored = {s.code: s for s in await service.list_statuses(definition.id)}
        assert stored["REVIEW"].is_initial is False
        assert stored["DRAFT"].is_initial is True

    async def test_resubmitting_the_initial_flag_on_the_current_initial_state_is_fine(
        self, service: WorkflowService, actor: User
    ) -> None:
        definition = await new_definition(service, actor)
        draft = await new_status(service, actor, definition.id, "DRAFT", initial=True)

        response = await service.update_status(
            draft.id, WorkflowStatusUpdate(is_initial=True, name="Start"), actor
        )

        assert response.is_initial is True
        assert response.name == "Start"

    async def test_the_initial_flag_can_be_cleared(
        self, service: WorkflowService, actor: User
    ) -> None:
        definition = await new_definition(service, actor)
        draft = await new_status(service, actor, definition.id, "DRAFT", initial=True)

        response = await service.update_status(
            draft.id, WorkflowStatusUpdate(is_initial=False), actor
        )

        assert response.is_initial is False

    async def test_clearing_the_initial_flag_lets_another_state_take_it(
        self, service: WorkflowService, actor: User
    ) -> None:
        definition = await new_definition(service, actor)
        draft = await new_status(service, actor, definition.id, "DRAFT", initial=True)
        review = await new_status(service, actor, definition.id, "REVIEW")

        await service.update_status(draft.id, WorkflowStatusUpdate(is_initial=False), actor)
        response = await service.update_status(
            review.id, WorkflowStatusUpdate(is_initial=True), actor
        )

        assert response.is_initial is True

    async def test_making_an_initial_state_terminal_is_rejected(
        self, service: WorkflowService, actor: User
    ) -> None:
        definition = await new_definition(service, actor)
        draft = await new_status(service, actor, definition.id, "DRAFT", initial=True)

        with pytest.raises(
            BusinessRuleViolationError, match="cannot be both initial and terminal"
        ):
            await service.update_status(
                draft.id, WorkflowStatusUpdate(is_terminal=True), actor
            )

    async def test_making_a_terminal_state_initial_is_rejected(
        self, service: WorkflowService, actor: User
    ) -> None:
        definition = await new_definition(service, actor)
        done = await new_status(service, actor, definition.id, "DONE", terminal=True)

        with pytest.raises(
            BusinessRuleViolationError, match="cannot be both initial and terminal"
        ):
            await service.update_status(
                done.id, WorkflowStatusUpdate(is_initial=True), actor
            )

    async def test_swapping_initial_for_terminal_in_one_update_is_allowed(
        self, service: WorkflowService, actor: User
    ) -> None:
        definition = await new_definition(service, actor)
        draft = await new_status(service, actor, definition.id, "DRAFT", initial=True)

        response = await service.update_status(
            draft.id, WorkflowStatusUpdate(is_initial=False, is_terminal=True), actor
        )

        assert (response.is_initial, response.is_terminal) == (False, True)

    async def test_a_rejected_update_changes_nothing(
        self, service: WorkflowService, actor: User
    ) -> None:
        definition = await new_definition(service, actor)
        draft = await new_status(service, actor, definition.id, "DRAFT", initial=True)

        with pytest.raises(BusinessRuleViolationError):
            await service.update_status(
                draft.id,
                WorkflowStatusUpdate(name="Changed", is_terminal=True),
                actor,
            )

        (stored,) = await service.list_statuses(definition.id)
        assert stored.name == "Draft"
        assert stored.is_terminal is False

    async def test_update_is_persisted_and_stamps_the_actor(
        self,
        service: WorkflowService,
        definitions: FakeWorkflowDefinitionRepository,
        actor: User,
    ) -> None:
        _, status = await self._setup(service, actor)

        await service.update_status(
            status.id, WorkflowStatusUpdate(name="Persisted"), User(id=2, username="bob")
        )

        assert definitions.statuses[status.id].name == "Persisted"
        assert definitions.statuses[status.id].modified_by == "bob"

    @pytest.mark.xfail(
        strict=True,
        reason=(
            "Suspected bug: the module states 'no transition may leave a terminal "
            "state' and create_transition enforces it, but update_status lets a state "
            "that already has outgoing transitions be marked terminal, leaving a "
            "terminal state with transitions leaving it."
        ),
    )
    async def test_a_state_with_outgoing_transitions_cannot_be_made_terminal(
        self, service: WorkflowService, actor: User
    ) -> None:
        definition = await new_definition(service, actor)
        draft = await new_status(service, actor, definition.id, "DRAFT", initial=True)
        review = await new_status(service, actor, definition.id, "REVIEW")
        await new_transition(service, actor, definition.id, review.id, draft.id, "BACK")

        with pytest.raises(BusinessRuleViolationError):
            await service.update_status(
                review.id, WorkflowStatusUpdate(is_terminal=True), actor
            )


class TestDeleteStatus:
    async def test_deletes_an_unused_state(
        self,
        service: WorkflowService,
        definitions: FakeWorkflowDefinitionRepository,
        actor: User,
    ) -> None:
        definition = await new_definition(service, actor)
        status = await new_status(service, actor, definition.id, "REVIEW")

        await service.delete_status(status.id)

        assert status.id not in definitions.statuses

    async def test_unknown_status_is_rejected(self, service: WorkflowService) -> None:
        with pytest.raises(EntityNotFoundError):
            await service.delete_status(999_999)

    async def test_a_state_a_transition_leaves_from_cannot_be_deleted(
        self,
        service: WorkflowService,
        definitions: FakeWorkflowDefinitionRepository,
        actor: User,
    ) -> None:
        definition = await new_definition(service, actor)
        review = await new_status(service, actor, definition.id, "REVIEW")
        done = await new_status(service, actor, definition.id, "DONE", terminal=True)
        await new_transition(service, actor, definition.id, review.id, done.id, "FINISH")

        with pytest.raises(BusinessRuleViolationError, match=r"1 transition\(s\) reference it"):
            await service.delete_status(review.id)

        assert review.id in definitions.statuses

    async def test_a_state_a_transition_enters_cannot_be_deleted(
        self, service: WorkflowService, actor: User
    ) -> None:
        definition = await new_definition(service, actor)
        review = await new_status(service, actor, definition.id, "REVIEW")
        done = await new_status(service, actor, definition.id, "DONE", terminal=True)
        await new_transition(service, actor, definition.id, review.id, done.id, "FINISH")

        with pytest.raises(BusinessRuleViolationError, match=r"1 transition\(s\) reference it"):
            await service.delete_status(done.id)

    async def test_a_state_holding_live_instances_cannot_be_deleted(
        self,
        service: WorkflowService,
        definitions: FakeWorkflowDefinitionRepository,
        actor: User,
    ) -> None:
        definition = await new_definition(service, actor)
        review = await new_status(service, actor, definition.id, "REVIEW")
        definitions.instances_in_status[review.id] = 3

        with pytest.raises(
            BusinessRuleViolationError, match=r"3 instance\(s\) are currently in it"
        ):
            await service.delete_status(review.id)

        assert review.id in definitions.statuses

    async def test_deleting_one_state_keeps_the_others(
        self,
        service: WorkflowService,
        definitions: FakeWorkflowDefinitionRepository,
        actor: User,
    ) -> None:
        definition = await new_definition(service, actor)
        gone = await new_status(service, actor, definition.id, "GONE")
        kept = await new_status(service, actor, definition.id, "KEPT")

        await service.delete_status(gone.id)

        assert list(definitions.statuses) == [kept.id]


# ═══════════════════════════ Transitions ═══════════════════════════


class TestListTransitions:
    async def test_returns_the_definitions_transitions_ordered_by_priority(
        self, service: WorkflowService, actor: User
    ) -> None:
        definition = await new_definition(service, actor)
        review = await new_status(service, actor, definition.id, "REVIEW")
        done = await new_status(service, actor, definition.id, "DONE", terminal=True)
        gone = await new_status(service, actor, definition.id, "GONE", terminal=True)
        await new_transition(
            service, actor, definition.id, review.id, done.id, "LATE", priority=9
        )
        await new_transition(
            service, actor, definition.id, review.id, gone.id, "EARLY", priority=1
        )

        result = await service.list_transitions(definition.id)

        assert [t.action_code for t in result] == ["EARLY", "LATE"]

    async def test_unknown_definition_is_rejected(self, service: WorkflowService) -> None:
        with pytest.raises(EntityNotFoundError):
            await service.list_transitions(999_999)


class TestCreateTransition:
    async def _setup(
        self, service: WorkflowService, actor: User
    ) -> tuple[
        WorkflowDefinitionResponse, WorkflowStatusResponse, WorkflowStatusResponse
    ]:
        definition = await new_definition(service, actor)
        review = await new_status(service, actor, definition.id, "REVIEW")
        done = await new_status(service, actor, definition.id, "DONE", terminal=True)
        return definition, review, done

    async def test_creates_the_transition_with_every_field(
        self,
        service: WorkflowService,
        definitions: FakeWorkflowDefinitionRepository,
        actor: User,
    ) -> None:
        definition, review, done = await self._setup(service, actor)

        response = await new_transition(
            service,
            actor,
            definition.id,
            review.id,
            done.id,
            "approve",
            action_type=WorkflowActionType.APPROVE,
            guard_expression="amount < 10",
            requires_comment=True,
            auto_execute=True,
            priority=4,
        )

        assert response.id != 0
        assert response.workflow_definition_id == definition.id
        assert (response.from_status_id, response.to_status_id) == (review.id, done.id)
        assert response.action_code == "APPROVE"
        assert response.action_type == WorkflowActionType.APPROVE
        assert response.guard_expression == "amount < 10"
        assert response.requires_comment is True
        assert response.auto_execute is True
        assert response.priority == 4
        assert definitions.transitions[response.id].created_by == "alice"

    async def test_defaults_to_a_custom_action_without_guard_or_comment(
        self, service: WorkflowService, actor: User
    ) -> None:
        definition, review, done = await self._setup(service, actor)

        response = await new_transition(
            service, actor, definition.id, review.id, done.id, "FINISH"
        )

        assert response.action_type == WorkflowActionType.CUSTOM
        assert response.guard_expression is None
        assert response.requires_comment is False
        assert response.auto_execute is False
        assert response.priority == 0

    async def test_unknown_definition_is_rejected(
        self, service: WorkflowService, actor: User
    ) -> None:
        with pytest.raises(EntityNotFoundError, match="WorkflowDefinition"):
            await new_transition(service, actor, 999_999, 1, 2)

    async def test_unknown_source_state_is_rejected(
        self, service: WorkflowService, actor: User
    ) -> None:
        definition, _, done = await self._setup(service, actor)

        with pytest.raises(EntityNotFoundError, match="WorkflowStatus"):
            await new_transition(service, actor, definition.id, 999_999, done.id)

    async def test_unknown_target_state_is_rejected(
        self, service: WorkflowService, actor: User
    ) -> None:
        definition, review, _ = await self._setup(service, actor)

        with pytest.raises(EntityNotFoundError, match="WorkflowStatus"):
            await new_transition(service, actor, definition.id, review.id, 999_999)

    async def test_source_state_from_another_definition_is_rejected(
        self, service: WorkflowService, actor: User
    ) -> None:
        definition, _, done = await self._setup(service, actor)
        other = await new_definition(service, actor, code="OTHER")
        foreign = await new_status(service, actor, other.id, "FOREIGN")

        with pytest.raises(
            BusinessRuleViolationError, match="'FOREIGN' belongs to a different workflow"
        ):
            await new_transition(service, actor, definition.id, foreign.id, done.id)

    async def test_target_state_from_another_definition_is_rejected(
        self, service: WorkflowService, actor: User
    ) -> None:
        definition, review, _ = await self._setup(service, actor)
        other = await new_definition(service, actor, code="OTHER")
        foreign = await new_status(service, actor, other.id, "FOREIGN")

        with pytest.raises(
            BusinessRuleViolationError, match="'FOREIGN' belongs to a different workflow"
        ):
            await new_transition(service, actor, definition.id, review.id, foreign.id)

    async def test_no_transition_may_leave_a_terminal_state(
        self,
        service: WorkflowService,
        definitions: FakeWorkflowDefinitionRepository,
        actor: User,
    ) -> None:
        definition, review, done = await self._setup(service, actor)

        with pytest.raises(BusinessRuleViolationError, match="'DONE' is terminal"):
            await new_transition(service, actor, definition.id, done.id, review.id)

        assert definitions.transitions == {}

    async def test_a_transition_may_enter_a_terminal_state(
        self, service: WorkflowService, actor: User
    ) -> None:
        definition, review, done = await self._setup(service, actor)

        response = await new_transition(service, actor, definition.id, review.id, done.id)

        assert response.to_status_id == done.id

    async def test_a_transition_cannot_loop_back_onto_its_own_state(
        self, service: WorkflowService, actor: User
    ) -> None:
        definition, review, _ = await self._setup(service, actor)

        with pytest.raises(BusinessRuleViolationError, match="two different states"):
            await new_transition(service, actor, definition.id, review.id, review.id)

    async def test_a_terminal_self_loop_reports_the_terminal_rule_first(
        self, service: WorkflowService, actor: User
    ) -> None:
        definition, _, done = await self._setup(service, actor)

        with pytest.raises(BusinessRuleViolationError, match="is terminal"):
            await new_transition(service, actor, definition.id, done.id, done.id)

    async def test_the_same_action_twice_from_one_state_is_rejected(
        self, service: WorkflowService, actor: User
    ) -> None:
        definition, review, done = await self._setup(service, actor)
        other = await new_status(service, actor, definition.id, "OTHER", terminal=True)
        await new_transition(service, actor, definition.id, review.id, done.id, "FINISH")

        with pytest.raises(DuplicateEntityError) as exc_info:
            await new_transition(
                service, actor, definition.id, review.id, other.id, "FINISH"
            )

        assert (exc_info.value.entity, exc_info.value.field) == (
            "WorkflowTransition",
            "action_code",
        )
        assert exc_info.value.value == "FINISH from REVIEW"

    async def test_the_same_action_from_a_different_state_is_allowed(
        self, service: WorkflowService, actor: User
    ) -> None:
        definition, review, done = await self._setup(service, actor)
        draft = await new_status(service, actor, definition.id, "DRAFT", initial=True)
        await new_transition(service, actor, definition.id, review.id, done.id, "FINISH")

        response = await new_transition(
            service, actor, definition.id, draft.id, done.id, "FINISH"
        )

        assert response.from_status_id == draft.id

    async def test_a_different_action_between_the_same_states_is_allowed(
        self, service: WorkflowService, actor: User
    ) -> None:
        definition, review, done = await self._setup(service, actor)
        await new_transition(service, actor, definition.id, review.id, done.id, "FINISH")

        response = await new_transition(
            service, actor, definition.id, review.id, done.id, "ABORT"
        )

        assert response.action_code == "ABORT"


class TestDeleteTransition:
    async def test_deletes_the_transition(
        self,
        service: WorkflowService,
        definitions: FakeWorkflowDefinitionRepository,
        actor: User,
    ) -> None:
        definition = await new_definition(service, actor)
        review = await new_status(service, actor, definition.id, "REVIEW")
        done = await new_status(service, actor, definition.id, "DONE", terminal=True)
        transition = await new_transition(
            service, actor, definition.id, review.id, done.id
        )

        await service.delete_transition(transition.id)

        assert transition.id not in definitions.transitions

    async def test_unknown_transition_is_rejected(self, service: WorkflowService) -> None:
        with pytest.raises(EntityNotFoundError, match="WorkflowTransition"):
            await service.delete_transition(999_999)


# ═══════════════════════════ Runtime ═══════════════════════════


def start_request(scenario: WorkflowScenario, **overrides: Any) -> WorkflowStartRequest:
    values: dict[str, Any] = {
        "definition_code": "COMPLIANCE_TASK_APPROVAL",
        "entity_type": scenario.ENTITY_TYPE,
        "entity_id": 5001,
    }
    values.update(overrides)
    return WorkflowStartRequest(**values)


class TestStartWorkflow:
    async def test_returns_the_new_instance_at_the_initial_state(
        self, scenario: WorkflowScenario, runtime: WorkflowService, maker: User
    ) -> None:
        response = await runtime.start_workflow(
            start_request(scenario, priority=3, metadata={"amount": 10}), maker
        )

        assert response.id in scenario.instances.instances
        assert response.workflow_definition_id == scenario.definition.id
        assert response.definition_code == "COMPLIANCE_TASK_APPROVAL"
        assert response.definition_name == "Compliance Task Approval"
        assert response.entity_type == scenario.ENTITY_TYPE
        assert response.entity_id == 5001
        assert response.current_status_id == scenario.status_ids["DRAFT"]
        assert response.current_status_code == "DRAFT"
        assert response.current_status_name == "Draft"
        assert response.is_terminal is False
        assert response.initiated_by == maker.id
        assert response.priority == 3
        assert response.metadata == {"amount": 10}
        assert response.is_completed is False
        assert response.completed_at is None
        assert response.approval_level == 0
        assert response.is_awaiting_approval is False

    async def test_unknown_definition_code_is_rejected(
        self, scenario: WorkflowScenario, runtime: WorkflowService, maker: User
    ) -> None:
        with pytest.raises(EntityNotFoundError):
            await runtime.start_workflow(
                start_request(scenario, definition_code="NO_SUCH"), maker
            )

    async def test_a_record_with_an_open_instance_cannot_be_started_again(
        self, scenario: WorkflowScenario, runtime: WorkflowService, maker: User
    ) -> None:
        await runtime.start_workflow(start_request(scenario), maker)

        with pytest.raises(BusinessRuleViolationError, match="already has an open workflow"):
            await runtime.start_workflow(start_request(scenario), maker)

        assert len(scenario.instances.instances) == 1


class TestExecuteAction:
    async def test_submit_moves_the_instance_and_opens_approval_level_one(
        self, scenario: WorkflowScenario, runtime: WorkflowService, maker: User
    ) -> None:
        scenario.add_two_level_matrix()
        instance = scenario.new_instance(status_code="DRAFT")

        response = await runtime.execute_action(
            instance.id, WorkflowActionRequest(action_code="SUBMIT"), maker
        )

        assert response.id == instance.id
        assert response.current_status_code == "L1_REVIEW"
        assert response.current_status_name == "L1 Review"
        assert response.definition_code == "COMPLIANCE_TASK_APPROVAL"
        assert response.approval_level == 1
        assert response.is_awaiting_approval is True
        assert response.is_completed is False

    async def test_reaching_a_terminal_state_completes_the_response(
        self, scenario: WorkflowScenario, runtime: WorkflowService, maker: User
    ) -> None:
        instance = scenario.new_instance(status_code="DRAFT")

        response = await runtime.execute_action(
            instance.id,
            WorkflowActionRequest(action_code="CANCEL", comments="no longer needed"),
            maker,
        )

        assert response.current_status_code == "CANCELLED"
        assert response.is_terminal is True
        assert response.is_completed is True
        assert response.completed_at is not None

    async def test_the_actor_comment_and_ip_are_recorded_in_the_history(
        self, scenario: WorkflowScenario, runtime: WorkflowService, maker: User
    ) -> None:
        instance = scenario.new_instance(status_code="DRAFT")

        await runtime.execute_action(
            instance.id,
            WorkflowActionRequest(action_code="CANCEL", comments="duplicate"),
            maker,
            ip_address="10.1.2.3",
        )

        (entry,) = scenario.instances.history
        assert entry.instance_id == instance.id
        assert entry.action_code == "CANCEL"
        assert entry.actor_id == maker.id
        assert entry.actor_username == "maker"
        assert entry.comments == "duplicate"
        assert entry.ip_address == "10.1.2.3"

    async def test_the_new_state_is_persisted(
        self, scenario: WorkflowScenario, runtime: WorkflowService, maker: User
    ) -> None:
        scenario.add_two_level_matrix()
        instance = scenario.new_instance(status_code="DRAFT")

        await runtime.execute_action(
            instance.id, WorkflowActionRequest(action_code="SUBMIT"), maker
        )

        stored = scenario.instances.instances[instance.id]
        assert stored.current_status_id == scenario.status_ids["L1_REVIEW"]
        assert stored.approval_level == 1

    async def test_unknown_instance_is_rejected(
        self, runtime: WorkflowService, maker: User
    ) -> None:
        with pytest.raises(EntityNotFoundError, match="WorkflowInstance"):
            await runtime.execute_action(
                999_999, WorkflowActionRequest(action_code="SUBMIT"), maker
            )

    async def test_an_action_not_offered_from_the_state_is_rejected(
        self, scenario: WorkflowScenario, runtime: WorkflowService, maker: User
    ) -> None:
        instance = scenario.new_instance(status_code="DRAFT")

        with pytest.raises(BusinessRuleViolationError, match="not allowed from the current state"):
            await runtime.execute_action(
                instance.id, WorkflowActionRequest(action_code="APPROVE"), maker
            )

    async def test_a_comment_required_action_without_one_is_rejected(
        self, scenario: WorkflowScenario, runtime: WorkflowService, maker: User
    ) -> None:
        instance = scenario.new_instance(status_code="DRAFT")

        with pytest.raises(BusinessRuleViolationError, match="requires a comment"):
            await runtime.execute_action(
                instance.id, WorkflowActionRequest(action_code="CANCEL"), maker
            )

        assert (
            scenario.instances.instances[instance.id].current_status_id
            == scenario.status_ids["DRAFT"]
        )

    async def test_a_completed_instance_accepts_no_further_actions(
        self, scenario: WorkflowScenario, runtime: WorkflowService, maker: User
    ) -> None:
        instance = scenario.new_instance(status_code="DRAFT")
        await runtime.execute_action(
            instance.id,
            WorkflowActionRequest(action_code="CANCEL", comments="done"),
            maker,
        )

        with pytest.raises(BusinessRuleViolationError, match="already completed"):
            await runtime.execute_action(
                instance.id, WorkflowActionRequest(action_code="SUBMIT"), maker
            )


class TestGetInstance:
    async def test_returns_the_instance_resolved_to_its_state_and_definition(
        self, scenario: WorkflowScenario, runtime: WorkflowService
    ) -> None:
        instance = scenario.new_instance(
            status_code="L1_REVIEW", extra_data={"risk": "HIGH"}, approval_level=1
        )

        response = await runtime.get_instance(instance.id)

        assert response.id == instance.id
        assert response.current_status_code == "L1_REVIEW"
        assert response.definition_code == "COMPLIANCE_TASK_APPROVAL"
        assert response.entity_id == instance.entity_id
        assert response.approval_level == 1
        assert response.is_awaiting_approval is True
        assert response.metadata == {"risk": "HIGH"}

    async def test_unknown_instance_is_rejected(self, runtime: WorkflowService) -> None:
        with pytest.raises(EntityNotFoundError, match="WorkflowInstance"):
            await runtime.get_instance(999_999)


class TestListInstances:
    async def test_returns_instances_with_definition_and_state_resolved(
        self, scenario: WorkflowScenario, runtime: WorkflowService
    ) -> None:
        draft = scenario.new_instance(status_code="DRAFT")
        review = scenario.new_instance(status_code="L1_REVIEW")

        result = await runtime.list_instances()

        rows = {r.id: r for r in result.instances}
        assert set(rows) == {draft.id, review.id}
        assert rows[draft.id].current_status_code == "DRAFT"
        assert rows[review.id].current_status_name == "L1 Review"
        assert rows[review.id].definition_name == "Compliance Task Approval"
        assert (result.total, result.skip, result.limit) == (2, 0, 100)

    async def test_total_counts_all_matches_not_just_the_page(
        self, scenario: WorkflowScenario, runtime: WorkflowService
    ) -> None:
        for _ in range(4):
            scenario.new_instance(status_code="DRAFT")

        result = await runtime.list_instances(skip=1, limit=2)

        assert len(result.instances) == 2
        assert result.total == 4
        assert (result.skip, result.limit) == (1, 2)

    async def test_status_filter_reaches_the_repository(
        self, scenario: WorkflowScenario, runtime: WorkflowService
    ) -> None:
        scenario.new_instance(status_code="DRAFT")
        review = scenario.new_instance(status_code="L1_REVIEW")

        result = await runtime.list_instances(status_id=scenario.status_ids["L1_REVIEW"])

        assert [r.id for r in result.instances] == [review.id]
        assert result.total == 1

    async def test_entity_filters_reach_the_repository(
        self, scenario: WorkflowScenario, runtime: WorkflowService
    ) -> None:
        wanted = scenario.new_instance(status_code="DRAFT")
        scenario.new_instance(status_code="DRAFT")

        result = await runtime.list_instances(
            entity_type=scenario.ENTITY_TYPE, entity_id=wanted.entity_id
        )

        assert [r.id for r in result.instances] == [wanted.id]
        assert result.total == 1

    async def test_definition_filter_reaches_the_repository(
        self, scenario: WorkflowScenario, runtime: WorkflowService
    ) -> None:
        scenario.new_instance(status_code="DRAFT")

        matching = await runtime.list_instances(definition_id=scenario.definition.id)
        other = await runtime.list_instances(definition_id=999_999)

        assert matching.total == 1
        assert other.total == 0
        assert other.instances == []

    async def test_is_completed_filter_reaches_the_repository(
        self, scenario: WorkflowScenario, runtime: WorkflowService
    ) -> None:
        scenario.new_instance(status_code="DRAFT")
        finished = scenario.new_instance(status_code="APPROVED")
        stored = scenario.instances.instances[finished.id]
        stored.completed_at = datetime.now(UTC)

        done = await runtime.list_instances(is_completed=True)
        open_ = await runtime.list_instances(is_completed=False)

        assert [r.id for r in done.instances] == [finished.id]
        assert done.instances[0].is_terminal is True
        assert open_.total == 1

    async def test_an_empty_store_returns_an_empty_page(
        self, runtime: WorkflowService
    ) -> None:
        result = await runtime.list_instances()

        assert result.instances == []
        assert result.total == 0

    async def test_a_row_whose_state_has_vanished_is_skipped_but_still_counted(
        self, scenario: WorkflowScenario, runtime: WorkflowService
    ) -> None:
        kept = scenario.new_instance(status_code="DRAFT")
        orphan = scenario.new_instance(status_code="L1_REVIEW")
        del scenario.definitions.statuses[scenario.status_ids["L1_REVIEW"]]

        result = await runtime.list_instances()

        assert [r.id for r in result.instances] == [kept.id]
        assert orphan.id in scenario.instances.instances
        assert result.total == 2

    async def test_a_row_whose_definition_has_vanished_is_skipped(
        self, scenario: WorkflowScenario, runtime: WorkflowService
    ) -> None:
        scenario.new_instance(status_code="DRAFT")
        del scenario.definitions.definitions[scenario.definition.id]

        result = await runtime.list_instances()

        assert result.instances == []


class TestAvailableActions:
    async def test_lists_the_actions_the_current_state_offers(
        self, scenario: WorkflowScenario, runtime: WorkflowService
    ) -> None:
        instance = scenario.new_instance(status_code="DRAFT")

        actions = await runtime.available_actions(instance.id)

        by_code = {a.action_code: a for a in actions}
        assert set(by_code) == {"SUBMIT", "CANCEL"}
        submit = by_code["SUBMIT"]
        assert submit.action_type == WorkflowActionType.SUBMIT
        assert submit.to_status_id == scenario.status_ids["L1_REVIEW"]
        assert submit.to_status_code == "L1_REVIEW"
        assert submit.to_status_name == "L1 Review"
        assert submit.requires_comment is False
        assert submit.is_terminal is False

    async def test_the_target_states_terminal_flag_and_comment_rule_are_carried(
        self, scenario: WorkflowScenario, runtime: WorkflowService
    ) -> None:
        instance = scenario.new_instance(status_code="DRAFT")

        actions = await runtime.available_actions(instance.id)

        cancel = next(a for a in actions if a.action_code == "CANCEL")
        assert cancel.to_status_code == "CANCELLED"
        assert cancel.is_terminal is True
        assert cancel.requires_comment is True
        assert cancel.action_type == WorkflowActionType.CANCEL

    async def test_actions_follow_the_instances_current_state(
        self, scenario: WorkflowScenario, runtime: WorkflowService
    ) -> None:
        instance = scenario.new_instance(status_code="L1_REVIEW")

        actions = await runtime.available_actions(instance.id)

        assert {a.action_code for a in actions} == {"APPROVE", "REFER_BACK", "REJECT"}

    async def test_a_completed_instance_offers_nothing(
        self, scenario: WorkflowScenario, runtime: WorkflowService
    ) -> None:
        instance = scenario.new_instance(status_code="APPROVED")
        scenario.instances.instances[instance.id].completed_at = datetime.now(UTC)

        assert await runtime.available_actions(instance.id) == []

    async def test_a_state_with_no_outgoing_transitions_offers_nothing(
        self, scenario: WorkflowScenario, runtime: WorkflowService
    ) -> None:
        instance = scenario.new_instance(status_code="APPROVED")

        assert await runtime.available_actions(instance.id) == []

    async def test_an_action_whose_target_state_has_vanished_is_skipped(
        self, scenario: WorkflowScenario, runtime: WorkflowService
    ) -> None:
        instance = scenario.new_instance(status_code="DRAFT")
        del scenario.definitions.statuses[scenario.status_ids["CANCELLED"]]

        actions = await runtime.available_actions(instance.id)

        assert [a.action_code for a in actions] == ["SUBMIT"]

    async def test_unknown_instance_is_rejected(self, runtime: WorkflowService) -> None:
        with pytest.raises(EntityNotFoundError, match="WorkflowInstance"):
            await runtime.available_actions(999_999)


class TestInstanceHistory:
    @staticmethod
    def _entry(
        instance_id: int,
        *,
        from_status_id: int | None,
        to_status_id: int,
        action_code: str,
        minutes_ago: int,
    ) -> WorkflowHistoryEntry:
        return WorkflowHistoryEntry(
            instance_id=instance_id,
            from_status_id=from_status_id,
            to_status_id=to_status_id,
            action_code=action_code,
            actor_id=7,
            actor_username="maker",
            comments="c",
            ip_address="10.0.0.1",
            created_at=datetime.now(UTC) - timedelta(minutes=minutes_ago),
        )

    async def test_returns_entries_newest_first_with_state_codes_resolved(
        self, scenario: WorkflowScenario, runtime: WorkflowService
    ) -> None:
        instance = scenario.new_instance(status_code="L2_REVIEW")
        ids = scenario.status_ids
        scenario.instances.history.extend(
            [
                self._entry(
                    instance.id,
                    from_status_id=ids["DRAFT"],
                    to_status_id=ids["L1_REVIEW"],
                    action_code="SUBMIT",
                    minutes_ago=30,
                ),
                self._entry(
                    instance.id,
                    from_status_id=ids["L1_REVIEW"],
                    to_status_id=ids["L2_REVIEW"],
                    action_code="APPROVE",
                    minutes_ago=10,
                ),
            ]
        )

        history = await runtime.instance_history(instance.id)

        assert [h.action_code for h in history] == ["APPROVE", "SUBMIT"]
        assert (history[0].from_status_code, history[0].to_status_code) == (
            "L1_REVIEW",
            "L2_REVIEW",
        )
        assert (history[1].from_status_code, history[1].to_status_code) == (
            "DRAFT",
            "L1_REVIEW",
        )
        assert history[0].actor_id == 7
        assert history[0].actor_username == "maker"
        assert history[0].comments == "c"
        assert history[0].ip_address == "10.0.0.1"
        assert history[0].instance_id == instance.id

    async def test_an_entry_without_a_source_state_has_no_source_code(
        self, scenario: WorkflowScenario, runtime: WorkflowService
    ) -> None:
        instance = scenario.new_instance(status_code="DRAFT")
        scenario.instances.history.append(
            self._entry(
                instance.id,
                from_status_id=None,
                to_status_id=scenario.status_ids["DRAFT"],
                action_code="START",
                minutes_ago=1,
            )
        )

        (entry,) = await runtime.instance_history(instance.id)

        assert entry.from_status_id is None
        assert entry.from_status_code is None
        assert entry.to_status_code == "DRAFT"

    async def test_a_state_that_no_longer_exists_resolves_to_no_code(
        self, scenario: WorkflowScenario, runtime: WorkflowService
    ) -> None:
        instance = scenario.new_instance(status_code="DRAFT")
        scenario.instances.history.append(
            self._entry(
                instance.id,
                from_status_id=888_888,
                to_status_id=999_999,
                action_code="LEGACY",
                minutes_ago=1,
            )
        )

        (entry,) = await runtime.instance_history(instance.id)

        assert entry.from_status_code is None
        assert entry.to_status_code is None
        assert (entry.from_status_id, entry.to_status_id) == (888_888, 999_999)

    async def test_other_instances_entries_are_excluded(
        self, scenario: WorkflowScenario, runtime: WorkflowService
    ) -> None:
        mine = scenario.new_instance(status_code="DRAFT")
        theirs = scenario.new_instance(status_code="DRAFT")
        scenario.instances.history.append(
            self._entry(
                theirs.id,
                from_status_id=None,
                to_status_id=scenario.status_ids["DRAFT"],
                action_code="START",
                minutes_ago=1,
            )
        )

        assert await runtime.instance_history(mine.id) == []

    async def test_history_recorded_by_executing_an_action_is_returned(
        self, scenario: WorkflowScenario, runtime: WorkflowService, maker: User
    ) -> None:
        instance = scenario.new_instance(status_code="DRAFT")
        await runtime.execute_action(
            instance.id,
            WorkflowActionRequest(action_code="CANCEL", comments="withdrawn"),
            maker,
            ip_address="10.9.9.9",
        )

        (entry,) = await runtime.instance_history(instance.id)

        assert (entry.from_status_code, entry.to_status_code) == ("DRAFT", "CANCELLED")
        assert entry.action_code == "CANCEL"
        assert entry.ip_address == "10.9.9.9"

    async def test_unknown_instance_is_rejected(self, runtime: WorkflowService) -> None:
        with pytest.raises(EntityNotFoundError, match="WorkflowInstance"):
            await runtime.instance_history(999_999)


class TestMyTasks:
    async def test_returns_the_open_tasks_assigned_to_the_user(
        self, scenario: WorkflowScenario, runtime: WorkflowService, maker: User
    ) -> None:
        scenario.add_two_level_matrix()
        instance = scenario.new_instance(status_code="DRAFT")
        await runtime.execute_action(
            instance.id, WorkflowActionRequest(action_code="SUBMIT"), maker
        )

        tasks = await runtime.my_tasks(scenario.manager_a)

        assert len(tasks) == 1
        assert tasks[0].instance_id == instance.id
        assert tasks[0].assignee_id == scenario.manager_a
        assert tasks[0].level == 1
        assert tasks[0].status == ApprovalTaskStatus.PENDING

    async def test_a_user_outside_the_current_level_has_no_tasks(
        self, scenario: WorkflowScenario, runtime: WorkflowService, maker: User
    ) -> None:
        scenario.add_two_level_matrix()
        instance = scenario.new_instance(status_code="DRAFT")
        await runtime.execute_action(
            instance.id, WorkflowActionRequest(action_code="SUBMIT"), maker
        )

        assert await runtime.my_tasks(scenario.admin) == []
        assert await runtime.my_tasks(scenario.maker) == []

    async def test_settled_tasks_are_not_listed(
        self, scenario: WorkflowScenario, runtime: WorkflowService, maker: User
    ) -> None:
        scenario.add_two_level_matrix()
        instance = scenario.new_instance(status_code="DRAFT")
        await runtime.execute_action(
            instance.id, WorkflowActionRequest(action_code="SUBMIT"), maker
        )
        await runtime.execute_action(
            instance.id,
            WorkflowActionRequest(action_code="REJECT", comments="no"),
            User(id=scenario.manager_a, username="manager_a"),
        )

        assert await runtime.my_tasks(scenario.manager_a) == []
        assert await runtime.my_tasks(scenario.manager_b) == []


class TestInstanceTasks:
    async def test_returns_every_task_raised_for_the_instance(
        self, scenario: WorkflowScenario, runtime: WorkflowService, maker: User
    ) -> None:
        scenario.add_two_level_matrix()
        instance = scenario.new_instance(status_code="DRAFT")
        await runtime.execute_action(
            instance.id, WorkflowActionRequest(action_code="SUBMIT"), maker
        )

        tasks = await runtime.instance_tasks(instance.id)

        assert {t.assignee_id for t in tasks} == {scenario.manager_a, scenario.manager_b}
        assert {t.level for t in tasks} == {1}
        assert {t.instance_id for t in tasks} == {instance.id}

    async def test_settled_tasks_are_still_part_of_the_record(
        self, scenario: WorkflowScenario, runtime: WorkflowService, maker: User
    ) -> None:
        scenario.add_two_level_matrix()
        instance = scenario.new_instance(status_code="DRAFT")
        await runtime.execute_action(
            instance.id, WorkflowActionRequest(action_code="SUBMIT"), maker
        )
        await runtime.execute_action(
            instance.id,
            WorkflowActionRequest(action_code="REJECT", comments="no"),
            User(id=scenario.manager_a, username="manager_a"),
        )

        tasks = await runtime.instance_tasks(instance.id)

        assert len(tasks) == 2
        assert all(t.status != ApprovalTaskStatus.PENDING for t in tasks)

    async def test_other_instances_tasks_are_excluded(
        self, scenario: WorkflowScenario, runtime: WorkflowService, maker: User
    ) -> None:
        scenario.add_two_level_matrix()
        submitted = scenario.new_instance(status_code="DRAFT")
        untouched = scenario.new_instance(status_code="DRAFT")
        await runtime.execute_action(
            submitted.id, WorkflowActionRequest(action_code="SUBMIT"), maker
        )

        assert await runtime.instance_tasks(untouched.id) == []

    async def test_an_instance_with_no_tasks_has_an_empty_list(
        self, scenario: WorkflowScenario, runtime: WorkflowService
    ) -> None:
        instance = scenario.new_instance(status_code="DRAFT")

        assert await runtime.instance_tasks(instance.id) == []

    async def test_unknown_instance_is_rejected(self, runtime: WorkflowService) -> None:
        with pytest.raises(EntityNotFoundError, match="WorkflowInstance"):
            await runtime.instance_tasks(999_999)
