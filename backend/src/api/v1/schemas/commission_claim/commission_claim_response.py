"""
Commission Claim response schemas (Pydantic v2).

Maps the ClaimHeader / ClaimLine domain aggregate to the API representation.
Uses ``ConfigDict(from_attributes=True)`` so responses can be built directly
from domain objects / dicts.

Requirements: 19.2, 20.2
"""

from datetime import date, datetime
from decimal import Decimal
from uuid import UUID

from pydantic import BaseModel, ConfigDict


class ClaimLineResponse(BaseModel):
    """Full representation of a single invoice line within a claim."""

    id: UUID
    claim_header_id: UUID
    invoice_header_id: UUID
    invoice_number: str | None = None
    product_master_id: UUID
    customer_id: UUID
    bill_amount_excl_gst: Decimal
    amount_deducted: Decimal
    tds_value: Decimal
    ld_charges: Decimal
    retention_amount: Decimal
    net_amount: Decimal
    commission_payable_base: Decimal
    due_date: date
    payment_clearing_date: date
    delay_days: int
    applicable_commission_percent: Decimal
    commission_amount: Decimal
    gst_on_commission: Decimal
    final_line_claim_amount: Decimal
    pod_document_id: UUID | None
    remarks: str
    created_by: str
    created_date: datetime

    model_config = ConfigDict(from_attributes=True)


class ClaimHeaderResponse(BaseModel):
    """Full representation of a commission claim header."""

    id: UUID
    vendor_id: UUID
    entity_id: UUID | None = None
    claim_number: str | None
    claim_date: date
    status: str
    workflow_status_name: str | None = None  # e.g. "L1 Approval Pending"
    workflow_instance_id: UUID | None
    total_claim_amount: Decimal
    total_commission_amount: Decimal
    total_gst_amount: Decimal
    total_tds_amount: Decimal
    total_ld_amount: Decimal
    total_retention_amount: Decimal
    gstn_verification_status: str
    gst_invoice_number: str | None
    gst_invoice_upload_date: date | None
    sap_p2p_booking_reference: str | None
    created_by: str
    created_date: datetime
    modified_date: datetime

    model_config = ConfigDict(from_attributes=True)


class ClaimDetailResponse(BaseModel):
    """Full claim detail: header + lines + workflow context."""

    header: ClaimHeaderResponse
    lines: list[ClaimLineResponse]
    workflow_status: dict | None = None
    available_actions: list = []


class ClaimListResponse(BaseModel):
    """Paginated list of claim headers."""

    items: list[ClaimHeaderResponse]
    total: int
    skip: int
    limit: int


class ClaimAuditEntryResponse(BaseModel):
    """Single audit log entry for a commission claim action."""

    id: UUID
    claim_header_id: UUID
    action: str
    actor_username: str
    actor_user_id: UUID
    timestamp_utc: datetime
    from_status: str | None
    to_status: str | None
    workflow_step_name: str | None
    remarks: str | None
    field_changes: dict | None

    model_config = ConfigDict(from_attributes=True)


class ApprovalQueueItemResponse(BaseModel):
    """Single row in the approver's pending-claims queue."""

    claim_number: str | None
    vendor_id: UUID
    claim_date: date
    total_claim_amount: Decimal
    status: str
    workflow_step_name: str | None = None
    submitted_date: datetime | None = None
    id: UUID

    model_config = ConfigDict(from_attributes=True)


class MISItemResponse(BaseModel):
    """Single row in the MIS pending or history view."""

    id: UUID
    claim_number: str | None
    vendor_id: UUID
    claim_date: date
    status: str
    status_label: str  # e.g. "Pending - L1 Verification" or "Closed"
    total_claim_amount: Decimal
    total_commission_amount: Decimal
    created_date: datetime

    model_config = ConfigDict(from_attributes=True)
