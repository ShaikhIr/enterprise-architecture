"""
Invoice Header and Invoice Line domain entities.

An Invoice is a two-level aggregate: an Invoice Header owns one or more Invoice
Lines. The header captures billing totals, the vendor/customer relationship, and
payment-clearing lifecycle fields, while each line references a billable Product
Detail.
"""

from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal
from uuid import UUID

from src.domain.entities.base_entity import BaseEntity
from src.domain.enums.masters import InvoiceStatus


@dataclass
class InvoiceLineEntity(BaseEntity):
    """
    Invoice Line entity (a single billed product row on an invoice).

    Business Rules:
    - Must belong to an existing Invoice Header (``invoice_header_id``).
    - Must reference an existing Product Detail (``product_detail_id``).
    - Quantity and amounts, when supplied, are non-negative (validated at the
      service level).
    """

    invoice_header_id: UUID | None = field(default=None)
    product_detail_id: UUID | None = field(default=None)
    quantity: Decimal | None = field(default=None)
    line_amount: Decimal | None = field(default=None)
    vat_gst_amount: Decimal | None = field(default=None)


@dataclass
class InvoiceHeaderEntity(BaseEntity):
    """
    Invoice Header aggregate root.

    Business Rules:
    - Invoice Number must be unique across invoice headers (enforced at the
      repository/DB level).
    - Must reference an existing Vendor and Customer.
    - ``bill_amount_excl_gst`` is required; ``amount_deducted`` and ``tds_value``
      default to 0.
    - New invoices default to ``Open`` status.
    - Deleting a header cascades to its lines (DB ``ON DELETE CASCADE``).
    """

    invoice_number: str = field(default="")
    invoice_date: date | None = field(default=None)
    vendor_id: UUID | None = field(default=None)
    customer_id: UUID | None = field(default=None)
    bill_amount_excl_gst: Decimal = field(default=Decimal("0"))
    bill_amount_incl_tax: Decimal | None = field(default=None)
    amount_deducted: Decimal = field(default=Decimal("0"))
    tds_value: Decimal = field(default=Decimal("0"))
    due_date: date | None = field(default=None)
    payment_clearing_date: date | None = field(default=None)
    sap_clearing_document_no: str | None = field(default=None)
    invoice_status: InvoiceStatus = field(default=InvoiceStatus.Open)
    lines: list[InvoiceLineEntity] = field(default_factory=list)
