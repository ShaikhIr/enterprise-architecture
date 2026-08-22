"""
Rule evaluator tests.

The evaluator decides which approval matrix routes a record, so a wrong answer
here sends work to the wrong approver. It is pure logic with no I/O, which makes
it the cheapest place in the engine to pin behaviour down precisely.
"""

from decimal import Decimal
from typing import Any
from uuid import uuid4

import pytest

from src.application.services.workflow.rule_evaluator import RuleEvaluator
from src.domain.entities.approval_matrix import ApprovalRule
from src.domain.enums.workflow_enums import RuleDataType, RuleOperator


def rule(
    field: str,
    operator: RuleOperator,
    value: str,
    data_type: RuleDataType = RuleDataType.STRING,
    logical_group: str = "default",
) -> ApprovalRule:
    return ApprovalRule(
        id=uuid4(),
        matrix_id=uuid4(),
        field=field,
        operator=operator,
        value=value,
        data_type=data_type,
        logical_group=logical_group,
    )


@pytest.fixture
def evaluator() -> RuleEvaluator:
    return RuleEvaluator()


class TestOperators:
    """Each operator against a matching and a non-matching record."""

    @pytest.mark.parametrize(
        ("operator", "configured", "actual", "expected"),
        [
            (RuleOperator.EQ, "OPEN", "OPEN", True),
            (RuleOperator.EQ, "OPEN", "CLOSED", False),
            (RuleOperator.NEQ, "OPEN", "CLOSED", True),
            (RuleOperator.NEQ, "OPEN", "OPEN", False),
            (RuleOperator.CONTAINS, "labour", "indian labour law", True),
            (RuleOperator.CONTAINS, "tax", "indian labour law", False),
            (RuleOperator.STARTS_WITH, "IN", "IN-MH-001", True),
            (RuleOperator.STARTS_WITH, "MH", "IN-MH-001", False),
        ],
    )
    def test_string_operators(
        self,
        evaluator: RuleEvaluator,
        operator: RuleOperator,
        configured: str,
        actual: str,
        expected: bool,
    ) -> None:
        assert (
            evaluator.matches_single(
                rule("status", operator, configured), {"status": actual}
            )
            is expected
        )

    @pytest.mark.parametrize(
        ("operator", "configured", "actual", "expected"),
        [
            (RuleOperator.GT, "100000", 250000, True),
            (RuleOperator.GT, "100000", 100000, False),
            (RuleOperator.GTE, "100000", 100000, True),
            (RuleOperator.LT, "100000", 99999, True),
            (RuleOperator.LTE, "100000", 100000, True),
            (RuleOperator.EQ, "100000", 100000, True),
        ],
    )
    def test_numeric_operators(
        self,
        evaluator: RuleEvaluator,
        operator: RuleOperator,
        configured: str,
        actual: int,
        expected: bool,
    ) -> None:
        assert (
            evaluator.matches_single(
                rule("amount", operator, configured, RuleDataType.NUMBER),
                {"amount": actual},
            )
            is expected
        )

    @pytest.mark.parametrize(
        ("operator", "actual", "expected"),
        [
            (RuleOperator.IN, "MH", True),
            (RuleOperator.IN, "TN", False),
            (RuleOperator.NOT_IN, "TN", True),
            (RuleOperator.NOT_IN, "MH", False),
        ],
    )
    def test_collection_operators(
        self,
        evaluator: RuleEvaluator,
        operator: RuleOperator,
        actual: str,
        expected: bool,
    ) -> None:
        assert (
            evaluator.matches_single(
                rule("state", operator, "MH, KA, GJ"), {"state": actual}
            )
            is expected
        )


class TestValueCasting:
    """A rule's value is always stored as text; comparison has to cast both sides."""

    def test_number_compares_numerically_not_lexically(
        self, evaluator: RuleEvaluator
    ) -> None:
        # "9" > "100000" as strings, which is the bug this cast exists to avoid.
        assert evaluator.matches_single(
            rule("amount", RuleOperator.LT, "100000", RuleDataType.NUMBER),
            {"amount": 9},
        )

    def test_number_accepts_decimal_and_string_records(
        self, evaluator: RuleEvaluator
    ) -> None:
        condition = rule("amount", RuleOperator.GTE, "500.50", RuleDataType.NUMBER)
        assert evaluator.matches_single(condition, {"amount": Decimal("500.50")})
        assert evaluator.matches_single(condition, {"amount": "600"})

    @pytest.mark.parametrize("truthy", ["true", "TRUE", "1", "yes", "on"])
    def test_boolean_truthy_spellings(
        self, evaluator: RuleEvaluator, truthy: str
    ) -> None:
        assert evaluator.matches_single(
            rule("is_critical", RuleOperator.EQ, truthy, RuleDataType.BOOLEAN),
            {"is_critical": True},
        )

    def test_boolean_matches_record_string(self, evaluator: RuleEvaluator) -> None:
        assert evaluator.matches_single(
            rule("is_critical", RuleOperator.EQ, "true", RuleDataType.BOOLEAN),
            {"is_critical": "yes"},
        )

    def test_list_data_type_splits_on_comma(self, evaluator: RuleEvaluator) -> None:
        assert evaluator.matches_single(
            rule("state", RuleOperator.IN, " MH , KA ", RuleDataType.LIST),
            {"state": "KA"},
        )


