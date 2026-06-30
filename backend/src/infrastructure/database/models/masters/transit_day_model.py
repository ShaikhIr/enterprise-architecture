"""Transit Day Master ORM model."""

from sqlalchemy import Boolean, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from src.infrastructure.database.models.base_model import BaseModel


class TransitDayMasterModel(BaseModel):
    """Transit Day master data."""

    __tablename__ = "transit_day_master"

    country_name: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    country_code: Mapped[str | None] = mapped_column(String(10), nullable=True)
    customer_clearance: Mapped[int | None] = mapped_column(Integer, nullable=True)
    transit_days_for_air: Mapped[int | None] = mapped_column(Integer, nullable=True)
    container_load_for_sea: Mapped[int | None] = mapped_column(Integer, nullable=True)
    test_days: Mapped[int | None] = mapped_column(Integer, nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
