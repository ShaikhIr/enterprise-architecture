"""
SQLAlchemy ORM models for the approval matrix.

Rules and assignments are owned by their matrix and cascade on delete, which is
what lets the repository implement "update" as a wholesale replace of both child
collections. Approval tasks point at a workflow instance and cascade with it.
"""

import uuid
from datetime import datetime

from sqlalchemy import (
    Boolean,
    DateTime,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from src.infrastructure.database.models.base_model import BaseModel


class ApprovalMatrixModel(BaseModel):
    """Routing table for one entity type, selected by rule match then priority."""

    __tablename__ = "approval_matrices"

    code: Mapped[str] = mapped_column(
        String(100), unique=True, nullable=False, index=True
    )
    name: Mapped[str] = mapped_column(
        String(255), unique=True, nullable=False, index=True
    )
    entity_type: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    priority: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)


class ApprovalRuleModel(BaseModel):
    """One condition on a matrix, e.g. `amount GTE 100000`."""

    __tablename__ = "approval_rules"

    matrix_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("approval_matrices.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    # Dotted path into the entity payload, e.g. "claim.amount".
    field: Mapped[str] = mapped_column(String(100), nullable=False)
    operator: Mapped[str] = mapped_column(String(20), nullable=False)
    value: Mapped[str] = mapped_column(String(500), nullable=False)
    data_type: Mapped[str] = mapped_column(
        String(20), default="STRING", nullable=False
    )
    # Rules in the same group are ANDed; groups are ORed against each other.
    logical_group: Mapped[str] = mapped_column(
        String(50), default="default", nullable=False
    )


class ApprovalAssignmentModel(BaseModel):
    """One approval level on a matrix, resolved to a role or a specific user."""

    __tablename__ = "approval_assignments"

    matrix_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("approval_matrices.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    assignment_type: Mapped[str] = mapped_column(String(20), nullable=False)
    user_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=True,
        index=True,
    )
    role_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("roles.id", ondelete="CASCADE"),
        nullable=True,
        index=True,
    )
    level: Mapped[int] = mapped_column(Integer, default=1, nullable=False)


class ApprovalTaskModel(BaseModel):
    """A pending or completed approval action owned by one user."""

    __tablename__ = "approval_tasks"
    __table_args__ = (
        UniqueConstraint(
            "instance_id",
            "assignee_id",
            "level",
            name="uq_approval_tasks_instance_assignee_level",
        ),
    )

    instance_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("workflow_instances.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    matrix_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("approval_matrices.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    assignee_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    level: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    status: Mapped[str] = mapped_column(
        String(20), default="PENDING", nullable=False, index=True
    )
    action_taken: Mapped[str | None] = mapped_column(String(50), nullable=True)
    due_date: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True, index=True
    )
    comments: Mapped[str | None] = mapped_column(Text, nullable=True)
