"""
SQLAlchemy ORM model for the Country Master entity.
"""

from sqlalchemy import Boolean, ForeignKey, String
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.infrastructure.database.models.base_model import BaseModel


class CountryModel(BaseModel):
    """Country master data table."""

    __tablename__ = "country_master"

    country_code: Mapped[str] = mapped_column(
        String(10), nullable=False, index=True
    )
    country_name: Mapped[str] = mapped_column(
        String(100), unique=True, nullable=False, index=True
    )
    region_id: Mapped[str | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("region_master.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    # Relationship to region
    region = relationship("RegionModel", lazy="selectin")
