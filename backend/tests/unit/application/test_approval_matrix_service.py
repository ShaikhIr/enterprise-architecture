"""
Approval matrix service tests.

The service owns matrix configuration: code and name uniqueness, partial updates whose
`rules` / `assignments` collections are replace-if-supplied (so the last rule can be
deleted), the delete guard, and the dry-run `resolve`. The repository only runs queries,
so these tests pin the rules down against the shared in-memory fake.
"""

from typing import Any

import pytest
from workflow_fakes import FakeApprovalMatrixRepository, build_matrix

from src.api.v1.schemas.approval_matrix_schema import (
    ApprovalAssignmentInput,
    ApprovalMatrixCreate,
    ApprovalMatrixUpdate,
    ApprovalRuleInput,
)
from src.application.services.approval_matrix_service import ApprovalMatrixService
from src.domain.entities.approval_matrix import ApprovalMatrix
from src.domain.entities.user import User
from src.domain.enums.workflow_enums import AssignmentType, RuleDataType, RuleOperator
from src.domain.exceptions.domain_exceptions import (
    DuplicateEntityError,
    EntityNotFoundError,
)

ENTITY = "compliance_task"


@pytest.fixture
def repo() -> FakeApprovalMatrixRepository:
    return FakeApprovalMatrixRepository()


@pytest.fixture
def service(repo: FakeApprovalMatrixRepository) -> ApprovalMatrixService:
    return ApprovalMatrixService(repo)


@pytest.fixture
def actor() -> User:
    return User(id=1, username="alice")


def rule_input(
    field: str = "amount",
    operator: RuleOperator = RuleOperator.GT,
    value: str = "1000",
    data_type: RuleDataType = RuleDataType.NUMBER,
    logical_group: str = "default",
) -> ApprovalRuleInput:
    return ApprovalRuleInput(
        field=field,
        operator=operator,
        value=value,
        data_type=data_type,
        logical_group=logical_group,
    )


def role_level(level: int, role_id: int) -> ApprovalAssignmentInput:
    return ApprovalAssignmentInput(
        level=level, assignment_type=AssignmentType.ROLE, role_id=role_id
    )


def user_level(level: int, user_id: int) -> ApprovalAssignmentInput:
    return ApprovalAssignmentInput(
        level=level, assignment_type=AssignmentType.USER, user_id=user_id
    )


def create_request(**overrides: Any) -> ApprovalMatrixCreate:
    values: dict[str, Any] = {
        "code": "TASK_STANDARD",
        "name": "Task standard",
        "entity_type": ENTITY,
    }
    values.update(overrides)
    return ApprovalMatrixCreate(**values)


def seed(
    repo: FakeApprovalMatrixRepository, **overrides: Any
) -> ApprovalMatrix:
    matrix = build_matrix(**overrides)
    repo.matrices[matrix.id] = matrix
    return matrix


