"""Vehicle Type Master ORM model."""

from sqlalchemy import Boolean, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from src.infrastructure.database.models.base_model import BaseModel


class VehicleTypeMasterModel(BaseModel):
    """Vehicle Type Master — pallet/box count to vehicle type mapping."""

    __tablename__ = "vehicle_type_master"

    from_no_of_pallet_or_box: Mapped[int] = mapped_column(Integer, nullable=False)
    to_no_of_pallet_or_box: Mapped[int] = mapped_column(Integer, nullable=False)
    vehicle_type: Mapped[str] = mapped_column(
        String(100), nullable=False, index=True
    )
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
