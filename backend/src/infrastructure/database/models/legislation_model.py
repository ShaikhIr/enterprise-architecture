"""
SQLAlchemy ORM model for the Legislation master.
"""

from datetime import date

from sqlalchemy import BigInteger, Boolean, Date, ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from src.infrastructure.database.models.base_model import BaseModel


class LegislationModel(BaseModel):
    """Legislation / act / statute database table."""

    __tablename__ = "legislations"

    code: Mapped[str] = mapped_column(
        String(50), unique=True, nullable=False, index=True
    )
    name: Mapped[str] = mapped_column(String(500), nullable=False, index=True)
    description: Mapped[str] = mapped_column(Text, default="", nullable=False)
    category_of_law_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("categories_of_law.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    # Nullable to support central / federal legislations (country level only).
    state_id: Mapped[int | None] = mapped_column(
        BigInteger,
        ForeignKey("states.id", ondelete="RESTRICT"),
        nullable=True,
        index=True,
    )
    country_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("countries.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    legislation_number: Mapped[str | None] = mapped_column(String(100), nullable=True)
    effective_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
