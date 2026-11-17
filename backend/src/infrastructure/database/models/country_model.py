"""
SQLAlchemy ORM model for the Country master.
"""

from sqlalchemy import Boolean, String
from sqlalchemy.orm import Mapped, mapped_column

from src.infrastructure.database.models.base_model import BaseModel


class CountryModel(BaseModel):
    """Country database table."""

    __tablename__ = "countries"

    code: Mapped[str] = mapped_column(
        String(10), unique=True, nullable=False, index=True
    )
    name: Mapped[str] = mapped_column(
        String(255), unique=True, nullable=False, index=True
    )
    iso3_code: Mapped[str | None] = mapped_column(String(10), nullable=True)
    dial_code: Mapped[str | None] = mapped_column(String(10), nullable=True)
    currency_code: Mapped[str | None] = mapped_column(String(10), nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
