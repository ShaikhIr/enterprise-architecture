"""
Workflow engine domain entities.

Four configuration aggregates (`WorkflowDefinition`, `WorkflowStatus`,
`WorkflowTransition`) plus the runtime pair (`WorkflowInstance` and its
append-only `WorkflowHistoryEntry` trail).

`WorkflowHistoryEntry` deliberately does not extend `BaseEntity`: history rows
are never updated, so `modified_by` / `modified_date` would always be noise.
"""

from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any
from uuid import UUID, uuid4

from src.domain.entities.base_entity import BaseEntity
from src.domain.enums.workflow_enums import WorkflowActionType


@dataclass(kw_only=True)
class WorkflowDefinition(BaseEntity):
    """A named, versioned state machine bound to one business entity type."""

    code: str
    name: str
    entity_type: str
    description: str = ""
    version: int = 1
    is_active: bool = True

    def deactivate(self) -> None:
        """Retire the definition without deleting its history."""
        self.is_active = False


@dataclass(kw_only=True)
class WorkflowStatus(BaseEntity):
    """One state within a workflow definition."""

    workflow_definition_id: UUID
    code: str
    name: str
    is_initial: bool = False
    is_terminal: bool = False
    sequence: int = 0


@dataclass(kw_only=True)
class WorkflowTransition(BaseEntity):
    """A permitted move between two states, triggered by an action code."""

    workflow_definition_id: UUID
    from_status_id: UUID
    to_status_id: UUID
    action_code: str
    # What this move means for the approval chain. Free-text `action_code` cannot
    # carry that meaning, so the designer declares it here.
    action_type: WorkflowActionType = WorkflowActionType.CUSTOM
    guard_expression: str | None = None
    requires_comment: bool = False
    auto_execute: bool = False
    priority: int = 0


@dataclass(kw_only=True)
class WorkflowInstance(BaseEntity):
    """A running (or finished) execution of a definition against one record."""

    workflow_definition_id: UUID
    entity_type: str
    entity_id: UUID
    current_status_id: UUID
    initiated_by: UUID
    priority: int = 0
    due_date: datetime | None = None
    started_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    completed_at: datetime | None = None
    extra_data: dict[str, Any] = field(default_factory=dict)
    # Which approval level the instance is currently waiting on; 0 means no chain
    # is running. Stored rather than derived so a refer-back can reset it without
    # the engine having to reinterpret task history.
    approval_level: int = 0

    @property
    def is_completed(self) -> bool:
        """True once the instance has reached a terminal state."""
        return self.completed_at is not None

    @property
    def is_awaiting_approval(self) -> bool:
        """True while an approval level is open."""
        return self.approval_level > 0

    def move_to(self, status_id: UUID, *, is_terminal: bool) -> None:
        """Advance to a new state, stamping completion when it is terminal."""
        self.current_status_id = status_id
        if is_terminal:
            self.completed_at = datetime.now(UTC)


@dataclass(kw_only=True)
class WorkflowHistoryEntry:
    """Immutable record of one executed transition."""

    instance_id: UUID
    to_status_id: UUID
    action_code: str
    id: UUID = field(default_factory=uuid4)
    from_status_id: UUID | None = None
    actor_id: UUID | None = None
    actor_username: str = ""
    comments: str = ""
    extra_data: dict[str, Any] = field(default_factory=dict)
    ip_address: str = ""
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC))
