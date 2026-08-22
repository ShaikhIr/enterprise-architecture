"""
SQLAlchemy ORM model for the Task Type master.
"""

from sqlalchemy import Boolean, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from src.infrastructure.database.models.base_model import BaseModel


class TaskTypeModel(BaseModel):
    """Task type database table."""

    __tablename__ = "task_types"

    code: Mapped[str] = mapped_column(
        String(50), unique=True, nullable=False, index=True
    )
    name: Mapped[str] = mapped_column(
        String(255), unique=True, nullable=False, index=True
    )
    description: Mapped[str] = mapped_column(Text, default="", nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
