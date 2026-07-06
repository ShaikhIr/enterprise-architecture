"""
SQLAlchemy ORM model for the Vendor entity.
Maps the Vendor domain entity to the 'vendors' database table.
"""

from sqlalchemy import ForeignKey, String, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from src.domain.enums.masters import VendorStatus
from src.infrastructure.database.models.base_model import BaseModel


class VendorModel(BaseModel):
    """Vendor database table mapping."""

    __tablename__ = "vendors"

    vendor_code: Mapped[str] = mapped_column(
        String(50), unique=True, nullable=False, index=True
    )
    vendor_name: Mapped[str] = mapped_column(String(255), nullable=False)
    vendor_email: Mapped[str] = mapped_column(
        String(255), unique=True, nullable=False, index=True
    )
    vendor_contact: Mapped[str | None] = mapped_column(String(20), nullable=True)
    vendor_address: Mapped[str | None] = mapped_column(Text, nullable=True)
    city: Mapped[str | None] = mapped_column(String(100), nullable=True)
    gstn_number: Mapped[str | None] = mapped_column(String(15), nullable=True)
    pan_number: Mapped[str | None] = mapped_column(String(10), nullable=True)
    bank_account_no: Mapped[str | None] = mapped_column(String(30), nullable=True)
    bank_ifsc: Mapped[str | None] = mapped_column(String(11), nullable=True)
    bank_name: Mapped[str | None] = mapped_column(String(100), nullable=True)
    portal_user_id: Mapped[str | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id"),
        nullable=True,
        index=True,
    )
    status: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        default=VendorStatus.Active.value,
    )
