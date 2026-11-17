"""
Approval matrix resolver.

Given an entity type and a dictionary describing one record, finds the
highest-priority active matrix whose rules match and returns its approval levels
in order. First match wins, which is why `priority` on the matrix matters: it is
the tie-breaker between overlapping matrices.
"""

import logging
from dataclasses import dataclass
from typing import Any

from src.application.services.workflow.rule_evaluator import RuleEvaluator
from src.domain.entities.approval_matrix import ApprovalAssignment, ApprovalMatrix
from src.domain.repositories.approval_matrix_repository import IApprovalMatrixRepository

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class ResolvedApprovers:
    """The matrix that matched and the approvers it routes to, level by level."""

    matrix: ApprovalMatrix
    assignments: list[ApprovalAssignment]

    @property
    def levels(self) -> list[int]:
        """Distinct approval levels in ascending order."""
        return sorted({a.level for a in self.assignments})


class ApprovalMatrixResolver:
    """Selects the approval matrix that applies to a record."""

    def __init__(
        self,
        matrix_repo: IApprovalMatrixRepository,
        rule_evaluator: RuleEvaluator | None = None,
    ) -> None:
        self._matrices = matrix_repo
        self._rules = rule_evaluator or RuleEvaluator()

    async def resolve(
        self, entity_type: str, entity_data: dict[str, Any]
    ) -> ResolvedApprovers | None:
        """
        Find the applicable matrix, or None when nothing matches.

        Returning None rather than raising keeps this usable as a preview: an
        unrouted record is a configuration answer, not an error.
        """
        candidates = await self._matrices.list_active_for_entity_type(entity_type)
        if not candidates:
            logger.info("No active approval matrix for entity_type=%s", entity_type)
            return None

        for matrix in candidates:
            if self._rules.matches(matrix.rules, entity_data):
                logger.info(
                    "Approval matrix '%s' matched entity_type=%s", matrix.code, entity_type
                )
                return ResolvedApprovers(
                    matrix=matrix,
                    assignments=sorted(matrix.assignments, key=lambda a: a.level),
                )

        logger.info(
            "No approval matrix rules matched entity_type=%s (%d candidate(s))",
            entity_type,
            len(candidates),
        )
        return None
