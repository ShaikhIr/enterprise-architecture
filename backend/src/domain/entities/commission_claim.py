"""
Domain entities for Commission Claim Management.

This module defines:
- ClaimStatus enum and the allowed state-machine transition map (task 1.1)
- ClaimHeader and ClaimLine dataclasses (task 1.2)
"""

from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal
from enum import Enum
from uuid import UUID


class ClaimStatus(str, Enum):
    """Lifecycle states for a commission claim."""

    Draft = "Draft"
    Pending = "Pending"
    ReferredBack = "Referred Back"
    Rejected = "Rejected"
    Closed = "Closed"


# Allowed state-machine edges: (from_status, action) → to_status
# Only the six transitions listed in Requirement 11.1 are present.
CLAIM_TRANSITIONS: dict[tuple[ClaimStatus, str], ClaimStatus] = {
    (ClaimStatus.Draft,        "submit"):        ClaimStatus.Pending,
    (ClaimStatus.Pending,      "approve"):       ClaimStatus.Pending,      # intermediate approval
    (ClaimStatus.Pending,      "final_approve"): ClaimStatus.Closed,
    (ClaimStatus.Pending,      "refer_back"):    ClaimStatus.ReferredBack,
    (ClaimStatus.Pending,      "reject"):        ClaimStatus.Rejected,
    (ClaimStatus.ReferredBack, "submit"):        ClaimStatus.Pending,
}

# Terminal statuses — no further transitions are permitted (Requirements 11.3, 11.4)
TERMINAL_STATUSES: frozenset[ClaimStatus] = frozenset({
    ClaimStatus.Closed,
    ClaimStatus.Rejected,
})


@dataclass
class ClaimHeader:
    """
    Top-level aggregate for a commission claim.

    Owns one or more ClaimLines and tracks overall status, workflow linkage,
    persisted header totals, and post-closure fields.

    Requirements 1.1, 1.2, 1.3, 4.1
    """

    id: UUID
    vendor_id: UUID
    entity_id: UUID | None                # linked entity for workflow routing
    claim_number: str | None          # null until first submission (Req 1.2, 6.3)
    claim_date: date                  # UTC date of draft creation (Req 1.3)
    status: ClaimStatus
    workflow_instance_id: UUID | None

    # Header totals — recalculated on every line add/update/delete (Req 4.1)
    total_claim_amount: Decimal
    total_commission_amount: Decimal
    total_gst_amount: Decimal
    total_tds_amount: Decimal
    total_ld_amount: Decimal
    total_retention_amount: Decimal

    # Post-closure fields (Req 9.2, 9.3, 9.5)
    gstn_verification_status: str     # "Pending" | "Verified" | "Failed"
    gst_invoice_number: str | None
    gst_invoice_upload_date: date | None
    sap_p2p_booking_reference: str | None

    # Audit fields (populated by AuditMixin / service layer)
    created_by: str
    created_date: datetime
    modified_by: str
    modified_date: datetime


@dataclass
class ClaimLine:
    """
    Single invoice-level row within a ClaimHeader.

    Stores all raw inputs plus all 7 commission formula outputs.

    Requirements 1.1, 3.1–3.12, 4.1
    """

    id: UUID
    claim_header_id: UUID
    invoice_header_id: UUID
    product_master_id: UUID
    customer_id: UUID

    # Invoice-sourced input fields
    bill_amount_excl_gst: Decimal
    amount_deducted: Decimal
    tds_value: Decimal
    ld_charges: Decimal           # display-only, not used in formula (Req 3.12)
    retention_amount: Decimal     # display-only, not used in formula (Req 3.12)

    # 7-step formula outputs — all persisted for audit/display (Req 3.10)
    net_amount: Decimal                       # Step 1: max(0, bill − deducted − tds)
    commission_payable_base: Decimal          # Step 2: net + tds + deducted
    due_date: date                            # Invoice Date + credit_days (overridable)
    payment_clearing_date: date              # Step 3 input for delay_days
    delay_days: int                           # Step 3: (clearing_date − due_date).days
    applicable_commission_percent: Decimal    # Steps 4/5: slab-based rate
    commission_amount: Decimal                # Step 6: base × percent
    gst_on_commission: Decimal                # Step 7a: commission × 18%
    final_line_claim_amount: Decimal          # Step 7b: commission + gst

    # Non-formula display / document fields
    pod_document_id: UUID | None  # mandatory before submission (Req 5.1, 5.2)
    remarks: str

    # Audit fields
    created_by: str
    created_date: datetime
    modified_by: str
    modified_date: datetime
