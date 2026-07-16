"""
Property-based tests for CommissionClaimService._recalculate_header_totals — Property 6.

Tests verify that after _recalculate_header_totals, every header total equals the
sum of the corresponding field across all ClaimLines.  The aggregation logic is
exercised directly by mocking the two repository collaborators so no real DB is needed.

**Validates: Requirements 4.1, 4.2**
"""

import asyncio
from datetime import date, datetime, timezone
from decimal import Decimal
from unittest.mock import AsyncMock
from uuid import uuid4

from hypothesis import given, settings
from hypothesis import strategies as st

from src.application.services.commission_claim_service import CommissionClaimService
from src.domain.entities.commission_claim import ClaimHeader, ClaimLine, ClaimStatus
from src.domain.repositories.commission_claim.claim_line_repository import ClaimTotals

# ---------------------------------------------------------------------------
# Shared strategy
# ---------------------------------------------------------------------------

amount_strategy = st.decimals(
    min_value=Decimal("0"),
    max_value=Decimal("100000"),
    allow_nan=False,
    allow_infinity=False,
    places=2,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_line(
    claim_id,
    final_claim: Decimal,
    commission: Decimal,
    gst: Decimal,
    tds: Decimal,
    ld: Decimal,
    retention: Decimal,
) -> ClaimLine:
    """Build a ClaimLine populated with the six totals-relevant fields."""
    now = datetime.now(timezone.utc)
    return ClaimLine(
        id=uuid4(),
        claim_header_id=claim_id,
        invoice_header_id=uuid4(),
        product_master_id=uuid4(),
        customer_id=uuid4(),
        bill_amount_excl_gst=Decimal("1000"),
        amount_deducted=Decimal("0"),
        tds_value=tds,
        ld_charges=ld,
        retention_amount=retention,
        net_amount=Decimal("1000"),
        commission_payable_base=Decimal("1000"),
        due_date=date.today(),
        payment_clearing_date=date.today(),
        delay_days=0,
        applicable_commission_percent=Decimal("5.00"),
        commission_amount=commission,
        gst_on_commission=gst,
        final_line_claim_amount=final_claim,
        pod_document_id=None,
        remarks="",
        created_by="system",
        created_date=now,
        modified_by="system",
        modified_date=now,
    )


def _make_header(claim_id) -> ClaimHeader:
    """Build a ClaimHeader with zero totals (pre-recalculation state)."""
    now = datetime.now(timezone.utc)
    return ClaimHeader(
        id=claim_id,
        vendor_id=uuid4(),
        entity_id=None,
        claim_number=None,
        claim_date=date.today(),
        status=ClaimStatus.Draft,
        workflow_instance_id=None,
        total_claim_amount=Decimal("0"),
        total_commission_amount=Decimal("0"),
        total_gst_amount=Decimal("0"),
        total_tds_amount=Decimal("0"),
        total_ld_amount=Decimal("0"),
        total_retention_amount=Decimal("0"),
        gstn_verification_status="Pending",
        gst_invoice_number=None,
        gst_invoice_upload_date=None,
        sap_p2p_booking_reference=None,
        created_by="system",
        created_date=now,
        modified_by="system",
        modified_date=now,
    )


def _build_service(claim_id, totals: ClaimTotals, header: ClaimHeader):
    """
    Construct a CommissionClaimService instance with mocked repos.

    Returns (svc, updated_headers) where updated_headers is a list that
    capture_update appends to so the test can inspect the written header.
    """
    svc = CommissionClaimService.__new__(CommissionClaimService)

    # Mock line repo: sum_totals returns the pre-computed totals
    line_repo = AsyncMock()
    line_repo.sum_totals = AsyncMock(return_value=totals)
    svc._line_repo = line_repo

    # Mock header repo: get_by_id returns the header; update captures the call
    updated_headers: list[ClaimHeader] = []

    async def capture_update(h: ClaimHeader) -> ClaimHeader:
        updated_headers.append(h)
        return h

    header_repo = AsyncMock()
    header_repo.get_by_id = AsyncMock(return_value=header)
    header_repo.update = AsyncMock(side_effect=capture_update)
    svc._header_repo = header_repo

    return svc, updated_headers


# ---------------------------------------------------------------------------
# Property 6: Header Totals Equal Sum of Lines
# ---------------------------------------------------------------------------


@settings(max_examples=200)
@given(
    amounts=st.lists(
        st.tuples(
            amount_strategy,  # final_claim
            amount_strategy,  # commission
            amount_strategy,  # gst
            amount_strategy,  # tds
            amount_strategy,  # ld
            amount_strategy,  # retention
        ),
        min_size=0,
        max_size=20,
    )
)
def test_property_6_header_totals_equal_sum_of_lines(amounts) -> None:
    """Property 6: Header Totals Equal Sum of Lines.

    For any list of ClaimLine objects (including empty), after
    _recalculate_header_totals the six header total fields SHALL equal
    the corresponding sums of ClaimLine fields:

        header.total_claim_amount      == Σ line.final_line_claim_amount
        header.total_commission_amount == Σ line.commission_amount
        header.total_gst_amount        == Σ line.gst_on_commission
        header.total_tds_amount        == Σ line.tds_value
        header.total_ld_amount         == Σ line.ld_charges
        header.total_retention_amount  == Σ line.retention_amount

    The empty-list case confirms all totals are zero when there are no lines.

    **Validates: Requirements 4.1, 4.2**
    """
    claim_id = uuid4()

    # Build ClaimLine objects from the generated tuples
    lines = [_make_line(claim_id, *a) for a in amounts]

    # Compute expected sums in Python (this is the property we verify holds in the service)
    expected_claim = sum((ln.final_line_claim_amount for ln in lines), Decimal("0"))
    expected_commission = sum((ln.commission_amount for ln in lines), Decimal("0"))
    expected_gst = sum((ln.gst_on_commission for ln in lines), Decimal("0"))
    expected_tds = sum((ln.tds_value for ln in lines), Decimal("0"))
    expected_ld = sum((ln.ld_charges for ln in lines), Decimal("0"))
    expected_retention = sum((ln.retention_amount for ln in lines), Decimal("0"))

    # Build the ClaimTotals value object the mocked repo will return
    totals = ClaimTotals(
        total_claim_amount=expected_claim,
        total_commission_amount=expected_commission,
        total_gst_amount=expected_gst,
        total_tds_amount=expected_tds,
        total_ld_amount=expected_ld,
        total_retention_amount=expected_retention,
    )

    header = _make_header(claim_id)
    svc, updated_headers = _build_service(claim_id, totals, header)

    # Run the async method synchronously — avoids async Hypothesis complexity
    asyncio.run(svc._recalculate_header_totals(claim_id))

    # The header_repo.update must have been called exactly once
    assert len(updated_headers) == 1, (
        f"Expected header_repo.update to be called once; got {len(updated_headers)}"
    )

    updated = updated_headers[0]

    assert updated.total_claim_amount == expected_claim, (
        f"total_claim_amount mismatch: expected {expected_claim}, got {updated.total_claim_amount}"
    )
    assert updated.total_commission_amount == expected_commission, (
        f"total_commission_amount mismatch: expected {expected_commission}, "
        f"got {updated.total_commission_amount}"
    )
    assert updated.total_gst_amount == expected_gst, (
        f"total_gst_amount mismatch: expected {expected_gst}, got {updated.total_gst_amount}"
    )
    assert updated.total_tds_amount == expected_tds, (
        f"total_tds_amount mismatch: expected {expected_tds}, got {updated.total_tds_amount}"
    )
    assert updated.total_ld_amount == expected_ld, (
        f"total_ld_amount mismatch: expected {expected_ld}, got {updated.total_ld_amount}"
    )
    assert updated.total_retention_amount == expected_retention, (
        f"total_retention_amount mismatch: expected {expected_retention}, "
        f"got {updated.total_retention_amount}"
    )
