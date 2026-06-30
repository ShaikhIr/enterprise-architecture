"""Fixed Charges Master ORM model."""

from decimal import Decimal

from sqlalchemy import Boolean, Numeric, String
from sqlalchemy.orm import Mapped, mapped_column

from src.infrastructure.database.models.base_model import BaseModel


class FixedChargesMasterModel(BaseModel):
    """Fixed Charges master data."""

    __tablename__ = "fixed_charges_master"

    mode_of_shipment: Mapped[str | None] = mapped_column(String(100), nullable=True)
    pallet_name: Mapped[str | None] = mapped_column(String(100), nullable=True)
    document_charges: Mapped[Decimal | None] = mapped_column(
        Numeric(12, 4), nullable=True
    )
    shrink_wrap_charges: Mapped[Decimal | None] = mapped_column(
        Numeric(12, 4), nullable=True
    )
    unloading_charges: Mapped[Decimal | None] = mapped_column(
        Numeric(12, 4), nullable=True
    )
    pallet_charges: Mapped[Decimal | None] = mapped_column(
        Numeric(12, 4), nullable=True
    )
    data_logger_charges: Mapped[Decimal | None] = mapped_column(
        Numeric(12, 4), nullable=True
    )
    blanket_charges: Mapped[Decimal | None] = mapped_column(
        Numeric(12, 4), nullable=True
    )
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