class TestCreate:
    async def test_creates_a_matrix_with_actor_audit_fields(
        self,
        service: ApprovalMatrixService,
        repo: FakeApprovalMatrixRepository,
        actor: User,
    ) -> None:
        response = await service.create_matrix(
            create_request(priority=4, is_active=False), actor
        )

        assert response.id != 0
        assert response.code == "TASK_STANDARD"
        assert response.name == "Task standard"
        assert response.entity_type == ENTITY
        assert response.priority == 4
        assert response.is_active is False
        assert response.created_by == "alice"
        assert response.modified_by == "alice"
        assert response.id in repo.matrices

    async def test_defaults_to_active_with_priority_zero_and_no_children(
        self, service: ApprovalMatrixService, actor: User
    ) -> None:
        response = await service.create_matrix(create_request(), actor)

        assert response.is_active is True
        assert response.priority == 0
        assert response.rules == []
        assert response.assignments == []

    async def test_code_is_normalised_by_the_schema_before_the_uniqueness_check(
        self,
        service: ApprovalMatrixService,
        repo: FakeApprovalMatrixRepository,
        actor: User,
    ) -> None:
        seed(repo, code="FILING_BY_AMOUNT")

        with pytest.raises(DuplicateEntityError, match="code 'FILING_BY_AMOUNT'"):
            await service.create_matrix(
                create_request(code="filing by-amount", name="Another name"), actor
            )

    async def test_duplicate_code_is_rejected(
        self,
        service: ApprovalMatrixService,
        repo: FakeApprovalMatrixRepository,
        actor: User,
    ) -> None:
        seed(repo, code="TASK_STANDARD")

        with pytest.raises(DuplicateEntityError) as exc_info:
            await service.create_matrix(create_request(name="A different name"), actor)

        assert (exc_info.value.entity, exc_info.value.field) == ("ApprovalMatrix", "code")
        assert len(repo.matrices) == 1

    async def test_duplicate_name_is_rejected(
        self,
        service: ApprovalMatrixService,
        repo: FakeApprovalMatrixRepository,
        actor: User,
    ) -> None:
        existing = seed(repo, code="OTHER_CODE")
        existing.name = "Task standard"

        with pytest.raises(DuplicateEntityError) as exc_info:
            await service.create_matrix(create_request(), actor)

        assert (exc_info.value.entity, exc_info.value.field) == ("ApprovalMatrix", "name")
        assert len(repo.matrices) == 1

    async def test_same_name_is_allowed_after_the_other_matrix_is_gone(
        self,
        service: ApprovalMatrixService,
        repo: FakeApprovalMatrixRepository,
        actor: User,
    ) -> None:
        existing = seed(repo, code="OTHER_CODE")
        existing.name = "Task standard"
        await service.delete_matrix(existing.id)

        response = await service.create_matrix(create_request(), actor)

        assert response.code == "TASK_STANDARD"

    async def test_rules_are_persisted_field_for_field(
        self,
        service: ApprovalMatrixService,
        repo: FakeApprovalMatrixRepository,
        actor: User,
    ) -> None:
        response = await service.create_matrix(
            create_request(
                rules=[
                    rule_input("amount", RuleOperator.GTE, "5000", RuleDataType.NUMBER),
                    rule_input(
                        "state.code",
                        RuleOperator.IN,
                        "MH,KA",
                        RuleDataType.LIST,
                        logical_group="g2",
                    ),
                ]
            ),
            actor,
        )

        stored_rules = repo.matrices[response.id].rules
        assert [
            (r.field, r.operator, r.value, r.data_type, r.logical_group)
            for r in stored_rules
        ] == [
            ("amount", RuleOperator.GTE, "5000", RuleDataType.NUMBER, "default"),
            ("state.code", RuleOperator.IN, "MH,KA", RuleDataType.LIST, "g2"),
        ]
        assert {r.created_by for r in stored_rules} == {"alice"}
        assert {r.modified_by for r in stored_rules} == {"alice"}
        assert [r.field for r in response.rules] == ["amount", "state.code"]

    async def test_assignments_are_persisted_field_for_field(
        self,
        service: ApprovalMatrixService,
        repo: FakeApprovalMatrixRepository,
        actor: User,
    ) -> None:
        response = await service.create_matrix(
            create_request(assignments=[role_level(1, 11), user_level(2, 22)]), actor
        )

        stored = repo.matrices[response.id].assignments
        assert [
            (a.level, a.assignment_type, a.role_id, a.user_id) for a in stored
        ] == [
            (1, AssignmentType.ROLE, 11, None),
            (2, AssignmentType.USER, None, 22),
        ]
        assert {a.created_by for a in stored} == {"alice"}
        assert {a.modified_by for a in stored} == {"alice"}
        assert [a.level for a in response.assignments] == [1, 2]

    async def test_children_are_built_with_the_zero_matrix_id_placeholder(
        self,
        service: ApprovalMatrixService,
        repo: FakeApprovalMatrixRepository,
        actor: User,
    ) -> None:
        # The matrix id is DB-assigned; the repository stamps the real parent id.
        response = await service.create_matrix(
            create_request(rules=[rule_input()], assignments=[role_level(1, 11)]), actor
        )

        stored = repo.matrices[response.id]
        assert [r.matrix_id for r in stored.rules] == [0]
        assert [a.matrix_id for a in stored.assignments] == [0]


