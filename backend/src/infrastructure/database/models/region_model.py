"""
SQLAlchemy ORM model for the Region Master entity.
"""

from sqlalchemy import Boolean, String, DateTime
from sqlalchemy.orm import Mapped, mapped_column
from datetime import datetime, timezone

from src.infrastructure.database.models.base_model import BaseModel


class RegionModel(BaseModel):
    """Region master data table."""

    __tablename__ = "region_master"

    region_id: Mapped[str | None] = mapped_column(String(50), nullable=True)
    region_name: Mapped[str] = mapped_column(
        String(100), unique=True, nullable=False, index=True
    )
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
