"""Air Master (Freight Slab) ORM models."""

from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, Numeric, String
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.infrastructure.database.models.base_model import BaseModel


class AirMasterModel(BaseModel):
    """Air Master — freight slab with country + product type."""

    __tablename__ = "air_master"

    to_country_id: Mapped[str] = mapped_column(
        UUID(as_uuid=True), ForeignKey("country_master.id"), nullable=False
    )
    product_type: Mapped[str | None] = mapped_column(String(100), nullable=True)
    min_slab: Mapped[int] = mapped_column(Integer, nullable=False)
    max_slab: Mapped[int] = mapped_column(Integer, nullable=False)
    slab_name: Mapped[str | None] = mapped_column(String(50), nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    to_country = relationship(
        "CountryMasterModel", foreign_keys=[to_country_id], lazy="selectin"
    )
    rates = relationship(
        "AirMasterRateModel",
        back_populates="air_master",
        cascade="all, delete-orphan",
        lazy="selectin",
    )


class AirMasterRateModel(BaseModel):
    """Rate entries linked to an air master record."""

    __tablename__ = "air_master_rate"

    air_master_id: Mapped[str] = mapped_column(
        UUID(as_uuid=True), ForeignKey("air_master.id"), nullable=False
    )
    rate: Mapped[float] = mapped_column(Numeric(12, 4), nullable=False)
    valid_from: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    valid_till: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    air_master = relationship(
        "AirMasterModel", back_populates="rates"
    )
