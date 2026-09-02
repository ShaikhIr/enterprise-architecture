"""
SQLAlchemy declarative base with audit mixin.
All ORM models inherit from this to get automatic audit field population.
"""

from datetime import UTC, datetime

from sqlalchemy import BigInteger, DateTime, String
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

    Note: `id` is a database-generated bigint (identity/sequence), assigned on
    INSERT. No client-side default — the row must be flushed before its id is
    known, which is why entities carry the sentinel 0 until persisted.
    """

    id: Mapped[int] = mapped_column(
        BigInteger,
        primary_key=True,
        autoincrement=True,
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
