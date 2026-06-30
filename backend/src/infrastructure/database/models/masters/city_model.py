"""City Master ORM model — lookup table for local freight masters."""

from sqlalchemy import Boolean, ForeignKey, String
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.infrastructure.database.models.base_model import BaseModel


class CityMasterModel(BaseModel):
    """City master data used by local freight masters."""

    __tablename__ = "city_master"

    city_name: Mapped[str] = mapped_column(
        String(200), nullable=False, index=True
    )
    country_id: Mapped[str | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("country_master.id"), nullable=True
    )
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    country = relationship("CountryMasterModel", foreign_keys=[country_id], lazy="selectin")
