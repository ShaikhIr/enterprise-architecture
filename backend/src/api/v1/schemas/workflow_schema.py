"""
Pydantic schemas for the workflow engine API.

Split into three groups: definition configuration, state machine wiring
(statuses and transitions), and runtime (instances, actions, history).

Codes are normalised to upper snake case on the way in, so `commission claim`
and `Commission_Claim` cannot both exist as separate workflows.
"""

from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field, field_validator

from src.domain.enums.workflow_enums import WorkflowActionType


def _normalise_code(value: str) -> str:
    return value.strip().upper().replace(" ", "_").replace("-", "_")


# ─── Workflow definitions ───


class WorkflowDefinitionCreate(BaseModel):
    """Create a workflow definition."""

    code: str = Field(..., min_length=2, max_length=100, examples=["RETURN_FILING"])
    name: str = Field(
        ..., min_length=2, max_length=255, examples=["Return Filing Approval"]
    )
    entity_type: str = Field(..., min_length=2, max_length=100, examples=["task"])
    description: str = Field(default="", examples=["Maker-checker flow for filings"])
    is_active: bool = Field(default=True)

    @field_validator("code")
    @classmethod
    def _upper(cls, value: str) -> str:
        return _normalise_code(value)

    @field_validator("name", "entity_type")
    @classmethod
    def _trim(cls, value: str) -> str:
        return value.strip()


class WorkflowDefinitionUpdate(BaseModel):
    """Update a workflow definition. Only supplied fields are changed."""

    code: str | None = Field(default=None, min_length=2, max_length=100)
    name: str | None = Field(default=None, min_length=2, max_length=255)
    entity_type: str | None = Field(default=None, min_length=2, max_length=100)
    description: str | None = Field(default=None)
    is_active: bool | None = Field(default=None)

    @field_validator("code")
    @classmethod
    def _upper(cls, value: str | None) -> str | None:
        return _normalise_code(value) if value else value

    @field_validator("name", "entity_type")
    @classmethod
    def _trim(cls, value: str | None) -> str | None:
        return value.strip() if value else value


class WorkflowDefinitionResponse(BaseModel):
    """Workflow definition read response."""

    id: int
    code: str
    name: str
    description: str
    entity_type: str
    version: int
    is_active: bool
    created_by: str
    created_date: datetime
    modified_by: str
    modified_date: datetime

    model_config = {"from_attributes": True}


class WorkflowDefinitionListResponse(BaseModel):
    """Paginated list of workflow definitions."""

    definitions: list[WorkflowDefinitionResponse]
    total: int
    skip: int
    limit: int


# ─── Statuses ───


class WorkflowStatusCreate(BaseModel):
    """Add a state to a workflow definition."""

    code: str = Field(..., min_length=2, max_length=50, examples=["DRAFT"])
    name: str = Field(..., min_length=1, max_length=255, examples=["Draft"])
    is_initial: bool = Field(default=False)
    is_terminal: bool = Field(default=False)
    sequence: int = Field(default=0, ge=0)

    @field_validator("code")
    @classmethod
    def _upper(cls, value: str) -> str:
        return _normalise_code(value)

    @field_validator("name")
    @classmethod
    def _trim(cls, value: str) -> str:
        return value.strip()


class WorkflowStatusUpdate(BaseModel):
    """Update a state. Only supplied fields are changed."""

    code: str | None = Field(default=None, min_length=2, max_length=50)
    name: str | None = Field(default=None, min_length=1, max_length=255)
    is_initial: bool | None = Field(default=None)
    is_terminal: bool | None = Field(default=None)
    sequence: int | None = Field(default=None, ge=0)

    @field_validator("code")
    @classmethod
    def _upper(cls, value: str | None) -> str | None:
        return _normalise_code(value) if value else value

    @field_validator("name")
    @classmethod
    def _trim(cls, value: str | None) -> str | None:
        return value.strip() if value else value


class WorkflowStatusResponse(BaseModel):
    """Workflow state read response."""

    id: int
    workflow_definition_id: int
    code: str
    name: str
    is_initial: bool
    is_terminal: bool
    sequence: int

    model_config = {"from_attributes": True}


# ─── Transitions ───


