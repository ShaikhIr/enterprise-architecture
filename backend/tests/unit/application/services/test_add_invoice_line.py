"""
Unit tests for CommissionClaimService.add_invoice_line.

Updated for multi-product logic:
- One ClaimLine created per invoice product line
- Vendor-Customer Mapping uses claim.vendor_id + invoice.customer_id
- Agreement lookup uses claim.vendor_id + product_master_id

Requirements: 2.1, 2.2, 2.3, 2.4, 2.5, 3.1, 3.10, 3.11, 3.12, 4.1, 4.2
"""
from __future__ import annotations

from datetime import date, datetime, timezone
from decimal import Decimal
from typing import Any
from unittest.mock import AsyncMock, MagicMock
from uuid import UUID, uuid4

import pytest

from src.application.services.commission_claim_service import (
    CommissionClaimService,
    LineOverrides,
)
from src.domain.entities.claim_audit_entry import ClaimAuditEntry
from src.domain.entities.commission_claim import ClaimHeader, ClaimLine, ClaimStatus
from src.domain.enums.masters import AgreementStatus, InvoiceStatus, MappingStatus


# ─── Helpers ──────────────────────────────────────────────────────────────────

def _actor() -> Any:
    actor = MagicMock()
    actor.id = uuid4()
    actor.username = "test_user"
    return actor


def _make_invoice(
    *,
    invoice_id: UUID | None = None,
    customer_id: UUID | None = None,
    invoice_date: date = date(2024, 1, 15),
    payment_clearing_date: date | None = date(2024, 2, 10),
    invoice_status: str = InvoiceStatus.PaymentCleared.value,
    amount_deducted: Decimal = Decimal("0"),
    tds_value: Decimal = Decimal("0"),
) -> MagicMock:
    inv = MagicMock()
    inv.id = invoice_id or uuid4()
    inv.customer_id = customer_id or uuid4()
    inv.invoice_date = invoice_date
    inv.payment_clearing_date = payment_clearing_date
    inv.invoice_status = invoice_status
    inv.amount_deducted = amount_deducted
    inv.tds_value = tds_value
    return inv


def _make_invoice_line(
    *,
    product_master_id: UUID | None = None,
    line_amount: Decimal = Decimal("100000"),
) -> MagicMock:
    ln = MagicMock()
    ln.product_master_id = product_master_id or uuid4()
    ln.line_amount = line_amount
    return ln


def _make_mapping() -> MagicMock:
    m = MagicMock()
    m.status = MappingStatus.Active.value
    return m


def _make_agreement(
    *,
    slab_in_days: int = 30,
    reduction_percent: Decimal = Decimal("1"),
    max_commission_percent: Decimal = Decimal("5"),
    min_commission_percent: Decimal = Decimal("1"),
    credit_days: int = 30,
) -> MagicMock:
    ag = MagicMock()
    ag.slab_in_days = slab_in_days
    ag.reduction_percent = reduction_percent
    ag.max_commission_percent = max_commission_percent
    ag.min_commission_percent = min_commission_percent
    ag.credit_days = credit_days
    ag.status = AgreementStatus.Active.value
    return ag


