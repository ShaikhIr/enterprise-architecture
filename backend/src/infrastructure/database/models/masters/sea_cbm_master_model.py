"""Sea CBM Master ORM model."""

from sqlalchemy import Boolean, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from src.infrastructure.database.models.base_model import BaseModel


class SeaCbmMasterModel(BaseModel):
    """Sea CBM Master — cubic metre slab definitions."""

    __tablename__ = "sea_cbm_master"

    slab_name: Mapped[str | None] = mapped_column(String(100), nullable=True)
    from_cbm: Mapped[int] = mapped_column(Integer, nullable=False)
    to_cbm: Mapped[int] = mapped_column(Integer, nullable=False)
    type: Mapped[str | None] = mapped_column(String(100), nullable=True)
    total_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
