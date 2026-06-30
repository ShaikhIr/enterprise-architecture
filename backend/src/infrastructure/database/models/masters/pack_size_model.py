"""Pack Style Master ORM model."""

from sqlalchemy import Boolean, String
from sqlalchemy.orm import Mapped, mapped_column

from src.infrastructure.database.models.base_model import BaseModel


class PackStyleMasterModel(BaseModel):
    """Pack Style master data."""

    __tablename__ = "pack_style_master"

    pack_style: Mapped[str] = mapped_column(
        String(100), unique=True, nullable=False, index=True
    )
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