class TestFieldPaths:
    """Rules address the record by dotted path."""

    def test_reads_nested_value(self, evaluator: RuleEvaluator) -> None:
        assert evaluator.matches_single(
            rule("state.code", RuleOperator.EQ, "MH"),
            {"state": {"code": "MH", "name": "Maharashtra"}},
        )

    @pytest.mark.parametrize(
        "record",
        [
            {},
            {"state": {}},
            {"state": None},
            {"state": "MH"},  # path runs into a scalar
            {"other": {"code": "MH"}},
        ],
        ids=["empty", "empty-branch", "null-branch", "scalar-branch", "wrong-branch"],
    )
    def test_missing_path_does_not_match(
        self, evaluator: RuleEvaluator, record: dict[str, Any]
    ) -> None:
        assert not evaluator.matches_single(
            rule("state.code", RuleOperator.EQ, "MH"), record
        )


class TestGroupLogic:
    """Rules AND within a group and OR across groups."""

    def test_no_rules_matches_everything(self, evaluator: RuleEvaluator) -> None:
        # This is what makes an unconditional catch-all matrix expressible.
        assert evaluator.matches([], {})

    def test_same_group_requires_all(self, evaluator: RuleEvaluator) -> None:
        rules = [
            rule("amount", RuleOperator.GTE, "100000", RuleDataType.NUMBER, "g1"),
            rule("state", RuleOperator.EQ, "MH", RuleDataType.STRING, "g1"),
        ]
        assert evaluator.matches(rules, {"amount": 250000, "state": "MH"})
        assert not evaluator.matches(rules, {"amount": 250000, "state": "KA"})

    def test_separate_groups_are_alternatives(self, evaluator: RuleEvaluator) -> None:
        rules = [
            rule("amount", RuleOperator.GTE, "1000000", RuleDataType.NUMBER, "big"),
            rule("risk", RuleOperator.EQ, "CRITICAL", RuleDataType.STRING, "risky"),
        ]
        assert evaluator.matches(rules, {"amount": 2_000_000, "risk": "LOW"})
        assert evaluator.matches(rules, {"amount": 10, "risk": "CRITICAL"})
        assert not evaluator.matches(rules, {"amount": 10, "risk": "LOW"})

    def test_one_group_fully_matching_is_enough(self, evaluator: RuleEvaluator) -> None:
        rules = [
            rule("a", RuleOperator.EQ, "1", RuleDataType.STRING, "g1"),
            rule("b", RuleOperator.EQ, "2", RuleDataType.STRING, "g1"),
            rule("c", RuleOperator.EQ, "3", RuleDataType.STRING, "g2"),
        ]
        # g1 half-matches, g2 matches outright.
        assert evaluator.matches(rules, {"a": "1", "b": "wrong", "c": "3"})


class TestMisconfiguredRules:
    """A bad rule must not take the request down; it just fails to match."""

    def test_non_numeric_record_value_under_number_type(
        self, evaluator: RuleEvaluator
    ) -> None:
        assert not evaluator.matches_single(
            rule("amount", RuleOperator.GT, "100", RuleDataType.NUMBER),
            {"amount": "not-a-number"},
        )

    def test_non_numeric_configured_value_under_number_type(
        self, evaluator: RuleEvaluator
    ) -> None:
        assert not evaluator.matches_single(
            rule("amount", RuleOperator.GT, "abc", RuleDataType.NUMBER),
            {"amount": 500},
        )

    def test_ordering_operator_on_uncomparable_types(
        self, evaluator: RuleEvaluator
    ) -> None:
        # LIST leaves the record value untouched, so this asks Python to order a
        # dict against a list. That raises, and the evaluator must absorb it.
        assert not evaluator.matches_single(
            rule("payload", RuleOperator.GT, "a,b", RuleDataType.LIST),
            {"payload": {"nested": 1}},
        )

    def test_string_ordering_is_lexical_not_an_error(
        self, evaluator: RuleEvaluator
    ) -> None:
        # Worth stating outright: under STRING both sides are stringified, so an
        # ordering operator compares text. It is not an error, and "9" > "100".
        assert evaluator.matches_single(
            rule("amount", RuleOperator.GT, "100"), {"amount": 9}
        )

    def test_failing_rule_does_not_satisfy_its_group(
        self, evaluator: RuleEvaluator
    ) -> None:
        rules = [
            rule("amount", RuleOperator.GT, "abc", RuleDataType.NUMBER, "g1"),
            rule("state", RuleOperator.EQ, "MH", RuleDataType.STRING, "g1"),
        ]
        assert not evaluator.matches(rules, {"amount": 500, "state": "MH"})
