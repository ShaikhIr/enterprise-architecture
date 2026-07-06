"""
SQLAlchemy ORM model for the Customer master.
Maps the ``CustomerEntity`` domain entity to the 'customers' database table.
"""

from sqlalchemy import String, Text
from sqlalchemy.orm import Mapped, mapped_column

from src.domain.enums.masters import CustomerStatus
from src.infrastructure.database.models.base_model import BaseModel


class CustomerModel(BaseModel):
    """Customer master database table mapping."""

    __tablename__ = "customers"

    customer_code: Mapped[str] = mapped_column(
        String(50), nullable=False, unique=True
    )
    customer_name: Mapped[str] = mapped_column(String(255), nullable=False)
    address: Mapped[str | None] = mapped_column(Text, nullable=True)
    gstn_number: Mapped[str | None] = mapped_column(String(15), nullable=True)
    contact_person: Mapped[str | None] = mapped_column(String(100), nullable=True)
    contact_number: Mapped[str | None] = mapped_column(String(20), nullable=True)
    contact_email: Mapped[str | None] = mapped_column(String(255), nullable=True)
    status: Mapped[str] = mapped_column(
        String(20), nullable=False, default=CustomerStatus.Active.value
    )