class WorkflowTransitionCreate(BaseModel):
    """Wire an action from one state to another."""

    from_status_id: int
    to_status_id: int
    action_code: str = Field(..., min_length=2, max_length=50, examples=["APPROVE"])
    action_type: WorkflowActionType = Field(
        default=WorkflowActionType.CUSTOM,
        description=(
            "What this move means for the approval chain. SUBMIT opens level 1, "
            "APPROVE steps to the next level, REJECT/CANCEL/REFER_BACK tear the "
            "chain down. CUSTOM leaves approvals untouched."
        ),
    )
    guard_expression: str | None = Field(default=None, max_length=2000)
    requires_comment: bool = Field(default=False)
    auto_execute: bool = Field(default=False)
    priority: int = Field(default=0, ge=0)

    @field_validator("action_code")
    @classmethod
    def _upper(cls, value: str) -> str:
        return _normalise_code(value)


class WorkflowTransitionResponse(BaseModel):
    """Workflow transition read response."""

    id: int
    workflow_definition_id: int
    from_status_id: int
    to_status_id: int
    action_code: str
    action_type: WorkflowActionType
    guard_expression: str | None
    requires_comment: bool
    auto_execute: bool
    priority: int

    model_config = {"from_attributes": True}


class WorkflowDefinitionDetailResponse(BaseModel):
    """A definition with its full state machine, as the builder screen needs it."""

    definition: WorkflowDefinitionResponse
    statuses: list[WorkflowStatusResponse]
    transitions: list[WorkflowTransitionResponse]


# ─── Runtime ───


class WorkflowStartRequest(BaseModel):
    """Open a workflow instance against one business record."""

    definition_code: str = Field(..., min_length=2, max_length=100)
    entity_type: str = Field(..., min_length=2, max_length=100)
    entity_id: int
    priority: int = Field(default=0, ge=0)
    metadata: dict[str, Any] = Field(
        default_factory=dict,
        description="Record snapshot used for approval routing and audit context",
    )

    @field_validator("definition_code")
    @classmethod
    def _upper(cls, value: str) -> str:
        return _normalise_code(value)

    @field_validator("entity_type")
    @classmethod
    def _trim(cls, value: str) -> str:
        return value.strip()


class WorkflowActionRequest(BaseModel):
    """Execute an action on a running instance."""

    action_code: str = Field(..., min_length=2, max_length=50)
    comments: str = Field(default="", max_length=4000)

    @field_validator("action_code")
    @classmethod
    def _upper(cls, value: str) -> str:
        return _normalise_code(value)


class WorkflowInstanceResponse(BaseModel):
    """
    Runtime view of one instance.

    Carries the resolved status code and name alongside the id so callers do not
    have to fetch the definition to render a row.
    """

    id: int
    workflow_definition_id: int
    definition_code: str
    definition_name: str
    entity_type: str
    entity_id: int
    current_status_id: int
    current_status_code: str
    current_status_name: str
    is_terminal: bool
    initiated_by: int
    priority: int
    due_date: datetime | None
    started_at: datetime
    completed_at: datetime | None
    is_completed: bool
    approval_level: int = Field(
        default=0, description="Approval level currently open; 0 means none"
    )
    is_awaiting_approval: bool = False
    metadata: dict[str, Any] = Field(default_factory=dict)


class WorkflowInstanceListResponse(BaseModel):
    """Paginated list of workflow instances."""

    instances: list[WorkflowInstanceResponse]
    total: int
    skip: int
    limit: int


class WorkflowAvailableActionResponse(BaseModel):
    """One action offered from the instance's current state."""

    action_code: str
    # Exposed so a caller can tell an approval from a rejection without having to
    # pattern-match the free-text action code.
    action_type: WorkflowActionType
    to_status_id: int
    to_status_code: str
    to_status_name: str
    requires_comment: bool
    is_terminal: bool


class WorkflowHistoryResponse(BaseModel):
    """One executed transition from the audit trail."""

    id: int
    instance_id: int
    from_status_id: int | None
    from_status_code: str | None
    to_status_id: int
    to_status_code: str | None
    action_code: str
    actor_id: int | None
    actor_username: str
    comments: str
    ip_address: str
    created_at: datetime
