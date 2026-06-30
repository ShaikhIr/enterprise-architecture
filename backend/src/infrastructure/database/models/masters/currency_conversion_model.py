"""Currency Conversion Rate Master ORM model."""

from datetime import datetime, timezone
from decimal import Decimal

from sqlalchemy import Boolean, DateTime, Integer, Numeric, String
from sqlalchemy.orm import Mapped, mapped_column

from src.infrastructure.database.models.base_model import BaseModel


class CurrencyConversionRateModel(BaseModel):
    """Currency Conversion Rate master data."""

    __tablename__ = "currency_conversion_rate_master"

    exrt: Mapped[str | None] = mapped_column(String(50), nullable=True)
    from_currency: Mapped[str] = mapped_column(String(10), nullable=False, index=True)
    to_currency: Mapped[str] = mapped_column(String(10), nullable=False, index=True)
    valid_from: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    exchange_rate: Mapped[Decimal | None] = mapped_column(
        Numeric(12, 6), nullable=True
    )
    ratio_from: Mapped[int | None] = mapped_column(Integer, nullable=True)
    ratio_to: Mapped[int | None] = mapped_column(Integer, nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
