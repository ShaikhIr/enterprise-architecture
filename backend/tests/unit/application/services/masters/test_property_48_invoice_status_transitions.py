# Feature: lacm-masters, Property 48: Invoice status transitions.
"""Property-based test for the Invoice status lifecycle transitions.

Property 48: Invoice status transitions.

**Validates: Requirements 17.1, 17.2**

*For any* existing Invoice Header, recording a SAP payment confirmation sets the
Payment Clearing Date and SAP Clearing Document No to the supplied values and the
Status to ``Payment Cleared`` (Req 17.1); reaching final claim approval
(``mark_settled``) sets the Status to ``Settled`` (Req 17.2).

The service is exercised end-to-end through real in-memory implementations of
its repository ports (not mocks). A fresh service/repository set is built per
generated example so no state leaks between examples. The async service is
driven with ``asyncio.run`` because each Hypothesis example is independent.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from uuid import UUID, uuid4

from hypothesis import given, settings
from hypothesis import strategies as st

from src.application.services.masters.invoice_service import (
    InvoiceCreateInput,
    InvoiceLineInput,
    InvoiceService,
    SapPaymentInput,
)
from src.domain.entities.masters.invoice import (
    InvoiceHeaderEntity,
    InvoiceLineEntity,
)
from src.domain.entities.user import User
from src.domain.enums.masters import InvoiceStatus


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

    async def get_by_invoice_number(
        self, invoice_number: str
    ) -> InvoiceHeaderEntity | None:
        for h in self._store.values():
            if h.invoice_number == invoice_number:
                return h
        return None

    async def update(self, header: InvoiceHeaderEntity) -> InvoiceHeaderEntity:
        self._store[header.id] = header
        return header

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
    """No applicable agreements — Due Date resolution is not under test here."""

    async def find_overlapping_active(
        self,
        vendor_id: UUID,
        product_detail_id: UUID,
        from_date: date,
        to_date: date,
        exclude_id: UUID | None = None,
    ) -> list[object]:
        return []


# ─── Scenario generation ───


@dataclass(frozen=True)
class _Scenario:
    invoice_date: date
    payment_clearing_date: date
    sap_clearing_document_no: str
    address_by_number: bool


_dates = st.dates(min_value=date(2000, 1, 1), max_value=date(2100, 1, 1))
# Non-empty after trimming, ≤ 50 chars (the service rejects blank / over-long).
_sap_document_nos = st.text(
    alphabet=st.characters(min_codepoint=33, max_codepoint=126),
    min_size=1,
    max_size=50,
)


@st.composite
def _scenarios(draw: st.DrawFn) -> _Scenario:
    return _Scenario(
        invoice_date=draw(_dates),
        payment_clearing_date=draw(_dates),
        sap_clearing_document_no=draw(_sap_document_nos),
        address_by_number=draw(st.booleans()),
    )


async def _seed_invoice(
    service: InvoiceService, actor: User, invoice_date: date
) -> InvoiceHeaderEntity:
    """Create a fresh Open invoice to transition."""
    vendor_id = uuid4()
    customer_id = uuid4()
    product_detail_id = uuid4()
    service._vendor_repo.existing.add(vendor_id)  # type: ignore[attr-defined]
    service._customer_repo.existing.add(customer_id)  # type: ignore[attr-defined]
    service._product_repo.existing.add(product_detail_id)  # type: ignore[attr-defined]
    return await service.create_invoice(
        InvoiceCreateInput(
            invoice_number="INV-001",
            invoice_date=invoice_date,
            vendor_id=vendor_id,
            customer_id=customer_id,
            bill_amount_excl_gst=Decimal("100.00"),
            lines=[InvoiceLineInput(product_detail_id=product_detail_id)],
        ),
        actor,
    )


@settings(max_examples=20)
@given(scenario=_scenarios())
def test_invoice_status_transitions(scenario: _Scenario) -> None:
    """SAP payment → Payment Cleared (with fields set); settle → Settled."""

    async def run() -> tuple[InvoiceStatus, date, str, InvoiceStatus]:
        invoice_repo = _FakeInvoiceRepository()
        service = InvoiceService(
            session=None,  # type: ignore[arg-type]
            invoice_repo=invoice_repo,  # type: ignore[arg-type]
            vendor_repo=_FakeVendorRepository(),  # type: ignore[arg-type]
            customer_repo=_FakeCustomerRepository(),  # type: ignore[arg-type]
            product_repo=_FakeProductRepository(),  # type: ignore[arg-type]
            agreement_repo=_FakeAgreementRepository(),  # type: ignore[arg-type]
        )
        actor = User(id=uuid4(), username="admin", is_active=True)

        created = await _seed_invoice(service, actor, scenario.invoice_date)
        assert created.invoice_status == InvoiceStatus.Open

        # Address the header by id or by invoice number (both are supported).
        payment_input = (
            SapPaymentInput(
                invoice_number=created.invoice_number,
                payment_clearing_date=scenario.payment_clearing_date,
                sap_clearing_document_no=scenario.sap_clearing_document_no,
            )
            if scenario.address_by_number
            else SapPaymentInput(
                invoice_id=created.id,
                payment_clearing_date=scenario.payment_clearing_date,
                sap_clearing_document_no=scenario.sap_clearing_document_no,
            )
        )

        # Req 17.1: SAP payment confirmation. Snapshot the persisted state
        # immediately, since the fake returns the live entity that the next
        # transition mutates in place.
        await service.record_sap_payment(payment_input, actor)
        stored = await invoice_repo.get_by_id(created.id)
        assert stored is not None
        payment_status = stored.invoice_status
        payment_clearing_date = stored.payment_clearing_date
        sap_document_no = stored.sap_clearing_document_no
        assert payment_clearing_date is not None
        assert sap_document_no is not None

        # Req 17.2: final claim approval.
        await service.mark_settled(created.id, actor)
        stored = await invoice_repo.get_by_id(created.id)
        assert stored is not None
        settle_status = stored.invoice_status
        return (
            payment_status,
            payment_clearing_date,
            sap_document_no,
            settle_status,
        )

    (
        payment_status,
        payment_clearing_date,
        sap_document_no,
        settle_status,
    ) = asyncio.run(run())

    # Req 17.1: SAP payment sets the supplied fields and Payment Cleared status.
    assert payment_status == InvoiceStatus.PaymentCleared
    assert payment_clearing_date == scenario.payment_clearing_date
    assert sap_document_no == scenario.sap_clearing_document_no

    # Req 17.2: final approval drives the status to Settled.
    assert settle_status == InvoiceStatus.Settled
