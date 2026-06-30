"""Local Master ORM models."""

from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, Numeric, String
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.infrastructure.database.models.base_model import BaseModel


class LocalMasterModel(BaseModel):
    """Local Master — freight local with cities, product type, vehicle."""

    __tablename__ = "local_master"

    from_city_id: Mapped[str] = mapped_column(
        UUID(as_uuid=True), ForeignKey("city_master.id"), nullable=False
    )
    to_city_id: Mapped[str] = mapped_column(
        UUID(as_uuid=True), ForeignKey("city_master.id"), nullable=False
    )
    product_type: Mapped[str | None] = mapped_column(String(100), nullable=True)
    vehicle_type_id: Mapped[str | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("vehicle_type_master.id"), nullable=True
    )
    min_slab: Mapped[str | None] = mapped_column(String(50), nullable=True)
    max_slab: Mapped[str | None] = mapped_column(String(50), nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    from_city = relationship(
        "CityMasterModel", foreign_keys=[from_city_id], lazy="selectin"
    )
    to_city = relationship(
        "CityMasterModel", foreign_keys=[to_city_id], lazy="selectin"
    )
    vehicle_type_ref = relationship(
        "VehicleTypeMasterModel", foreign_keys=[vehicle_type_id], lazy="selectin"
    )
    rates = relationship(
        "LocalMasterRateModel",
        back_populates="local_master",
        cascade="all, delete-orphan",
        lazy="selectin",
    )


class LocalMasterRateModel(BaseModel):
    """Rate entries linked to a local master record."""

    __tablename__ = "local_master_rate"

    local_master_id: Mapped[str] = mapped_column(
        UUID(as_uuid=True), ForeignKey("local_master.id"), nullable=False
    )
    rate: Mapped[float] = mapped_column(Numeric(12, 4), nullable=False)
    valid_from: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    valid_till: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    local_master = relationship(
        "LocalMasterModel", back_populates="rates"
    )
