"""
SQLAlchemy ORM model for the City Master entity.
"""

from sqlalchemy import Boolean, ForeignKey, String
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.infrastructure.database.models.base_model import BaseModel


class CityModel(BaseModel):
    """City master data table."""

    __tablename__ = "city_master"

    city_name: Mapped[str] = mapped_column(
        String(100), nullable=False, index=True
    )
    state_id: Mapped[str] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("state_master.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    # Relationship to state
    state = relationship("StateModel", lazy="selectin")