class TestGet:
    async def test_returns_the_matrix_with_rules_and_levels(
        self, service: ApprovalMatrixService, repo: FakeApprovalMatrixRepository
    ) -> None:
        matrix = seed(
            repo,
            rules=[("amount", "GT", "1000", "NUMBER")],
            levels=[(1, AssignmentType.ROLE, 11)],
        )

        response = await service.get_matrix(matrix.id)

        assert response.id == matrix.id
        assert [r.field for r in response.rules] == ["amount"]
        assert [(a.level, a.role_id) for a in response.assignments] == [(1, 11)]

    async def test_unknown_matrix_is_rejected(self, service: ApprovalMatrixService) -> None:
        with pytest.raises(EntityNotFoundError, match="ApprovalMatrix '999999'"):
            await service.get_matrix(999_999)


class TestList:
    async def test_returns_matrices_ordered_by_priority_with_total(
        self, service: ApprovalMatrixService, repo: FakeApprovalMatrixRepository
    ) -> None:
        seed(repo, code="LATE", priority=9)
        seed(repo, code="EARLY", priority=1)

        result = await service.list_matrices()

        assert [m.code for m in result.matrices] == ["EARLY", "LATE"]
        assert (result.total, result.skip, result.limit) == (2, 0, 100)

    async def test_total_counts_all_matches_not_just_the_page(
        self, service: ApprovalMatrixService, repo: FakeApprovalMatrixRepository
    ) -> None:
        for index in range(5):
            seed(repo, code=f"M{index}", priority=index)

        result = await service.list_matrices(skip=1, limit=2)

        assert [m.code for m in result.matrices] == ["M1", "M2"]
        assert result.total == 5
        assert (result.skip, result.limit) == (1, 2)

    async def test_search_filter_reaches_the_repository(
        self, service: ApprovalMatrixService, repo: FakeApprovalMatrixRepository
    ) -> None:
        seed(repo, code="ALPHA")
        seed(repo, code="BETA")

        result = await service.list_matrices(search="alp")

        assert [m.code for m in result.matrices] == ["ALPHA"]
        assert result.total == 1

    async def test_is_active_filter_reaches_the_repository(
        self, service: ApprovalMatrixService, repo: FakeApprovalMatrixRepository
    ) -> None:
        seed(repo, code="ON", is_active=True)
        seed(repo, code="OFF", is_active=False)

        result = await service.list_matrices(is_active=False)

        assert [m.code for m in result.matrices] == ["OFF"]
        assert result.total == 1

    async def test_entity_type_filter_reaches_the_repository(
        self, service: ApprovalMatrixService, repo: FakeApprovalMatrixRepository
    ) -> None:
        seed(repo, code="TASKS", entity_type="compliance_task")
        seed(repo, code="INVOICES", entity_type="invoice")

        result = await service.list_matrices(entity_type="invoice")

        assert [m.code for m in result.matrices] == ["INVOICES"]
        assert result.total == 1


