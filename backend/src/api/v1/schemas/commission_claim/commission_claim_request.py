"""
Commission Claim request schemas (Pydantic v2).

Carries the raw request payloads for the Commission Claim Management API.
Business validation lives in ``CommissionClaimService``; these DTOs handle
type coercion and basic field constraints only.

Requirements: 19.2, 20.2
"""

from datetime import date
from decimal import Decimal
from uuid import UUID

from pydantic import BaseModel, Field


class ClaimCreateRequest(BaseModel):
    """Request body for creating a new commission claim (draft)."""

    vendor_id: UUID  # The vendor this claim belongs to
    entity_id: UUID | None = None  # Optional entity for workflow routing


class ClaimEntityUpdateRequest(BaseModel):
    """Request body for updating the entity assigned to a draft claim."""

    entity_id: UUID | None = None


class AddInvoiceLineRequest(BaseModel):
    """Request body for adding an invoice line to a claim."""

    invoice_id: UUID
    due_date_override: date | None = None
    ld_charges: Decimal = Decimal("0")
    retention_amount: Decimal = Decimal("0")
    remarks: str = ""


class LineUpdateRequest(BaseModel):
    """Partial update request for a claim line - all fields optional."""

    amount_deducted: Decimal | None = None
    tds_value: Decimal | None = None
    payment_clearing_date: date | None = None
    ld_charges: Decimal | None = None
    retention_amount: Decimal | None = None
    due_date: date | None = None
    remarks: str | None = None


class WorkflowActionRequest(BaseModel):
    """Request body for any workflow action (approve / refer-back / reject).

    Non-empty remarks are required by all workflow actions (Req 7.5).
    """

    remarks: str = Field(..., min_length=1, description="Non-empty remarks required")


class PaymentClearingDateRequest(BaseModel):
    """Request body for updating the payment clearing date on a claim line."""

    payment_clearing_date: date


class SAPBookingRequest(BaseModel):
    """Request body for recording an SAP P2P booking reference on a closed claim."""

    sap_p2p_booking_reference: str = Field(..., min_length=1)


class GSTInvoiceRequest(BaseModel):
    """Request body for uploading a GST invoice number after GSTN verification."""

    gst_invoice_number: str = Field(..., min_length=1)


class PODUploadRequest(BaseModel):
    """Request body for associating a POD document with a claim line."""

    document_id: UUID


class MISFilterParams(BaseModel):
    """Query filter parameters for MIS pending / history endpoints."""

    vendor_id: UUID | None = None
    claim_number: str | None = None
    start_date: date | None = None
    end_date: date | None = None
