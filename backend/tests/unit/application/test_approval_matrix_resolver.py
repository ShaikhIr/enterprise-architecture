"""
Approval matrix resolver tests.

The resolver decides which matrix routes a record: candidates arrive from the
repository already ordered by priority, the first whose rules match wins, and no match
is an answer (`None`), not an error. These tests pin down that selection, the ordering of
the levels it returns, and its use of the injected rule evaluator.
"""

from typing import Any

import pytest
from workflow_fakes import FakeApprovalMatrixRepository, build_matrix

from src.application.services.workflow.approval_matrix_resolver import (
    ApprovalMatrixResolver,
    ResolvedApprovers,
)
from src.application.services.workflow.rule_evaluator import RuleEvaluator
from src.domain.entities.approval_matrix import ApprovalMatrix, ApprovalRule
from src.domain.enums.workflow_enums import AssignmentType

ENTITY = "compliance_task"
AMOUNT_OVER_1000 = [("amount", "GT", "1000", "NUMBER")]
AMOUNT_UNDER_1000 = [("amount", "LTE", "1000", "NUMBER")]


class RecordingMatrixRepository(FakeApprovalMatrixRepository):
    """The shared fake plus a log of which entity types were asked for."""

    def __init__(self) -> None:
        super().__init__()
        self.requested_entity_types: list[str] = []

    async def list_active_for_entity_type(self, entity_type: str) -> list[ApprovalMatrix]:
        self.requested_entity_types.append(entity_type)
        return await super().list_active_for_entity_type(entity_type)


class StubEvaluator(RuleEvaluator):
    """Evaluator whose verdict is fixed, to show the resolver defers to it."""

    def __init__(self, verdict: bool) -> None:
        self._verdict = verdict
        self.seen: list[tuple[list[ApprovalRule], dict[str, Any]]] = []

    def matches(self, rules: list[ApprovalRule], entity_data: dict[str, Any]) -> bool:
        self.seen.append((rules, entity_data))
        return self._verdict


@pytest.fixture
def repo() -> RecordingMatrixRepository:
    return RecordingMatrixRepository()


@pytest.fixture
def resolver(repo: RecordingMatrixRepository) -> ApprovalMatrixResolver:
    return ApprovalMatrixResolver(repo)


def add(repo: FakeApprovalMatrixRepository, matrix: ApprovalMatrix) -> ApprovalMatrix:
    repo.matrices[matrix.id] = matrix
    return matrix


