"""
Property 10: Settled Invoice Pre-Condition Rejection

For any invoice with ``invoice_status = "Settled"``, calling ``add_invoice_line``
ALWAYS raises ``ValueError("Invoice is already settled.")`` regardless of other
invoice attributes.

Validates: Requirements 2.1, 22.10
"""

import asyncio
from datetime import date
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from src.application.services.commission_claim_service import (
    CommissionClaimService,
    LineOverrides,
)
from src.domain.entities.commission_claim import ClaimHeader, ClaimStatus
from src.domain.enums.masters import InvoiceStatus

# Canonical "Settled" string as stored in the DB column
SETTLED = InvoiceStatus.Settled.value  # "Settled"


def _make_claim():
    from datetime import datetime, timezone

    now = datetime.now(timezone.utc)
    return ClaimHeader(
        id=uuid4(),
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


def _build_service_with_settled_invoice(invoice_mock):
    """Build a CommissionClaimService where session.execute returns the settled invoice."""
    svc = CommissionClaimService.__new__(CommissionClaimService)

    claim = _make_claim()
    header_repo = AsyncMock()
    header_repo.get_by_id = AsyncMock(return_value=claim)
    svc._header_repo = header_repo
    svc._line_repo = AsyncMock()
    svc._audit_repo = AsyncMock()
    svc._claim_number_service = AsyncMock()
    svc._workflow_engine = AsyncMock()
    svc._audit_service = AsyncMock()

    # session.execute returns the settled invoice as first scalar result
    result_mock = MagicMock()
    result_mock.scalar_one_or_none.return_value = invoice_mock
    session = AsyncMock()
    session.execute = AsyncMock(return_value=result_mock)
    svc._session = session

    return svc


@settings(max_examples=200)
@given(
    bill_amount=st.decimals(
        min_value=Decimal("0"),
        max_value=Decimal("1000000"),
        allow_nan=False,
        allow_infinity=False,
        places=2,
    ),
    vendor_id=st.uuids(),
    customer_id=st.uuids(),
    invoice_id=st.uuids(),
    invoice_date=st.dates(
        min_value=date(2020, 1, 1), max_value=date(2030, 12, 31)
    ),
)
def test_property_10_settled_invoice_always_rejected(
    bill_amount, vendor_id, customer_id, invoice_id, invoice_date
):
    """
    Property 10: For any invoice with invoice_status = 'Settled', add_invoice_line
    ALWAYS raises ValueError with message 'Invoice is already settled.'
    regardless of any other invoice attributes.

    Validates: Requirements 2.1, 22.10
    """
    # Build a mock invoice with Settled status and randomised other fields
    invoice = MagicMock()
    invoice.id = invoice_id
    invoice.invoice_status = SETTLED  # always "Settled"
    invoice.vendor_id = vendor_id
    invoice.customer_id = customer_id
    invoice.invoice_date = invoice_date
    invoice.bill_amount_excl_gst = bill_amount
    invoice.payment_clearing_date = invoice_date
    invoice.amount_deducted = Decimal("0")
    invoice.tds_value = Decimal("0")

    svc = _build_service_with_settled_invoice(invoice)

    actor = MagicMock()
    actor.username = "agent1"
    actor.id = uuid4()

    # The service must raise ValueError with the exact required message
    with pytest.raises(ValueError, match="Invoice is already settled\\."):
        asyncio.run(
            svc.add_invoice_line(
                svc._header_repo.get_by_id.return_value.id,
                invoice_id,
                LineOverrides(),
                actor,
            )
        )
