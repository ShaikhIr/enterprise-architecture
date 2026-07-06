"""
Invoice Master request schemas (Pydantic v2).

These thin DTOs carry the raw request payload to ``InvoiceService``. The
authoritative business validation (required fields, length/format limits,
Invoice Number uniqueness, Vendor/Customer/Product-Detail existence, numeric
bounds, status lifecycle, due-date resolution) lives in the service so all
business rules raise ``MasterValidationError`` / ``MasterConflictError`` /
``MasterNotFoundError`` (mapped to HTTP 422/409/404 by the controller).

An Invoice is a two-level aggregate: a header carries the billing totals and
references, while ``lines`` carries one or more billed Product-Detail rows that
are created atomically with the header.

Partial-update semantics: ``UpdateInvoiceRequest`` relies on Pydantic's
``model_fields_set`` so the controller can distinguish "field omitted" (leave
unchanged) from "field explicitly set to null" (clear the nullable value) when
building the service's ``UNSET``-aware ``InvoiceUpdateInput``.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class InvoiceLineRequest(BaseModel):
    """Payload for a single Invoice Line on a create request.

    ``quantity``, ``line_amount`` and ``vat_gst_amount`` are optional; when
    supplied they must be non-negative (validated by the service).
    """

    model_config = ConfigDict(extra="forbid")

    product_detail_id: UUID = Field(..., description="Referenced Product Detail")
    quantity: Decimal | None = Field(default=None)
    line_amount: Decimal | None = Field(default=None)
    vat_gst_amount: Decimal | None = Field(default=None)


class CreateInvoiceRequest(BaseModel):
    """Payload for creating an Invoice Header with its lines (Requirement 16)."""

    model_config = ConfigDict(extra="forbid")

    invoice_number: str = Field(..., description="Unique Invoice Number (≤ 50 chars)")
    invoice_date: date = Field(..., description="Invoice Date")
    vendor_id: UUID = Field(..., description="Referenced Vendor")
    customer_id: UUID = Field(..., description="Referenced Customer")
    bill_amount_excl_gst: Decimal = Field(..., description="Required bill amount excl. GST")
    lines: list[InvoiceLineRequest] = Field(
        default_factory=list, description="At least one invoice line is required"
    )
    bill_amount_incl_tax: Decimal | None = Field(default=None)
    amount_deducted: Decimal | None = Field(
        default=None, description="Defaults to 0 when omitted"
    )
    tds_value: Decimal | None = Field(
        default=None, description="Defaults to 0 when omitted"
    )
    due_date: date | None = Field(
        default=None,
        description=(
            "When omitted, computed from an applicable Agreement's Credit Days, "
            "else left unset"
        ),
    )


class UpdateInvoiceRequest(BaseModel):
    """Partial-update payload for an Invoice Header's own fields.

    Every field is optional. Only fields explicitly present in the request are
    applied; omitted fields are left unchanged (Req 16.7 partial-update
    semantics). Line membership is part of the create aggregate and is not
    updated here.
    """

    model_config = ConfigDict(extra="forbid")

    bill_amount_excl_gst: Decimal | None = Field(default=None)
    bill_amount_incl_tax: Decimal | None = Field(default=None)
    amount_deducted: Decimal | None = Field(default=None)
    tds_value: Decimal | None = Field(default=None)
    due_date: date | None = Field(default=None)


class SapPaymentRequest(BaseModel):
    """Payload for an SAP payment confirmation (Req 17.1).

    The target Invoice Header may be addressed by ``invoice_id`` or
    ``invoice_number`` (at least one must be supplied); an unknown reference is
    rejected with a not-found error by the service (Req 17.4).
    """

    model_config = ConfigDict(extra="forbid")

    payment_clearing_date: date = Field(..., description="Payment Clearing Date")
    sap_clearing_document_no: str = Field(
        ..., description="SAP Clearing Document No (≤ 50 chars)"
    )
    invoice_id: UUID | None = Field(default=None)
    invoice_number: str | None = Field(default=None)
