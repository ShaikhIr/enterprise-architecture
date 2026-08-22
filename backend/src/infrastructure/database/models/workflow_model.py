"""
SQLAlchemy ORM models for the workflow engine.

Configuration (`workflow_definitions` -> `workflow_statuses` ->
`workflow_transitions`) cascades on delete, because removing a definition should
take its own states and edges with it. Runtime rows (`workflow_instances`,
`workflow_history`) hold RESTRICT references onto configuration so a status that
something is sitting in cannot be deleted out from under it.

The JSONB column is named `extra_data`, not `metadata`: `metadata` is reserved on
SQLAlchemy declarative classes.
"""

import uuid
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import (
    Boolean,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from src.infrastructure.database.models.base_model import Base, BaseModel


class WorkflowDefinitionModel(BaseModel):
    """A named, versioned state machine bound to one business entity type."""

    __tablename__ = "workflow_definitions"

    code: Mapped[str] = mapped_column(
        String(100), unique=True, nullable=False, index=True
    )
    name: Mapped[str] = mapped_column(
        String(255), unique=True, nullable=False, index=True
    )
    description: Mapped[str] = mapped_column(Text, default="", nullable=False)
    entity_type: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    version: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)


class WorkflowStatusModel(BaseModel):
    """One state within a workflow definition."""

    __tablename__ = "workflow_statuses"
    __table_args__ = (
        UniqueConstraint(
            "workflow_definition_id", "code", name="uq_workflow_statuses_definition_code"
        ),
    )

    workflow_definition_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("workflow_definitions.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    code: Mapped[str] = mapped_column(String(50), nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    is_initial: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    is_terminal: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    sequence: Mapped[int] = mapped_column(Integer, default=0, nullable=False)


class WorkflowTransitionModel(BaseModel):
    """A permitted move between two states, triggered by an action code."""

    __tablename__ = "workflow_transitions"
    __table_args__ = (
        UniqueConstraint(
            "workflow_definition_id",
            "from_status_id",
            "action_code",
            name="uq_workflow_transitions_from_action",
        ),
    )

    workflow_definition_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("workflow_definitions.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    from_status_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("workflow_statuses.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    to_status_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("workflow_statuses.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    action_code: Mapped[str] = mapped_column(String(50), nullable=False, index=True)
    # Approval-chain semantics of this move; see WorkflowActionType.
    action_type: Mapped[str] = mapped_column(
        String(20), default="CUSTOM", nullable=False
    )
    guard_expression: Mapped[str | None] = mapped_column(Text, nullable=True)
    requires_comment: Mapped[bool] = mapped_column(
        Boolean, default=False, nullable=False
    )
    auto_execute: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    priority: Mapped[int] = mapped_column(Integer, default=0, nullable=False)


class WorkflowInstanceModel(BaseModel):
    """A running (or finished) execution of a definition against one record."""

    __tablename__ = "workflow_instances"

    __table_args__ = (
        # "Which workflow is this record in?" is the hot lookup for every business
        # screen that shows a status badge, so the pair gets a composite index on
        # top of the single-column ones.
        #
        # Declared here as well as in migration a7b8c9d0e1f2 because `alembic check`
        # compares the models against migration history: with the index only in the
        # migration, autogenerate saw it as an index to drop and CI failed on every
        # commit.
        Index("ix_workflow_instances_entity", "entity_type", "entity_id"),
    )

    workflow_definition_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("workflow_definitions.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    entity_type: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    entity_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), nullable=False, index=True
    )
    current_status_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("workflow_statuses.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    initiated_by: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    priority: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    due_date: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    started_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(UTC),
    )
    completed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True, index=True
    )
    extra_data: Mapped[dict[str, Any]] = mapped_column(
        JSONB, default=dict, nullable=False
    )
    # Approval level currently open; 0 when no chain is running.
    approval_level: Mapped[int] = mapped_column(Integer, default=0, nullable=False)


class WorkflowHistoryModel(Base):
    """
    Append-only trail of executed transitions.

    Inherits `Base` rather than `BaseModel`: nothing ever updates a history row,
    so `modified_by` / `modified_date` would be permanently equal to the created
    pair. `created_at` is named for the event, not for the row.
    """

    __tablename__ = "workflow_history"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4, nullable=False
    )
    instance_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("workflow_instances.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    from_status_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), nullable=True
    )
    to_status_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    action_code: Mapped[str] = mapped_column(String(50), nullable=False, index=True)
    actor_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    actor_username: Mapped[str] = mapped_column(
        String(255), default="", nullable=False
    )
    comments: Mapped[str] = mapped_column(Text, default="", nullable=False)
    extra_data: Mapped[dict[str, Any]] = mapped_column(
        JSONB, default=dict, nullable=False
    )
    # IPv6 in its longest textual form is 45 characters.
    ip_address: Mapped[str] = mapped_column(String(45), default="", nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(UTC),
        index=True,
    )