class TestUpdate:
    async def test_unknown_matrix_is_rejected(
        self, service: ApprovalMatrixService, actor: User
    ) -> None:
        with pytest.raises(EntityNotFoundError):
            await service.update_matrix(999_999, ApprovalMatrixUpdate(name="Whatever"), actor)

    async def test_name_alone_changes_only_the_name(
        self,
        service: ApprovalMatrixService,
        repo: FakeApprovalMatrixRepository,
        actor: User,
    ) -> None:
        matrix = seed(
            repo,
            code="M1",
            entity_type="invoice",
            priority=7,
            rules=[("amount", "GT", "1", "NUMBER")],
            levels=[(1, AssignmentType.ROLE, 11)],
        )

        response = await service.update_matrix(
            matrix.id, ApprovalMatrixUpdate(name="Renamed"), actor
        )

        assert response.name == "Renamed"
        assert response.entity_type == "invoice"
        assert response.priority == 7
        assert response.is_active is True
        assert len(response.rules) == 1
        assert len(response.assignments) == 1

    async def test_renaming_to_another_matrixs_name_is_rejected(
        self,
        service: ApprovalMatrixService,
        repo: FakeApprovalMatrixRepository,
        actor: User,
    ) -> None:
        other = seed(repo, code="OTHER")
        other.name = "Taken name"
        matrix = seed(repo, code="MINE")

        with pytest.raises(DuplicateEntityError) as exc_info:
            await service.update_matrix(
                matrix.id, ApprovalMatrixUpdate(name="Taken name"), actor
            )

        assert (exc_info.value.entity, exc_info.value.field) == ("ApprovalMatrix", "name")
        assert repo.matrices[matrix.id].name != "Taken name"

    async def test_resubmitting_the_current_name_is_not_a_conflict(
        self,
        service: ApprovalMatrixService,
        repo: FakeApprovalMatrixRepository,
        actor: User,
    ) -> None:
        matrix = seed(repo, code="MINE")

        response = await service.update_matrix(
            matrix.id, ApprovalMatrixUpdate(name=matrix.name), actor
        )

        assert response.name == matrix.name

    async def test_changing_only_the_case_of_the_name_is_allowed(
        self,
        service: ApprovalMatrixService,
        repo: FakeApprovalMatrixRepository,
        actor: User,
    ) -> None:
        matrix = seed(repo, code="MINE")
        matrix.name = "Task standard"

        response = await service.update_matrix(
            matrix.id, ApprovalMatrixUpdate(name="TASK STANDARD"), actor
        )

        assert response.name == "TASK STANDARD"

    async def test_entity_type_alone_changes_only_the_entity_type(
        self,
        service: ApprovalMatrixService,
        repo: FakeApprovalMatrixRepository,
        actor: User,
    ) -> None:
        matrix = seed(repo, code="M1", priority=7)
        original_name = matrix.name

        response = await service.update_matrix(
            matrix.id, ApprovalMatrixUpdate(entity_type="invoice"), actor
        )

        assert response.entity_type == "invoice"
        assert response.name == original_name
        assert response.priority == 7

    async def test_priority_alone_changes_only_the_priority(
        self,
        service: ApprovalMatrixService,
        repo: FakeApprovalMatrixRepository,
        actor: User,
    ) -> None:
        matrix = seed(repo, code="M1", priority=7, entity_type="invoice")

        response = await service.update_matrix(
            matrix.id, ApprovalMatrixUpdate(priority=3), actor
        )

        assert response.priority == 3
        assert response.entity_type == "invoice"
        assert response.is_active is True

    async def test_priority_zero_is_applied_not_mistaken_for_omitted(
        self,
        service: ApprovalMatrixService,
        repo: FakeApprovalMatrixRepository,
        actor: User,
    ) -> None:
        matrix = seed(repo, code="M1", priority=7)

        response = await service.update_matrix(
            matrix.id, ApprovalMatrixUpdate(priority=0), actor
        )

        assert response.priority == 0

    async def test_is_active_false_deactivates_without_touching_other_fields(
        self,
        service: ApprovalMatrixService,
        repo: FakeApprovalMatrixRepository,
        actor: User,
    ) -> None:
        matrix = seed(repo, code="M1", priority=7)

        response = await service.update_matrix(
            matrix.id, ApprovalMatrixUpdate(is_active=False), actor
        )

        assert response.is_active is False
        assert response.priority == 7

    async def test_supplied_rules_replace_the_stored_rules(
        self,
        service: ApprovalMatrixService,
        repo: FakeApprovalMatrixRepository,
        actor: User,
    ) -> None:
        matrix = seed(
            repo,
            code="M1",
            rules=[("amount", "GT", "1", "NUMBER"), ("region", "EQ", "W", "STRING")],
            levels=[(1, AssignmentType.ROLE, 11)],
        )

        await service.update_matrix(
            matrix.id,
            ApprovalMatrixUpdate(
                rules=[rule_input("state", RuleOperator.EQ, "MH", RuleDataType.STRING)]
            ),
            actor,
        )

        stored = repo.matrices[matrix.id]
        assert [(r.field, r.value) for r in stored.rules] == [("state", "MH")]
        assert [r.matrix_id for r in stored.rules] == [matrix.id]
        assert {r.created_by for r in stored.rules} == {"alice"}
        assert len(stored.assignments) == 1  # levels untouched

    async def test_an_empty_rules_list_clears_every_rule(
        self,
        service: ApprovalMatrixService,
        repo: FakeApprovalMatrixRepository,
        actor: User,
    ) -> None:
        matrix = seed(repo, code="M1", rules=[("amount", "GT", "1", "NUMBER")])

        response = await service.update_matrix(
            matrix.id, ApprovalMatrixUpdate(rules=[]), actor
        )

        assert response.rules == []
        assert repo.matrices[matrix.id].rules == []

    async def test_omitting_rules_leaves_them_untouched(
        self,
        service: ApprovalMatrixService,
        repo: FakeApprovalMatrixRepository,
        actor: User,
    ) -> None:
        matrix = seed(repo, code="M1", rules=[("amount", "GT", "1", "NUMBER")])
        original_rule_id = matrix.rules[0].id

        await service.update_matrix(matrix.id, ApprovalMatrixUpdate(priority=2), actor)

        assert [r.id for r in repo.matrices[matrix.id].rules] == [original_rule_id]

    async def test_supplied_assignments_replace_the_stored_levels(
        self,
        service: ApprovalMatrixService,
        repo: FakeApprovalMatrixRepository,
        actor: User,
    ) -> None:
        matrix = seed(
            repo,
            code="M1",
            rules=[("amount", "GT", "1", "NUMBER")],
            levels=[(1, AssignmentType.ROLE, 11), (2, AssignmentType.ROLE, 12)],
        )

        await service.update_matrix(
            matrix.id,
            ApprovalMatrixUpdate(assignments=[user_level(1, 77)]),
            actor,
        )

        stored = repo.matrices[matrix.id]
        assert [(a.level, a.assignment_type, a.user_id, a.role_id) for a in stored.assignments] == [
            (1, AssignmentType.USER, 77, None)
        ]
        assert [a.matrix_id for a in stored.assignments] == [matrix.id]
        assert {a.created_by for a in stored.assignments} == {"alice"}
        assert len(stored.rules) == 1  # rules untouched

    async def test_an_empty_assignments_list_clears_every_level(
        self,
        service: ApprovalMatrixService,
        repo: FakeApprovalMatrixRepository,
        actor: User,
    ) -> None:
        matrix = seed(repo, code="M1", levels=[(1, AssignmentType.ROLE, 11)])

        response = await service.update_matrix(
            matrix.id, ApprovalMatrixUpdate(assignments=[]), actor
        )

        assert response.assignments == []

    async def test_omitting_assignments_leaves_them_untouched(
        self,
        service: ApprovalMatrixService,
        repo: FakeApprovalMatrixRepository,
        actor: User,
    ) -> None:
        matrix = seed(repo, code="M1", levels=[(1, AssignmentType.ROLE, 11)])
        original_id = matrix.assignments[0].id

        await service.update_matrix(matrix.id, ApprovalMatrixUpdate(priority=2), actor)

        assert [a.id for a in repo.matrices[matrix.id].assignments] == [original_id]

    async def test_update_is_persisted_and_stamps_the_actor(
        self,
        service: ApprovalMatrixService,
        repo: FakeApprovalMatrixRepository,
        actor: User,
    ) -> None:
        matrix = seed(repo, code="M1")

        response = await service.update_matrix(
            matrix.id, ApprovalMatrixUpdate(priority=2), actor
        )

        assert repo.matrices[matrix.id].priority == 2
        assert repo.matrices[matrix.id].modified_by == "alice"
        assert response.modified_by == "alice"

    async def test_an_empty_update_changes_nothing_but_the_audit_stamp(
        self,
        service: ApprovalMatrixService,
        repo: FakeApprovalMatrixRepository,
        actor: User,
    ) -> None:
        matrix = seed(
            repo,
            code="M1",
            priority=7,
            rules=[("amount", "GT", "1", "NUMBER")],
            levels=[(1, AssignmentType.ROLE, 11)],
        )

        response = await service.update_matrix(matrix.id, ApprovalMatrixUpdate(), actor)

        assert response.priority == 7
        assert len(response.rules) == 1
        assert len(response.assignments) == 1
        assert response.modified_by == "alice"


