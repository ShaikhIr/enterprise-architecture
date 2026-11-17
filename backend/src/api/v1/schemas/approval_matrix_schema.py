"""
Pydantic schemas for the approval matrix API.

A matrix is created and updated as one document — basics plus rules plus approval
levels — because that is how it is edited and because a half-saved matrix would
route records incorrectly rather than merely look incomplete.
"""

from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field, field_validator, model_validator

from src.domain.enums.workflow_enums import (
    ApprovalTaskStatus,
    AssignmentType,
    RuleDataType,
    RuleOperator,
)

# ─── Rules and assignments ───


class ApprovalRuleInput(BaseModel):
    """One routing condition, e.g. `amount GTE 100000`."""

    field: str = Field(..., min_length=1, max_length=100, examples=["amount"])
    operator: RuleOperator = Field(default=RuleOperator.EQ)
    value: str = Field(..., min_length=1, max_length=500, examples=["100000"])
    data_type: RuleDataType = Field(default=RuleDataType.STRING)
    logical_group: str = Field(default="default", min_length=1, max_length=50)

    @field_validator("field", "logical_group")
    @classmethod
    def _trim(cls, value: str) -> str:
        return value.strip()


class ApprovalRuleResponse(BaseModel):
    """Routing condition read response."""

    id: int
    field: str
    operator: RuleOperator
    value: str
    data_type: RuleDataType
    logical_group: str

    model_config = {"from_attributes": True}


class ApprovalAssignmentInput(BaseModel):
    """One approver at one approval level."""

    level: int = Field(default=1, ge=1, le=99)
    assignment_type: AssignmentType = Field(default=AssignmentType.ROLE)
    user_id: int | None = Field(default=None)
    role_id: int | None = Field(default=None)

    @model_validator(mode="after")
    def _require_matching_target(self) -> "ApprovalAssignmentInput":
        """
        A USER level must name a user and a ROLE level must name a role.

        Without this an approval level can be saved pointing at nothing, which
        silently drops that level at routing time.
        """
        if self.assignment_type == AssignmentType.USER and self.user_id is None:
            raise ValueError("assignment_type 'USER' requires user_id")
        if self.assignment_type == AssignmentType.ROLE and self.role_id is None:
            raise ValueError("assignment_type 'ROLE' requires role_id")
        return self


class ApprovalAssignmentResponse(BaseModel):
    """Approval level read response."""

    id: int
    level: int
    assignment_type: AssignmentType
    user_id: int | None
    role_id: int | None

    model_config = {"from_attributes": True}


# ─── Matrices ───


class ApprovalMatrixCreate(BaseModel):
    """Create an approval matrix with its rules and levels."""

    code: str = Field(..., min_length=2, max_length=100, examples=["FILING_BY_AMOUNT"])
    name: str = Field(
        ..., min_length=2, max_length=255, examples=["Filing approval by amount"]
    )
    entity_type: str = Field(..., min_length=2, max_length=100, examples=["task"])
    priority: int = Field(
        default=0,
        ge=0,
        description="Lower runs first; the first matrix whose rules match wins",
    )
    is_active: bool = Field(default=True)
    rules: list[ApprovalRuleInput] = Field(default_factory=list)
    assignments: list[ApprovalAssignmentInput] = Field(default_factory=list)

    @field_validator("code")
    @classmethod
    def _upper(cls, value: str) -> str:
        return value.strip().upper().replace(" ", "_").replace("-", "_")

    @field_validator("name", "entity_type")
    @classmethod
    def _trim(cls, value: str) -> str:
        return value.strip()


class ApprovalMatrixUpdate(BaseModel):
    """
    Update an approval matrix.

    Supplying `rules` or `assignments` replaces that collection wholesale;
    omitting it leaves the stored one untouched.
    """

    name: str | None = Field(default=None, min_length=2, max_length=255)
    entity_type: str | None = Field(default=None, min_length=2, max_length=100)
    priority: int | None = Field(default=None, ge=0)
    is_active: bool | None = Field(default=None)
    rules: list[ApprovalRuleInput] | None = Field(default=None)
    assignments: list[ApprovalAssignmentInput] | None = Field(default=None)

    @field_validator("name", "entity_type")
    @classmethod
    def _trim(cls, value: str | None) -> str | None:
        return value.strip() if value else value


class ApprovalMatrixResponse(BaseModel):
    """Approval matrix read response, including its rules and levels."""

    id: int
    code: str
    name: str
    entity_type: str
    priority: int
    is_active: bool
    rules: list[ApprovalRuleResponse]
    assignments: list[ApprovalAssignmentResponse]
    created_by: str
    created_date: datetime
    modified_by: str
    modified_date: datetime

    model_config = {"from_attributes": True}


class ApprovalMatrixListResponse(BaseModel):
    """Paginated list of approval matrices."""

    matrices: list[ApprovalMatrixResponse]
    total: int
    skip: int
    limit: int


# ─── Resolution preview ───


class ApprovalResolveRequest(BaseModel):
    """Ask which matrix would route a sample record."""

    entity_type: str = Field(..., min_length=2, max_length=100)
    entity_data: dict[str, Any] = Field(
        default_factory=dict,
        description="Sample record; dotted rule fields read into nested objects",
        examples=[{"amount": 250000, "state": {"code": "MH"}}],
    )

    @field_validator("entity_type")
    @classmethod
    def _trim(cls, value: str) -> str:
        return value.strip()


class ApprovalResolveResponse(BaseModel):
    """Which matrix matched, and the approval chain it produces."""

    matched: bool
    matrix: ApprovalMatrixResponse | None = None
    levels: list[int] = Field(default_factory=list)
    assignments: list[ApprovalAssignmentResponse] = Field(default_factory=list)


# ─── Approval tasks ───


class ApprovalTaskResponse(BaseModel):
    """One approval task in a user's queue."""

    id: int
    instance_id: int
    matrix_id: int | None
    assignee_id: int
    level: int
    status: ApprovalTaskStatus
    action_taken: str | None
    due_date: datetime | None
    comments: str | None
    created_date: datetime

    model_config = {"from_attributes": True}
