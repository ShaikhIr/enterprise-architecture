# Feature: lacm-masters, Property 45: Invoice creation is atomic and validated.
"""Property-based test for atomic, validated Invoice creation.

Property 45: Invoice creation is atomic and validated.

**Validates: Requirements 16.2, 16.3, 16.4**

For any create-Invoice request, nothing (neither header nor any line) is
persisted when the Invoice Number duplicates an existing header (Req 16.2),
when the referenced Vendor or Customer does not exist (Req 16.3), or when any
Invoice Line references a non-existent Product Detail (Req 16.4); conversely a
request whose references all exist and whose Invoice Number is unique persists
exactly one new header together with all of its lines.

The service is exercised end-to-end through real in-memory stand-ins (not
mocks): dict-backed Invoice/Vendor/Customer/Product repositories that
faithfully answer the existence and uniqueness queries ``InvoiceService`` makes
during ``create_invoice``. A fresh set of repositories (pre-seeded with one
existing invoice, vendor, customer, and product detail) is built per generated
example so no state leaks between examples; the async service is driven with
``asyncio.run``.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from decimal import Decimal
from datetime import date
from uuid import UUID, uuid4

from hypothesis import given, settings
from hypothesis import strategies as st

from src.application.exceptions.application_exceptions import (
    MasterConflictError,
    MasterValidationError,
)
from src.application.services.masters.invoice_service import (
    InvoiceCreateInput,
    InvoiceLineInput,
    InvoiceService,
)
from src.domain.entities.masters.invoice import InvoiceHeaderEntity
from src.domain.entities.user import User
from src.domain.enums.masters import InvoiceStatus


# ─── In-memory repositories (real implementations, not mocks) ───


class _InMemoryInvoiceRepository:
    """Dict-backed Invoice aggregate store answering existence/uniqueness."""

    def __init__(self) -> None:
        self._store: dict[UUID, InvoiceHeaderEntity] = {}

    async def create(self, header, lines):
        header.lines = list(lines)
        self._store[header.id] = header
        return header

    async def get_by_id(self, header_id: UUID):
        return self._store.get(header_id)

    async def exists_by_invoice_number(
        self, invoice_number: str, exclude_id: UUID | None = None
    ) -> bool:
        return any(
            h.invoice_number == invoice_number and h.id != exclude_id
            for h in self._store.values()
        )

    async def count(self) -> int:
        return len(self._store)

    def seed(self, header: InvoiceHeaderEntity) -> None:
        self._store[header.id] = header


class _InMemoryVendorRepository:
    def __init__(self) -> None:
        self.existing: set[UUID] = set()

    async def get_by_id(self, vendor_id: UUID):
        return object() if vendor_id in self.existing else None


class _InMemoryCustomerRepository:
    def __init__(self) -> None:
        self.existing: set[UUID] = set()

    async def get_by_id(self, customer_id: UUID):
        return object() if customer_id in self.existing else None


class _InMemoryProductRepository:
    def __init__(self) -> None:
        self.existing: set[UUID] = set()

    async def get_detail_by_id(self, detail_id: UUID):
        return object() if detail_id in self.existing else None


class _NoAgreementRepository:
    """No applicable agreements — Due Date resolution is irrelevant here."""

    async def find_overlapping_active(self, *args, **kwargs):
        return []


# ─── World built per generated example ───

_EXISTING_INVOICE_NUMBER = "INV-EXISTING"


def _build_service() -> tuple[
    InvoiceService,
    _InMemoryInvoiceRepository,
    UUID,
    UUID,
    UUID,
]:
    """Build a service whose repos already know one vendor/customer/product and
    one existing invoice (so duplicate-number requests can be exercised)."""
    invoice_repo = _InMemoryInvoiceRepository()
    vendor_repo = _InMemoryVendorRepository()
    customer_repo = _InMemoryCustomerRepository()
    product_repo = _InMemoryProductRepository()

    known_vendor = uuid4()
    known_customer = uuid4()
    known_product = uuid4()
    vendor_repo.existing.add(known_vendor)
    customer_repo.existing.add(known_customer)
    product_repo.existing.add(known_product)

    invoice_repo.seed(
        InvoiceHeaderEntity(
            id=uuid4(),
            invoice_number=_EXISTING_INVOICE_NUMBER,
            invoice_date=date(2024, 1, 1),
            vendor_id=known_vendor,
            customer_id=known_customer,
            bill_amount_excl_gst=Decimal("10"),
            invoice_status=InvoiceStatus.Open,
        )
    )

    service = InvoiceService(
        session=None,  # type: ignore[arg-type]
        invoice_repo=invoice_repo,  # type: ignore[arg-type]
        vendor_repo=vendor_repo,  # type: ignore[arg-type]
        customer_repo=customer_repo,  # type: ignore[arg-type]
        product_repo=product_repo,  # type: ignore[arg-type]
        agreement_repo=_NoAgreementRepository(),  # type: ignore[arg-type]
    )
    return service, invoice_repo, known_vendor, known_customer, known_product


# ─── Generators ───


@dataclass(frozen=True)
class _Request:
    """A create request described by which references exist + number-collision.

    Concrete IDs/numbers are materialised against the per-example world so each
    flag maps to a genuinely existing or genuinely unknown reference.
    """

    vendor_exists: bool
    customer_exists: bool
    duplicate_number: bool
    line_products_exist: tuple[bool, ...]


_requests = st.builds(
    _Request,
    vendor_exists=st.booleans(),
    customer_exists=st.booleans(),
    duplicate_number=st.booleans(),
    line_products_exist=st.lists(
        st.booleans(), min_size=1, max_size=4
    ).map(tuple),
)


@settings(max_examples=20, deadline=None)
@given(req=_requests)
def test_invoice_creation_is_atomic_and_validated(req: _Request) -> None:
    """Bad reference/number ⇒ rejected + nothing stored; all-valid ⇒ one stored."""
    actor = User(id=uuid4(), username="admin", is_active=True)

    async def scenario():
        service, invoice_repo, vendor, customer, product = _build_service()
        count_before = await invoice_repo.count()

        vendor_id = vendor if req.vendor_exists else uuid4()
        customer_id = customer if req.customer_exists else uuid4()
        invoice_number = (
            _EXISTING_INVOICE_NUMBER if req.duplicate_number else f"INV-{uuid4()}"
        )
        lines = [
            InvoiceLineInput(
                product_master_id=product if exists else uuid4()
            )
            for exists in req.line_products_exist
        ]
        data = InvoiceCreateInput(
            invoice_number=invoice_number,
            invoice_date=date(2024, 1, 10),
            vendor_id=vendor_id,
            customer_id=customer_id,
            bill_amount_excl_gst=Decimal("100.00"),
            lines=lines,
        )

        raised: Exception | None = None
        created = None
        try:
            created = await service.create_invoice(data, actor)
        except (MasterValidationError, MasterConflictError) as exc:
            raised = exc

        count_after = await invoice_repo.count()
        return raised, created, count_before, count_after

    raised, created, count_before, count_after = asyncio.run(scenario())

    is_valid = (
        req.vendor_exists
        and req.customer_exists
        and all(req.line_products_exist)
        and not req.duplicate_number
    )

    if is_valid:
        # Valid request: persisted exactly one new header with all its lines.
        assert raised is None
        assert created is not None
        assert count_after == count_before + 1
        assert len(created.lines) == len(req.line_products_exist)
        assert all(
            line.invoice_header_id == created.id for line in created.lines
        )
    else:
        # Any bad reference or duplicate number ⇒ rejected, nothing persisted.
        assert created is None
        assert raised is not None
        assert count_after == count_before

        # Validation precedence: references (16.3/16.4) checked before
        # uniqueness (16.2), so the conflict surfaces only when all refs exist.
        if not req.vendor_exists:
            assert isinstance(raised, MasterValidationError)
            assert raised.field == "vendor_id"
        elif not req.customer_exists:
            assert isinstance(raised, MasterValidationError)
            assert raised.field == "customer_id"
        elif not all(req.line_products_exist):
            assert isinstance(raised, MasterValidationError)
            assert "product_master_id" in raised.field
        else:  # duplicate_number
            assert isinstance(raised, MasterConflictError)
