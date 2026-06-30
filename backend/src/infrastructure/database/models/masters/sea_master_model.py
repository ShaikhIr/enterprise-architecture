"""Sea Master ORM models."""

from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, Numeric, String
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.infrastructure.database.models.base_model import BaseModel


class SeaMasterModel(BaseModel):
    """Sea Master — freight with country + product type + currency."""

    __tablename__ = "sea_master"

    to_country_id: Mapped[str] = mapped_column(
        UUID(as_uuid=True), ForeignKey("country_master.id"), nullable=False
    )
    product_type: Mapped[str | None] = mapped_column(String(100), nullable=True)
    slab_name: Mapped[str | None] = mapped_column(String(100), nullable=True)
    currency: Mapped[str | None] = mapped_column(String(10), nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    to_country = relationship(
        "CountryMasterModel", foreign_keys=[to_country_id], lazy="selectin"
    )
    rates = relationship(
        "SeaMasterRateModel",
        back_populates="sea_master",
        cascade="all, delete-orphan",
        lazy="selectin",
    )


class SeaMasterRateModel(BaseModel):
    """Rate entries linked to a sea master record."""

    __tablename__ = "sea_master_rate"

    sea_master_id: Mapped[str] = mapped_column(
        UUID(as_uuid=True), ForeignKey("sea_master.id"), nullable=False
    )
    rate: Mapped[float] = mapped_column(Numeric(12, 4), nullable=False)
    valid_from: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    valid_till: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    sea_master = relationship(
        "SeaMasterModel", back_populates="rates"
    )
