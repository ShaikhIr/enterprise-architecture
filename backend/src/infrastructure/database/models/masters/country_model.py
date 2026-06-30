"""Country Master ORM model — lookup table for freight masters."""

from sqlalchemy import Boolean, String
from sqlalchemy.orm import Mapped, mapped_column

from src.infrastructure.database.models.base_model import BaseModel


class CountryMasterModel(BaseModel):
    """Country master data used by freight and other modules."""

    __tablename__ = "country_master"

    country_name: Mapped[str] = mapped_column(
        String(200), nullable=False, index=True
    )
    country_code: Mapped[str] = mapped_column(
        String(10), unique=True, nullable=False, index=True
    )
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
