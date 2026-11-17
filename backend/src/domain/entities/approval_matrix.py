"""
Approval matrix domain entities.

`ApprovalMatrix` is an aggregate: it owns its `rules` (the conditions that decide
whether the matrix applies to a record) and its `assignments` (the ordered
approval levels to route to when it does). Repositories persist the whole
aggregate in one call, so a matrix can never be stored with half its rules.

`dataclasses.field` is referenced through the module rather than imported bare,
because `ApprovalRule` has an attribute literally named `field` and the two
would otherwise read as the same thing.
"""

import dataclasses
from dataclasses import dataclass
from datetime import datetime

from src.domain.entities.base_entity import BaseEntity
from src.domain.enums.workflow_enums import (
    ApprovalTaskStatus,
    AssignmentType,
    RuleDataType,
    RuleOperator,
)


@dataclass(kw_only=True)
class ApprovalRule(BaseEntity):
    """One condition on a matrix, e.g. `amount GTE 100000`."""

    matrix_id: int | None = None
    field: str
    operator: RuleOperator = RuleOperator.EQ
    value: str
    data_type: RuleDataType = RuleDataType.STRING
    logical_group: str = "default"


@dataclass(kw_only=True)
class ApprovalAssignment(BaseEntity):
    """One approval level on a matrix, resolved to a role or a specific user."""

    matrix_id: int | None = None
    assignment_type: AssignmentType = AssignmentType.ROLE
    user_id: int | None = None
    role_id: int | None = None
    level: int = 1


@dataclass(kw_only=True)
class ApprovalMatrix(BaseEntity):
    """Routing table for one entity type, selected by rule match then priority."""

    code: str
    name: str
    entity_type: str
    priority: int = 0
    is_active: bool = True
    rules: list[ApprovalRule] = dataclasses.field(default_factory=list)
    assignments: list[ApprovalAssignment] = dataclasses.field(default_factory=list)

    @property
    def levels(self) -> list[int]:
        """Distinct approval levels defined on the matrix, in order."""
        return sorted({a.level for a in self.assignments})

    def assignments_for_level(self, level: int) -> list[ApprovalAssignment]:
        """Approvers configured for a single level."""
        return [a for a in self.assignments if a.level == level]


@dataclass(kw_only=True)
class ApprovalTask(BaseEntity):
    """A pending or completed approval action owned by one user."""

    instance_id: int
    assignee_id: int
    matrix_id: int | None = None
    level: int = 1
    status: ApprovalTaskStatus = ApprovalTaskStatus.PENDING
    action_taken: str | None = None
    due_date: datetime | None = None
    comments: str | None = None

    @property
    def is_open(self) -> bool:
        """True while the task still awaits a decision."""
        return self.status == ApprovalTaskStatus.PENDING
