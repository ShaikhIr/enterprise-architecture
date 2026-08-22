"""
Approval rule evaluator.

Pure logic: given a matrix's rules and a dictionary describing the record being
routed, decide whether the matrix applies. No database, no clock, no I/O — which
is what makes the routing decisions cheap to unit test.

Semantics: rules sharing a `logical_group` are ANDed, and groups are ORed against
each other. An empty rule set matches everything, so a matrix with no conditions
acts as the catch-all for its entity type.
"""

import logging
from collections.abc import Callable
from decimal import Decimal, InvalidOperation
from typing import Any

from src.domain.entities.approval_matrix import ApprovalRule
from src.domain.enums.workflow_enums import RuleDataType, RuleOperator

logger = logging.getLogger(__name__)

_TRUTHY = frozenset({"true", "1", "yes", "y", "on"})

# Comparators take (value from the record, value configured on the rule).
_Comparator = Callable[[Any, Any], bool]

OPERATORS: dict[RuleOperator, _Comparator] = {
    RuleOperator.EQ: lambda actual, expected: bool(actual == expected),
    RuleOperator.NEQ: lambda actual, expected: bool(actual != expected),
    RuleOperator.GT: lambda actual, expected: bool(actual > expected),
    RuleOperator.GTE: lambda actual, expected: bool(actual >= expected),
    RuleOperator.LT: lambda actual, expected: bool(actual < expected),
    RuleOperator.LTE: lambda actual, expected: bool(actual <= expected),
    RuleOperator.IN: lambda actual, expected: actual in expected,
    RuleOperator.NOT_IN: lambda actual, expected: actual not in expected,
    RuleOperator.CONTAINS: lambda actual, expected: str(expected) in str(actual),
    RuleOperator.STARTS_WITH: lambda actual, expected: str(actual).startswith(
        str(expected)
    ),
}

# Operators that compare against a collection, so the rule's stored value is
# split into a list even when its declared data type is not LIST.
_COLLECTION_OPERATORS = frozenset({RuleOperator.IN, RuleOperator.NOT_IN})


def _split_list(value: str) -> list[str]:
    return [part.strip() for part in value.split(",") if part.strip()]


def _cast_expected(rule: ApprovalRule) -> Any:
    """Cast the rule's stored string into the type its comparison needs."""
    if rule.operator in _COLLECTION_OPERATORS:
        return _split_list(rule.value)
    if rule.data_type == RuleDataType.NUMBER:
        return Decimal(rule.value)
    if rule.data_type == RuleDataType.BOOLEAN:
        return rule.value.strip().lower() in _TRUTHY
    if rule.data_type == RuleDataType.LIST:
        return _split_list(rule.value)
    return rule.value


def _cast_actual(rule: ApprovalRule, actual: Any) -> Any:
    """Bring the record's value into the same type as the rule's value."""
    if rule.operator in _COLLECTION_OPERATORS:
        return str(actual)
    if rule.data_type == RuleDataType.NUMBER:
        return actual if isinstance(actual, Decimal) else Decimal(str(actual))
    if rule.data_type == RuleDataType.BOOLEAN:
        if isinstance(actual, bool):
            return actual
        return str(actual).strip().lower() in _TRUTHY
    if rule.data_type == RuleDataType.LIST:
        return actual
    return str(actual)


def _read_path(data: dict[str, Any], path: str) -> Any:
    """
    Read a dotted path out of the record, e.g. `claim.amount`.

    Returns None when any segment is missing or when the path runs into a
    non-mapping value, which the caller treats as "rule does not match".
    """
    current: Any = data
    for segment in path.split("."):
        if not isinstance(current, dict):
            return None
        current = current.get(segment)
        if current is None:
            return None
    return current


class RuleEvaluator:
    """Decides whether a set of approval rules matches a record."""

    def matches(self, rules: list[ApprovalRule], entity_data: dict[str, Any]) -> bool:
        """
        True when every rule in at least one logical group matches.

        An empty rule set matches, so an unconditional matrix is expressible.
        """
        if not rules:
            return True

        groups: dict[str, list[ApprovalRule]] = {}
        for rule in rules:
            groups.setdefault(rule.logical_group, []).append(rule)

        return any(
            all(self.matches_single(rule, entity_data) for rule in group)
            for group in groups.values()
        )

    def matches_single(self, rule: ApprovalRule, entity_data: dict[str, Any]) -> bool:
        """Evaluate one condition, returning False rather than raising on bad data."""
        actual = _read_path(entity_data, rule.field)
        if actual is None:
            logger.debug("Rule field '%s' absent from record", rule.field)
            return False

        comparator = OPERATORS.get(rule.operator)
        if comparator is None:
            logger.warning("Unsupported rule operator: %s", rule.operator)
            return False

        try:
            result = comparator(_cast_actual(rule, actual), _cast_expected(rule))
        except (ArithmeticError, InvalidOperation, TypeError, ValueError) as exc:
            # A misconfigured rule must not take down the request; treat it as a
            # non-match and leave a trace for whoever configured it.
            logger.warning(
                "Rule '%s %s %s' could not be evaluated: %s",
                rule.field,
                rule.operator,
                rule.value,
                exc,
            )
            return False

        logger.debug(
            "Rule %s %s %s -> %s", rule.field, rule.operator, rule.value, result
        )
        return result
