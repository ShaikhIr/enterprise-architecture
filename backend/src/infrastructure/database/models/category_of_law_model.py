"""
SQLAlchemy ORM model for the Category of Law master.
"""

import uuid

from sqlalchemy import Boolean, ForeignKey, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from src.infrastructure.database.models.base_model import BaseModel


class CategoryOfLawModel(BaseModel):
    """Category of law database table (e.g. Labour Law, Environmental Law)."""

    __tablename__ = "categories_of_law"
    __table_args__ = (
        UniqueConstraint("state_id", "name", name="uq_categories_of_law_state_name"),
    )

    code: Mapped[str] = mapped_column(
        String(50), unique=True, nullable=False, index=True
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    description: Mapped[str] = mapped_column(Text, default="", nullable=False)
    # Nullable so a category can apply country-wide instead of per state.
    state_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("states.id", ondelete="RESTRICT"),
        nullable=True,
        index=True,
    )
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
