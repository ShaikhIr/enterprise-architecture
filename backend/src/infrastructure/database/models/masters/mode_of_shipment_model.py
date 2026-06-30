"""Mode of Shipment Master ORM model."""

from sqlalchemy import Boolean, String
from sqlalchemy.orm import Mapped, mapped_column

from src.infrastructure.database.models.base_model import BaseModel


class ModeOfShipmentMasterModel(BaseModel):
    """Mode of Shipment master data."""

    __tablename__ = "mode_of_shipment_master"

    mode_name: Mapped[str] = mapped_column(
        String(100), unique=True, nullable=False, index=True
    )
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