def _make_claim_header(claim_id: UUID | None = None) -> ClaimHeader:
    now = datetime.now(timezone.utc)
    return ClaimHeader(
        id=claim_id or uuid4(),
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


def _make_claim_line(claim_id: UUID, invoice_id: UUID) -> ClaimLine:
    now = datetime.now(timezone.utc)
    return ClaimLine(
        id=uuid4(),
        claim_header_id=claim_id,
        invoice_header_id=invoice_id,
        product_master_id=uuid4(),
        customer_id=uuid4(),
        bill_amount_excl_gst=Decimal("100000"),
        amount_deducted=Decimal("0"),
        tds_value=Decimal("0"),
        ld_charges=Decimal("0"),
        retention_amount=Decimal("0"),
        net_amount=Decimal("100000"),
        commission_payable_base=Decimal("100000"),
        due_date=date(2024, 2, 14),
        payment_clearing_date=date(2024, 2, 10),
        delay_days=-4,
        applicable_commission_percent=Decimal("5"),
        commission_amount=Decimal("5000"),
        gst_on_commission=Decimal("900"),
        final_line_claim_amount=Decimal("5900"),
        pod_document_id=None,
        remarks="",
        created_by="test_user",
        created_date=now,
        modified_by="test_user",
        modified_date=now,
    )


def _build_service(
    *,
    claim: ClaimHeader | None = None,
    invoice: MagicMock | None = None,
    invoice_lines: list[MagicMock] | None = None,
    mapping: MagicMock | None = None,
    agreements: list[MagicMock] | None = None,
    saved_line: ClaimLine | None = None,
) -> CommissionClaimService:
    """
    Build a CommissionClaimService with fully mocked session and repositories.

    New multi-product flow:
      1. InvoiceHeaderModel   → scalar_one_or_none
      2. InvoiceLineModel     → scalars().all()   (returns list)
      3. MappingModel         → scalar_one_or_none
      4. AgreementModel       → scalar_one_or_none  (once per product line)
    """
    session = AsyncMock()
    svc = CommissionClaimService.__new__(CommissionClaimService)
    svc._session = session
    svc._audit_service = MagicMock()
    svc._workflow_engine = MagicMock()

    # Header repo
    header_repo = AsyncMock()
    header_repo.get_by_id = AsyncMock(return_value=claim)
    header_repo.update = AsyncMock(side_effect=lambda h: h)
    svc._header_repo = header_repo

    # Line repo
    from src.domain.repositories.commission_claim.claim_line_repository import ClaimTotals
    line_repo = AsyncMock()
    line_repo.create = AsyncMock(
        return_value=saved_line or (
            _make_claim_line(claim.id, uuid4()) if claim else MagicMock()
        )
    )
    line_repo.sum_totals = AsyncMock(
        return_value=ClaimTotals(
            total_claim_amount=Decimal("5900"),
            total_commission_amount=Decimal("5000"),
            total_gst_amount=Decimal("900"),
            total_tds_amount=Decimal("0"),
            total_ld_amount=Decimal("0"),
            total_retention_amount=Decimal("0"),
        )
    )
    svc._line_repo = line_repo

    # Audit repo
    audit_repo = AsyncMock()
    audit_repo.create = AsyncMock(side_effect=lambda e: e)
    svc._audit_repo = audit_repo
    svc._claim_number_service = MagicMock()

    # Build session.execute side_effect sequence
    # 1: invoice header (scalar_one_or_none)
    # 2: invoice lines (scalars().all())
    # 3: mapping (scalar_one_or_none)
    # 4+: one agreement per invoice line (scalar_one_or_none each)
    def _scalar_result(obj):
        r = MagicMock()
        r.scalar_one_or_none.return_value = obj
        return r

    def _scalars_all_result(objs):
        r = MagicMock()
        scalars_mock = MagicMock()
        scalars_mock.all.return_value = objs or []
        r.scalars.return_value = scalars_mock
        return r

    inv_lines = invoice_lines if invoice_lines is not None else [_make_invoice_line()]
    ags = agreements if agreements is not None else [_make_agreement()]

    side_effects = [
        _scalar_result(invoice),           # InvoiceHeaderModel
        _scalars_all_result(inv_lines),     # InvoiceLineModel list
        _scalar_result(mapping),            # MappingModel
    ]
    # One agreement lookup per invoice line
    for ag in ags:
        side_effects.append(_scalar_result(ag))

    session.execute = AsyncMock(side_effect=side_effects)
    return svc


# ─── Pre-condition 1: invoice_status ─────────────────────────────────────────

@pytest.mark.asyncio
async def test_settled_invoice_raises_exact_error_message():
    """Req 2.1 — settled invoice raises ValueError with exact message."""
    claim = _make_claim_header()
    invoice = _make_invoice(invoice_status=InvoiceStatus.Settled.value)
    svc = _build_service(claim=claim, invoice=invoice)

    with pytest.raises(ValueError, match="Invoice is already settled."):
        await svc.add_invoice_line(claim.id, invoice.id, LineOverrides(), _actor())


@pytest.mark.asyncio
async def test_claim_not_found_raises_error():
    """Service raises ValueError when claim_id does not exist."""
    svc = _build_service(claim=None)
    svc._session.execute = AsyncMock()

    with pytest.raises(ValueError, match="Claim not found"):
        await svc.add_invoice_line(uuid4(), uuid4(), LineOverrides(), _actor())


@pytest.mark.asyncio
async def test_invoice_not_found_raises_error():
    """Service raises ValueError when invoice_id does not exist."""
    claim = _make_claim_header()

    def _none_result():
        r = MagicMock()
        r.scalar_one_or_none.return_value = None
        return r

    svc = _build_service(claim=claim)
    svc._session.execute = AsyncMock(return_value=_none_result())

    with pytest.raises(ValueError, match="Invoice not found"):
        await svc.add_invoice_line(claim.id, uuid4(), LineOverrides(), _actor())


# ─── Pre-condition 2: Vendor-Customer Mapping ─────────────────────────────────

@pytest.mark.asyncio
async def test_no_active_mapping_raises_error():
    """Req 2.2 — missing active mapping blocks the line addition."""
    claim = _make_claim_header()
    invoice = _make_invoice()
    svc = _build_service(claim=claim, invoice=invoice, mapping=None)

    with pytest.raises(ValueError, match="No active Vendor-Customer Mapping found"):
        await svc.add_invoice_line(claim.id, invoice.id, LineOverrides(), _actor())


# ─── Pre-condition 3: Agreement Master ───────────────────────────────────────

@pytest.mark.asyncio
async def test_no_active_agreement_raises_error():
    """Req 2.3 — missing active agreement blocks the add."""
    claim = _make_claim_header()
    invoice = _make_invoice()
    mapping = _make_mapping()
    svc = _build_service(claim=claim, invoice=invoice, mapping=mapping, agreements=[None])

    with pytest.raises(ValueError, match="No active Agreement Master found"):
        await svc.add_invoice_line(claim.id, invoice.id, LineOverrides(), _actor())


# ─── Pre-condition 4: payment_clearing_date >= invoice_date ──────────────────

@pytest.mark.asyncio
async def test_clearing_date_before_invoice_date_raises_error():
    """Req 3.11 — payment_clearing_date < invoice_date must be rejected."""
    claim = _make_claim_header()
    invoice = _make_invoice(
        invoice_date=date(2024, 3, 1),
        payment_clearing_date=date(2024, 2, 28),
    )
    mapping = _make_mapping()
    agreement = _make_agreement()
    svc = _build_service(
        claim=claim, invoice=invoice,
        mapping=mapping, agreements=[agreement],
    )

    with pytest.raises(ValueError, match="Payment Clearing Date cannot be earlier than Invoice Date."):
        await svc.add_invoice_line(claim.id, invoice.id, LineOverrides(), _actor())


# ─── Happy path ────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_due_date_defaults_to_invoice_date_plus_credit_days():
    """Req 2.4 — when no due_date_override, due_date = invoice_date + credit_days."""
    claim = _make_claim_header()
    invoice = _make_invoice(invoice_date=date(2024, 1, 15), payment_clearing_date=date(2024, 2, 10))
    mapping = _make_mapping()
    agreement = _make_agreement(credit_days=30)
    svc = _build_service(claim=claim, invoice=invoice, mapping=mapping, agreements=[agreement])

    await svc.add_invoice_line(claim.id, invoice.id, LineOverrides(), _actor())

    from datetime import timedelta
    created_line: ClaimLine = svc._line_repo.create.call_args[0][0]
    assert created_line.due_date == date(2024, 1, 15) + timedelta(days=30)


@pytest.mark.asyncio
async def test_due_date_override_is_respected():
    """Req 2.5 — when due_date_override is supplied it takes precedence."""
    claim = _make_claim_header()
    invoice = _make_invoice(invoice_date=date(2024, 1, 15), payment_clearing_date=date(2024, 2, 10))
    mapping = _make_mapping()
    agreement = _make_agreement(credit_days=30)
    svc = _build_service(claim=claim, invoice=invoice, mapping=mapping, agreements=[agreement])

    override_due = date(2024, 2, 5)
    await svc.add_invoice_line(claim.id, invoice.id, LineOverrides(due_date_override=override_due), _actor())

    created_line: ClaimLine = svc._line_repo.create.call_args[0][0]
    assert created_line.due_date == override_due


@pytest.mark.asyncio
async def test_one_claim_line_created_per_invoice_product():
    """New multi-product logic: one ClaimLine per invoice line."""
    claim = _make_claim_header()
    invoice = _make_invoice(invoice_date=date(2024, 1, 15), payment_clearing_date=date(2024, 2, 10))
    mapping = _make_mapping()
    # Two invoice lines with different products
    inv_lines = [_make_invoice_line(), _make_invoice_line()]
    agreements = [_make_agreement(), _make_agreement()]
    svc = _build_service(
        claim=claim, invoice=invoice,
        invoice_lines=inv_lines, mapping=mapping, agreements=agreements,
    )

    await svc.add_invoice_line(claim.id, invoice.id, LineOverrides(), _actor())

    # line_repo.create called twice — once per product line
    assert svc._line_repo.create.await_count == 2


@pytest.mark.asyncio
async def test_add_line_persists_formula_outputs():
    """Req 3.10 — 7 formula outputs stored on the ClaimLine."""
    claim = _make_claim_header()
    invoice = _make_invoice(invoice_date=date(2024, 1, 15), payment_clearing_date=date(2024, 2, 10))
    mapping = _make_mapping()
    agreement = _make_agreement(
        credit_days=30,
        max_commission_percent=Decimal("5"),
        min_commission_percent=Decimal("1"),
        slab_in_days=30,
        reduction_percent=Decimal("1"),
    )
    svc = _build_service(claim=claim, invoice=invoice, mapping=mapping, agreements=[agreement])

    await svc.add_invoice_line(claim.id, invoice.id, LineOverrides(), _actor())

    created_line: ClaimLine = svc._line_repo.create.call_args[0][0]
    assert created_line.net_amount >= Decimal("0")
    assert created_line.delay_days <= 0  # on-time payment
    assert created_line.applicable_commission_percent == Decimal("5")


@pytest.mark.asyncio
async def test_display_only_fields_stored():
    """Req 3.12 — ld_charges and retention_amount stored but not in formula."""
    claim = _make_claim_header()
    invoice = _make_invoice(invoice_date=date(2024, 1, 15), payment_clearing_date=date(2024, 2, 10))
    mapping = _make_mapping()
    agreement = _make_agreement()
    svc = _build_service(claim=claim, invoice=invoice, mapping=mapping, agreements=[agreement])

    overrides = LineOverrides(ld_charges=Decimal("500"), retention_amount=Decimal("200"), remarks="test")
    await svc.add_invoice_line(claim.id, invoice.id, overrides, _actor())

    created_line: ClaimLine = svc._line_repo.create.call_args[0][0]
    assert created_line.ld_charges == Decimal("500")
    assert created_line.retention_amount == Decimal("200")
    assert created_line.remarks == "test"


@pytest.mark.asyncio
async def test_header_totals_recalculated_after_all_lines():
    """Req 4.1, 4.2 — _recalculate_header_totals called once after all lines."""
    claim = _make_claim_header()
    invoice = _make_invoice(invoice_date=date(2024, 1, 15), payment_clearing_date=date(2024, 2, 10))
    mapping = _make_mapping()
    inv_lines = [_make_invoice_line(), _make_invoice_line()]
    agreements = [_make_agreement(), _make_agreement()]
    svc = _build_service(
        claim=claim, invoice=invoice,
        invoice_lines=inv_lines, mapping=mapping, agreements=agreements,
    )

    await svc.add_invoice_line(claim.id, invoice.id, LineOverrides(), _actor())

    # sum_totals called once regardless of number of products
    svc._line_repo.sum_totals.assert_awaited_once_with(claim.id)


@pytest.mark.asyncio
async def test_audit_entry_written_with_line_added_action():
    """Req 14.1 — single audit entry with action='Line Added' written."""
    claim = _make_claim_header()
    invoice = _make_invoice(invoice_date=date(2024, 1, 15), payment_clearing_date=date(2024, 2, 10))
    mapping = _make_mapping()
    agreement = _make_agreement()
    svc = _build_service(claim=claim, invoice=invoice, mapping=mapping, agreements=[agreement])
    actor = _actor()

    await svc.add_invoice_line(claim.id, invoice.id, LineOverrides(), actor)

    svc._audit_repo.create.assert_awaited_once()
    audit_entry: ClaimAuditEntry = svc._audit_repo.create.call_args[0][0]
    assert audit_entry.action == "Line Added"
    assert audit_entry.claim_header_id == claim.id
    assert audit_entry.actor_username == actor.username


@pytest.mark.asyncio
async def test_add_line_returns_first_persisted_line():
    """Return value is the first created ClaimLine."""
    claim = _make_claim_header()
    invoice = _make_invoice(invoice_date=date(2024, 1, 15), payment_clearing_date=date(2024, 2, 10))
    mapping = _make_mapping()
    agreement = _make_agreement()
    expected_line = _make_claim_line(claim.id, invoice.id)
    svc = _build_service(
        claim=claim, invoice=invoice,
        mapping=mapping, agreements=[agreement],
        saved_line=expected_line,
    )

    result = await svc.add_invoice_line(claim.id, invoice.id, LineOverrides(), _actor())
    assert result is expected_line
