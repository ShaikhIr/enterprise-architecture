"""
SQLAlchemy declarative base with audit mixin.
All ORM models inherit from this to get automatic audit field population.
"""

import uuid
from datetime import UTC, datetime

from sqlalchemy import DateTime, String
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    """SQLAlchemy declarative base class."""

    pass


class AuditMixin:
    """
    Mixin providing audit columns for all database models.

    Fields are auto-populated:
    - created_date: Set on INSERT (UTC)
    - modified_date: Set on INSERT and UPDATE (UTC)

    Note: `id` is annotated `Mapped[uuid.UUID]` because the column is declared
    with `as_uuid=True`, so SQLAlchemy returns `uuid.UUID` instances, not str.
    """

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
        nullable=False,
    )
    created_by: Mapped[str] = mapped_column(
        String(255), nullable=False, default="system"
    )
    created_date: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(UTC),
    )
    modified_by: Mapped[str] = mapped_column(
        String(255), nullable=False, default="system"
    )
    modified_date: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(UTC),
        onupdate=lambda: datetime.now(UTC),
    )


class BaseModel(AuditMixin, Base):
    """
    Abstract base model combining DeclarativeBase with audit fields.
    All concrete models should inherit from this.
    """

    __abstract__ = True
