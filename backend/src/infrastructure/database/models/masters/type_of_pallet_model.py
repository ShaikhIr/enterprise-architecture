"""Type of Pallet Master ORM model."""

from sqlalchemy import Boolean, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from src.infrastructure.database.models.base_model import BaseModel


class TypeOfPalletMasterModel(BaseModel):
    """Type of Pallet master data."""

    __tablename__ = "type_of_pallet_master"

    name: Mapped[str] = mapped_column(
        String(100), unique=True, nullable=False, index=True
    )
    length: Mapped[int | None] = mapped_column(Integer, nullable=True)
    width: Mapped[int | None] = mapped_column(Integer, nullable=True)
    height: Mapped[int | None] = mapped_column(Integer, nullable=True)
    gross_weight_per_pack_type: Mapped[int | None] = mapped_column(Integer, nullable=True)
    volumetric_weight: Mapped[int | None] = mapped_column(Integer, nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