class TestDelete:
    async def test_deletes_the_matrix(
        self, service: ApprovalMatrixService, repo: FakeApprovalMatrixRepository
    ) -> None:
        matrix = seed(repo, code="M1")

        await service.delete_matrix(matrix.id)

        assert matrix.id not in repo.matrices

    async def test_other_matrices_are_kept(
        self, service: ApprovalMatrixService, repo: FakeApprovalMatrixRepository
    ) -> None:
        gone = seed(repo, code="GONE")
        kept = seed(repo, code="KEPT")

        await service.delete_matrix(gone.id)

        assert list(repo.matrices) == [kept.id]

    async def test_unknown_matrix_is_rejected(
        self, service: ApprovalMatrixService, repo: FakeApprovalMatrixRepository
    ) -> None:
        kept = seed(repo, code="KEPT")

        with pytest.raises(EntityNotFoundError):
            await service.delete_matrix(999_999)

        assert kept.id in repo.matrices


class TestResolve:
    async def test_no_matrix_for_the_entity_type_is_reported_as_unmatched(
        self, service: ApprovalMatrixService
    ) -> None:
        result = await service.resolve(ENTITY, {"amount": 5})

        assert result.matched is False
        assert result.matrix is None
        assert result.levels == []
        assert result.assignments == []

    async def test_matrix_whose_rules_do_not_match_is_reported_as_unmatched(
        self, service: ApprovalMatrixService, repo: FakeApprovalMatrixRepository
    ) -> None:
        seed(
            repo,
            entity_type=ENTITY,
            rules=[("amount", "GT", "1000", "NUMBER")],
            levels=[(1, AssignmentType.ROLE, 11)],
        )

        result = await service.resolve(ENTITY, {"amount": 5})

        assert result.matched is False
        assert result.assignments == []

    async def test_matching_matrix_is_reported_with_levels_and_assignments(
        self, service: ApprovalMatrixService, repo: FakeApprovalMatrixRepository
    ) -> None:
        matrix = seed(
            repo,
            code="BIG",
            entity_type=ENTITY,
            rules=[("amount", "GT", "1000", "NUMBER")],
            levels=[(2, AssignmentType.ROLE, 12), (1, AssignmentType.USER, 21)],
        )

        result = await service.resolve(ENTITY, {"amount": 5000})

        assert result.matched is True
        assert result.matrix is not None
        assert (result.matrix.id, result.matrix.code) == (matrix.id, "BIG")
        assert result.levels == [1, 2]
        assert [(a.level, a.user_id, a.role_id) for a in result.assignments] == [
            (1, 21, None),
            (2, None, 12),
        ]

    async def test_resolve_does_not_write_anything(
        self, service: ApprovalMatrixService, repo: FakeApprovalMatrixRepository
    ) -> None:
        matrix = seed(repo, entity_type=ENTITY, levels=[(1, AssignmentType.ROLE, 11)])
        before = repo.matrices[matrix.id].modified_date

        await service.resolve(ENTITY, {})

        assert repo.matrices[matrix.id].modified_date == before
        assert repo.tasks == {}

    async def test_the_lowest_priority_matching_matrix_wins(
        self, service: ApprovalMatrixService, repo: FakeApprovalMatrixRepository
    ) -> None:
        seed(repo, code="LATE", entity_type=ENTITY, priority=9)
        seed(repo, code="EARLY", entity_type=ENTITY, priority=1)

        result = await service.resolve(ENTITY, {})

        assert result.matrix is not None
        assert result.matrix.code == "EARLY"

    async def test_a_matrix_created_through_the_service_can_be_resolved(
        self, service: ApprovalMatrixService, actor: User
    ) -> None:
        await service.create_matrix(
            create_request(
                rules=[rule_input("amount", RuleOperator.GTE, "100000")],
                assignments=[role_level(1, 11), role_level(2, 12)],
            ),
            actor,
        )

        hit = await service.resolve(ENTITY, {"amount": 250000})
        miss = await service.resolve(ENTITY, {"amount": 99})

        assert hit.matched is True
        assert hit.levels == [1, 2]
        assert miss.matched is False
