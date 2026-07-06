"""
SQLAlchemy ORM models for the Invoice Header and Invoice Line entities.

Maps the invoice aggregate to the ``invoice_headers`` and ``invoice_lines``
tables. An Invoice Line references its parent header via ``invoice_header_id``
with ``ON DELETE CASCADE`` so removing a header also removes its lines. The
header references ``vendors.id`` and ``customers.id``; each line references
``product_details.id``.
"""

from datetime import date
from decimal import Decimal

from sqlalchemy import Date, ForeignKey, Numeric, String
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.domain.enums.masters import InvoiceStatus
from src.infrastructure.database.models.base_model import BaseModel


class InvoiceHeaderModel(BaseModel):
    """Invoice Header database table mapping."""

    __tablename__ = "invoice_headers"

    invoice_number: Mapped[str] = mapped_column(
        String(50), nullable=False, unique=True, index=True
    )
    invoice_date: Mapped[date] = mapped_column(Date, nullable=False)
    vendor_id: Mapped[str] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("vendors.id"),
        nullable=False,
        index=True,
    )
    customer_id: Mapped[str | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("customers.id"),
        nullable=True,
        index=True,
    )
    bill_amount_excl_gst: Mapped[Decimal] = mapped_column(
        Numeric(14, 2), nullable=False
    )
    bill_amount_incl_tax: Mapped[Decimal | None] = mapped_column(
        Numeric(14, 2), nullable=True
    )
    amount_deducted: Mapped[Decimal] = mapped_column(
        Numeric(14, 2), nullable=False, default=Decimal("0")
    )
    tds_value: Mapped[Decimal] = mapped_column(
        Numeric(14, 2), nullable=False, default=Decimal("0")
    )
    due_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    payment_clearing_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    sap_clearing_document_no: Mapped[str | None] = mapped_column(
        String(50), nullable=True
    )
    invoice_status: Mapped[str] = mapped_column(
        String(20), nullable=False, default=InvoiceStatus.Open.value
    )

    lines: Mapped[list["InvoiceLineModel"]] = relationship(
        "InvoiceLineModel",
        back_populates="header",
        cascade="all, delete-orphan",
        passive_deletes=True,
        lazy="selectin",
    )


class InvoiceLineModel(BaseModel):
    """Invoice Line database table mapping."""

    __tablename__ = "invoice_lines"

    invoice_header_id: Mapped[str] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("invoice_headers.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    product_detail_id: Mapped[str] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("product_master.id"),
        nullable=False,
        index=True,
    )
    quantity: Mapped[Decimal | None] = mapped_column(Numeric(14, 3), nullable=True)
    line_amount: Mapped[Decimal | None] = mapped_column(Numeric(14, 2), nullable=True)
    vat_gst_amount: Mapped[Decimal | None] = mapped_column(
        Numeric(14, 2), nullable=True
    )

    header: Mapped["InvoiceHeaderModel"] = relationship(
        "InvoiceHeaderModel",
        back_populates="lines",
    )