class TestResolve:
    async def test_no_matrices_for_the_entity_type_resolves_to_none(
        self, resolver: ApprovalMatrixResolver
    ) -> None:
        assert await resolver.resolve(ENTITY, {"amount": 5}) is None

    async def test_the_repository_is_asked_for_the_given_entity_type(
        self, resolver: ApprovalMatrixResolver, repo: RecordingMatrixRepository
    ) -> None:
        await resolver.resolve(ENTITY, {})

        assert repo.requested_entity_types == [ENTITY]

    async def test_matrices_of_another_entity_type_are_not_considered(
        self, resolver: ApprovalMatrixResolver, repo: RecordingMatrixRepository
    ) -> None:
        add(repo, build_matrix(code="OTHER", entity_type="invoice"))

        assert await resolver.resolve(ENTITY, {}) is None

    async def test_inactive_matrices_are_not_considered(
        self, resolver: ApprovalMatrixResolver, repo: RecordingMatrixRepository
    ) -> None:
        add(repo, build_matrix(code="OFF", entity_type=ENTITY, is_active=False))

        assert await resolver.resolve(ENTITY, {}) is None

    async def test_matrix_without_rules_is_the_catch_all(
        self, resolver: ApprovalMatrixResolver, repo: RecordingMatrixRepository
    ) -> None:
        matrix = add(repo, build_matrix(code="CATCH_ALL", entity_type=ENTITY))

        resolved = await resolver.resolve(ENTITY, {"anything": "at all"})

        assert resolved is not None
        assert resolved.matrix.id == matrix.id

    async def test_matrix_whose_rules_match_is_returned(
        self, resolver: ApprovalMatrixResolver, repo: RecordingMatrixRepository
    ) -> None:
        matrix = add(
            repo, build_matrix(code="BIG", entity_type=ENTITY, rules=AMOUNT_OVER_1000)
        )

        resolved = await resolver.resolve(ENTITY, {"amount": 5000})

        assert resolved is not None
        assert resolved.matrix.code == "BIG"
        assert resolved.matrix.id == matrix.id

    async def test_matrix_whose_rules_do_not_match_resolves_to_none(
        self, resolver: ApprovalMatrixResolver, repo: RecordingMatrixRepository
    ) -> None:
        add(repo, build_matrix(code="BIG", entity_type=ENTITY, rules=AMOUNT_OVER_1000))

        assert await resolver.resolve(ENTITY, {"amount": 10}) is None

    async def test_record_missing_the_rule_field_resolves_to_none(
        self, resolver: ApprovalMatrixResolver, repo: RecordingMatrixRepository
    ) -> None:
        add(repo, build_matrix(code="BIG", entity_type=ENTITY, rules=AMOUNT_OVER_1000))

        assert await resolver.resolve(ENTITY, {"other": 1}) is None

    async def test_lowest_priority_number_wins_when_several_match(
        self, resolver: ApprovalMatrixResolver, repo: RecordingMatrixRepository
    ) -> None:
        add(repo, build_matrix(code="LATE", entity_type=ENTITY, priority=20))
        add(repo, build_matrix(code="EARLY", entity_type=ENTITY, priority=5))
        add(repo, build_matrix(code="MIDDLE", entity_type=ENTITY, priority=10))

        resolved = await resolver.resolve(ENTITY, {})

        assert resolved is not None
        assert resolved.matrix.code == "EARLY"

    async def test_a_non_matching_higher_priority_matrix_is_skipped(
        self, resolver: ApprovalMatrixResolver, repo: RecordingMatrixRepository
    ) -> None:
        add(
            repo,
            build_matrix(
                code="BIG", entity_type=ENTITY, priority=1, rules=AMOUNT_OVER_1000
            ),
        )
        add(
            repo,
            build_matrix(
                code="SMALL", entity_type=ENTITY, priority=2, rules=AMOUNT_UNDER_1000
            ),
        )

        resolved = await resolver.resolve(ENTITY, {"amount": 50})

        assert resolved is not None
        assert resolved.matrix.code == "SMALL"

    async def test_priority_decides_between_two_matching_rule_sets(
        self, resolver: ApprovalMatrixResolver, repo: RecordingMatrixRepository
    ) -> None:
        add(
            repo,
            build_matrix(
                code="BROAD", entity_type=ENTITY, priority=9, rules=AMOUNT_OVER_1000
            ),
        )
        add(
            repo,
            build_matrix(
                code="NARROW",
                entity_type=ENTITY,
                priority=3,
                rules=[("amount", "GT", "100", "NUMBER")],
            ),
        )

        resolved = await resolver.resolve(ENTITY, {"amount": 5000})

        assert resolved is not None
        assert resolved.matrix.code == "NARROW"

    async def test_catch_all_with_a_later_priority_is_the_fallback(
        self, resolver: ApprovalMatrixResolver, repo: RecordingMatrixRepository
    ) -> None:
        add(
            repo,
            build_matrix(
                code="BIG", entity_type=ENTITY, priority=1, rules=AMOUNT_OVER_1000
            ),
        )
        add(repo, build_matrix(code="DEFAULT", entity_type=ENTITY, priority=99))

        resolved = await resolver.resolve(ENTITY, {"amount": 1})

        assert resolved is not None
        assert resolved.matrix.code == "DEFAULT"


