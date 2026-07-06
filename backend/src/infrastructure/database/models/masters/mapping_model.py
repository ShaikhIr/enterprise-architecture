"""
SQLAlchemy ORM model for the Vendor-Customer Mapping entity.

Maps the Mapping domain entity to the ``vendor_customer_mappings`` table. This
exact table name and the ``customer_id``/``status`` columns are referenced by
the Customer repository's delete-guard, so they must not change without updating
that guard.
"""

from datetime import date

from sqlalchemy import Date, ForeignKey, Index, String
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from src.domain.enums.masters import MappingStatus
from src.infrastructure.database.models.base_model import BaseModel


class MappingModel(BaseModel):
    """Vendor-Customer Mapping database table mapping."""

    __tablename__ = "vendor_customer_mappings"

    vendor_id: Mapped[str] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("vendors.id"),
        nullable=False,
    )
    customer_id: Mapped[str] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("customers.id"),
        nullable=False,
    )
    validity_from: Mapped[date] = mapped_column(Date, nullable=False)
    validity_to: Mapped[date] = mapped_column(Date, nullable=False)
    status: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        default=MappingStatus.Active.value,
    )

    __table_args__ = (
        Index(
            "ix_vendor_customer_mappings_vendor_customer_status",
            "vendor_id",
            "customer_id",
            "status",
        ),
    )
