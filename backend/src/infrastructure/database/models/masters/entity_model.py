"""
SQLAlchemy ORM model for the Entity (legal company) master.
Maps the ``EntityEntity`` domain entity to the 'entities' database table.
"""

from sqlalchemy import Boolean, Index, String, func
from sqlalchemy.orm import Mapped, mapped_column

from src.infrastructure.database.models.base_model import BaseModel


class EntityModel(BaseModel):
    """Entity master database table mapping."""

    __tablename__ = "entities"

    entity_name: Mapped[str] = mapped_column(String(255), nullable=False)
    short_code: Mapped[str | None] = mapped_column(String(50), nullable=True)
    company_code: Mapped[str | None] = mapped_column(String(50), nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    __table_args__ = (
        # Trimmed, case-insensitive uniqueness on entity_name.
        Index(
            "uq_entities_entity_name_ci",
            func.lower(func.trim(entity_name)),
            unique=True,
        ),
        # Trimmed, case-insensitive uniqueness on company_code (nullable values
        # are excluded from the uniqueness constraint by PostgreSQL).
        Index(
            "uq_entities_company_code_ci",
            func.lower(func.trim(company_code)),
            unique=True,
        ),
    )