class TestResolvedApprovers:
    async def test_assignments_are_ordered_by_level(
        self, resolver: ApprovalMatrixResolver, repo: RecordingMatrixRepository
    ) -> None:
        add(
            repo,
            build_matrix(
                entity_type=ENTITY,
                levels=[
                    (3, AssignmentType.ROLE, 30),
                    (1, AssignmentType.USER, 10),
                    (2, AssignmentType.ROLE, 20),
                ],
            ),
        )

        resolved = await resolver.resolve(ENTITY, {})

        assert resolved is not None
        assert [a.level for a in resolved.assignments] == [1, 2, 3]
        assert [a.user_id or a.role_id for a in resolved.assignments] == [10, 20, 30]

    async def test_levels_are_distinct_and_ascending(
        self, resolver: ApprovalMatrixResolver, repo: RecordingMatrixRepository
    ) -> None:
        add(
            repo,
            build_matrix(
                entity_type=ENTITY,
                levels=[
                    (2, AssignmentType.ROLE, 20),
                    (1, AssignmentType.ROLE, 10),
                    (2, AssignmentType.ROLE, 21),
                ],
            ),
        )

        resolved = await resolver.resolve(ENTITY, {})

        assert resolved is not None
        assert resolved.levels == [1, 2]
        assert len(resolved.assignments) == 3

    async def test_matrix_without_assignments_has_no_levels(
        self, resolver: ApprovalMatrixResolver, repo: RecordingMatrixRepository
    ) -> None:
        add(repo, build_matrix(entity_type=ENTITY))

        resolved = await resolver.resolve(ENTITY, {})

        assert resolved is not None
        assert resolved.assignments == []
        assert resolved.levels == []

    async def test_sorting_does_not_reorder_the_matrix_itself(
        self, resolver: ApprovalMatrixResolver, repo: RecordingMatrixRepository
    ) -> None:
        add(
            repo,
            build_matrix(
                entity_type=ENTITY,
                levels=[(2, AssignmentType.ROLE, 20), (1, AssignmentType.ROLE, 10)],
            ),
        )

        resolved = await resolver.resolve(ENTITY, {})

        assert resolved is not None
        assert [a.level for a in resolved.matrix.assignments] == [2, 1]

    def test_levels_property_of_an_empty_result_is_empty(self) -> None:
        resolved = ResolvedApprovers(matrix=build_matrix(), assignments=[])

        assert resolved.levels == []


class TestInjectedEvaluator:
    async def test_the_injected_evaluator_decides_a_match(
        self, repo: RecordingMatrixRepository
    ) -> None:
        # The matrix has a rule that would not match; the stub says it does.
        matrix = add(
            repo, build_matrix(code="BIG", entity_type=ENTITY, rules=AMOUNT_OVER_1000)
        )
        evaluator = StubEvaluator(verdict=True)
        resolver = ApprovalMatrixResolver(repo, rule_evaluator=evaluator)

        resolved = await resolver.resolve(ENTITY, {"amount": 1})

        assert resolved is not None
        assert resolved.matrix.id == matrix.id

    async def test_the_injected_evaluator_can_veto_every_matrix(
        self, repo: RecordingMatrixRepository
    ) -> None:
        add(repo, build_matrix(code="CATCH_ALL", entity_type=ENTITY))
        resolver = ApprovalMatrixResolver(repo, rule_evaluator=StubEvaluator(verdict=False))

        assert await resolver.resolve(ENTITY, {}) is None

    async def test_the_evaluator_receives_the_matrix_rules_and_the_record(
        self, repo: RecordingMatrixRepository
    ) -> None:
        add(repo, build_matrix(code="BIG", entity_type=ENTITY, rules=AMOUNT_OVER_1000))
        evaluator = StubEvaluator(verdict=True)
        resolver = ApprovalMatrixResolver(repo, rule_evaluator=evaluator)
        record = {"amount": 7}

        await resolver.resolve(ENTITY, record)

        ((rules, seen_record),) = evaluator.seen
        assert [r.field for r in rules] == ["amount"]
        assert seen_record == record

    async def test_first_match_stops_evaluation_of_lower_priority_matrices(
        self, repo: RecordingMatrixRepository
    ) -> None:
        add(repo, build_matrix(code="FIRST", entity_type=ENTITY, priority=1))
        add(repo, build_matrix(code="SECOND", entity_type=ENTITY, priority=2))
        evaluator = StubEvaluator(verdict=True)
        resolver = ApprovalMatrixResolver(repo, rule_evaluator=evaluator)

        await resolver.resolve(ENTITY, {})

        assert len(evaluator.seen) == 1
