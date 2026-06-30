"""
SQLAlchemy ORM model for the State Master entity.
"""

from sqlalchemy import Boolean, ForeignKey, String
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.infrastructure.database.models.base_model import BaseModel


class StateModel(BaseModel):
    """State master data table."""

    __tablename__ = "state_master"

    country_id: Mapped[str] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("country_master.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    language_key: Mapped[str] = mapped_column(String(10), nullable=False)
    state_name: Mapped[str] = mapped_column(
        String(100), unique=True, nullable=False, index=True
    )
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    # Relationship to country
    country = relationship("CountryModel", lazy="selectin")
