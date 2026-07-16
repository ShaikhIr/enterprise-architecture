# Feature: lacm-masters, Property 46: Valid invoice creation defaults and due-date computation.
"""Property-based test for valid Invoice creation defaults + Due Date computation.

Property 46: Valid invoice creation defaults and due-date computation.

**Validates: Requirements 16.5, 16.6, 16.7**

*For any* valid create-Invoice request, the stored header has Amount Deducted 0,
TDS Value 0, and Status ``Open``; the Due Date equals the supplied value when
supplied (Req 16.7), otherwise Invoice Date + Credit Days from the applicable
Agreement when such an Agreement exists (Req 16.6), otherwise remains unset
(Req 16.8). In every case the defaults of Amount Deducted 0 / TDS 0 / Status
``Open`` hold (Req 16.5).

The service is exercised end-to-end through real in-memory implementations of
its repository ports (not mocks). A fresh service/repository set is built per
generated example so no state leaks between examples. The async service is
driven with ``asyncio.run`` because each Hypothesis example is independent.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from datetime import date, timedelta
from decimal import Decimal
from uuid import UUID, uuid4

from hypothesis import given, settings
from hypothesis import strategies as st

from src.application.services.masters.invoice_service import (
    InvoiceCreateInput,
    InvoiceLineInput,
    InvoiceService,
)
from src.domain.entities.masters.agreement import AgreementEntity
from src.domain.entities.masters.invoice import (
    InvoiceHeaderEntity,
    InvoiceLineEntity,
)
from src.domain.entities.user import User
from src.domain.enums.masters import AgreementStatus, InvoiceStatus


# ─── In-memory fakes (duck-typed against the repository ports) ───


class _FakeInvoiceRepository:
    """In-memory invoice header/line aggregate store."""

    def __init__(self) -> None:
        self._store: dict[UUID, InvoiceHeaderEntity] = {}

    async def create(
        self, header: InvoiceHeaderEntity, lines: list[InvoiceLineEntity]
    ) -> InvoiceHeaderEntity:
        header.lines = list(lines)
        self._store[header.id] = header
        return header

    async def get_by_id(self, header_id: UUID) -> InvoiceHeaderEntity | None:
        return self._store.get(header_id)

    async def exists_by_invoice_number(
        self, invoice_number: str, exclude_id: UUID | None = None
    ) -> bool:
        return any(
            h.invoice_number == invoice_number and h.id != exclude_id
            for h in self._store.values()
        )


class _FakeVendorRepository:
    def __init__(self) -> None:
        self.existing: set[UUID] = set()

    async def get_by_id(self, vendor_id: UUID) -> object | None:
        return object() if vendor_id in self.existing else None


class _FakeCustomerRepository:
    def __init__(self) -> None:
        self.existing: set[UUID] = set()

    async def get_by_id(self, customer_id: UUID) -> object | None:
        return object() if customer_id in self.existing else None


class _FakeProductRepository:
    def __init__(self) -> None:
        self.existing: set[UUID] = set()

    async def get_detail_by_id(self, detail_id: UUID) -> object | None:
        return object() if detail_id in self.existing else None


class _FakeAgreementRepository:
    """Returns active agreements covering a vendor + product detail + date."""

    def __init__(self) -> None:
        self._agreements: list[AgreementEntity] = []

    def add(self, agreement: AgreementEntity) -> None:
        self._agreements.append(agreement)

    async def find_overlapping_active(
        self,
        vendor_id: UUID,
        product_master_id: UUID,
        from_date: date,
        to_date: date,
        exclude_id: UUID | None = None,
    ) -> list[AgreementEntity]:
        return [
            a
            for a in self._agreements
            if a.vendor_id == vendor_id
            and a.product_master_id == product_master_id
            and a.status == AgreementStatus.Active
            and a.from_date is not None
            and a.to_date is not None
            and a.from_date <= to_date
            and from_date <= a.to_date
        ]


# ─── Scenario generation ───


@dataclass(frozen=True)
class _Scenario:
    invoice_date: date
    supplied_due_date: date | None
    # Agreement that is applicable to the first line (covers invoice date):
    applicable_credit_days: int | None
    bill_amount_excl_gst: Decimal
    line_count: int


# Bounded so that ``invoice_date + timedelta(days=credit_days)`` and the
# agreement validity window stay well within ``date`` range.
_invoice_dates = st.dates(min_value=date(2000, 1, 1), max_value=date(2100, 1, 1))
_credit_days = st.integers(min_value=0, max_value=3650)
_bill_amounts = st.integers(min_value=0, max_value=10_000_000).map(
    lambda cents: Decimal(cents) / Decimal("100")
)


@st.composite
def _scenarios(draw: st.DrawFn) -> _Scenario:
    invoice_date = draw(_invoice_dates)
    supply_due_date = draw(st.booleans())
    supplied_due_date = (
        draw(st.dates(min_value=date(2000, 1, 1), max_value=date(2100, 1, 1)))
        if supply_due_date
        else None
    )
    has_agreement = draw(st.booleans())
    applicable_credit_days = draw(_credit_days) if has_agreement else None
    bill_amount = draw(_bill_amounts)
    line_count = draw(st.integers(min_value=1, max_value=3))
    return _Scenario(
        invoice_date=invoice_date,
        supplied_due_date=supplied_due_date,
        applicable_credit_days=applicable_credit_days,
        bill_amount_excl_gst=bill_amount,
        line_count=line_count,
    )


@settings(max_examples=20)
@given(scenario=_scenarios())
def test_invoice_creation_defaults_and_due_date(scenario: _Scenario) -> None:
    """Valid create-Invoice applies fixed defaults and resolves the Due Date.

    Defaults hold unconditionally (Amount Deducted 0, TDS 0, Status Open).
    Due Date resolution follows the precedence supplied > agreement > unset.
    """

    async def run() -> InvoiceHeaderEntity:
        invoice_repo = _FakeInvoiceRepository()
        vendor_repo = _FakeVendorRepository()
        customer_repo = _FakeCustomerRepository()
        product_repo = _FakeProductRepository()
        agreement_repo = _FakeAgreementRepository()

        vendor_id = uuid4()
        customer_id = uuid4()
        vendor_repo.existing.add(vendor_id)
        customer_repo.existing.add(customer_id)

        product_master_ids = [uuid4() for _ in range(scenario.line_count)]
        for pid in product_master_ids:
            product_repo.existing.add(pid)

        # An applicable agreement covers the first line's product detail and a
        # validity window straddling the invoice date.
        if scenario.applicable_credit_days is not None:
            agreement_repo.add(
                AgreementEntity(
                    id=uuid4(),
                    vendor_id=vendor_id,
                    product_master_id=product_master_ids[0],
                    from_date=scenario.invoice_date - timedelta(days=1),
                    to_date=scenario.invoice_date + timedelta(days=1),
                    credit_days=scenario.applicable_credit_days,
                    status=AgreementStatus.Active,
                )
            )

        service = InvoiceService(
            session=None,  # type: ignore[arg-type]
            invoice_repo=invoice_repo,  # type: ignore[arg-type]
            vendor_repo=vendor_repo,  # type: ignore[arg-type]
            customer_repo=customer_repo,  # type: ignore[arg-type]
            product_repo=product_repo,  # type: ignore[arg-type]
            agreement_repo=agreement_repo,  # type: ignore[arg-type]
        )
        actor = User(id=uuid4(), username="admin", is_active=True)

        created = await service.create_invoice(
            InvoiceCreateInput(
                invoice_number="INV-001",
                invoice_date=scenario.invoice_date,
                vendor_id=vendor_id,
                customer_id=customer_id,
                bill_amount_excl_gst=scenario.bill_amount_excl_gst,
                lines=[
                    InvoiceLineInput(product_master_id=pid)
                    for pid in product_master_ids
                ],
                due_date=scenario.supplied_due_date,
                # amount_deducted / tds_value intentionally omitted to exercise
                # the 0 defaults (Req 16.5).
            ),
            actor,
        )
        # Read back what was persisted.
        stored = await invoice_repo.get_by_id(created.id)
        assert stored is not None
        return stored

    stored = asyncio.run(run())

    # Fixed defaults always hold (Req 16.5).
    assert stored.amount_deducted == Decimal("0")
    assert stored.tds_value == Decimal("0")
    assert stored.invoice_status == InvoiceStatus.Open

    # Due Date resolution precedence (Req 16.6, 16.7, and 16.8 for the unset
    # fall-through): supplied wins; else agreement-computed; else unset.
    if scenario.supplied_due_date is not None:
        expected_due_date: date | None = scenario.supplied_due_date
    elif scenario.applicable_credit_days is not None:
        expected_due_date = scenario.invoice_date + timedelta(
            days=scenario.applicable_credit_days
        )
    else:
        expected_due_date = None

    assert stored.due_date == expected_due_date
