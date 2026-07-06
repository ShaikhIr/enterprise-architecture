"""
Unit tests for :class:`InvoiceService`.

These exercise the service's business rules (atomic create with reference
validation, default application, due-date resolution, cascade delete, and the
status lifecycle) against lightweight in-memory fake repositories, so the tests
validate actual service logic through the repository ports.
"""

from __future__ import annotations

from datetime import date, timedelta
from decimal import Decimal
from uuid import UUID, uuid4

import pytest

from src.application.exceptions.application_exceptions import (
    MasterConflictError,
    MasterNotFoundError,
    MasterValidationError,
)
from src.application.services.masters.invoice_service import (
    InvoiceCreateInput,
    InvoiceLineInput,
    InvoiceService,
    InvoiceUpdateInput,
    SapPaymentInput,
)
from src.domain.entities.masters.agreement import AgreementEntity
from src.domain.entities.masters.invoice import (
    InvoiceHeaderEntity,
    InvoiceLineEntity,
)
from src.domain.entities.user import User
from src.domain.enums.masters import AgreementStatus, InvoiceStatus


# ─── In-memory fakes (duck-typed against the repository ports) ───


class FakeInvoiceRepository:
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

    async def delete(self, header_id: UUID) -> None:
        self._store.pop(header_id, None)

    async def list(
        self, skip: int = 0, limit: int = 20
    ) -> list[InvoiceHeaderEntity]:
        ordered = sorted(self._store.values(), key=lambda h: h.invoice_number)
        return ordered[skip : skip + limit]

    async def count(self) -> int:
        return len(self._store)

    async def get_lines_by_ids(
        self, line_ids: list[UUID]
    ) -> list[InvoiceLineEntity]:
        wanted = set(line_ids)
        result: list[InvoiceLineEntity] = []
        for header in self._store.values():
            result.extend(line for line in header.lines if line.id in wanted)
        return result

    async def exists_by_invoice_number(
        self, invoice_number: str, exclude_id: UUID | None = None
    ) -> bool:
        return any(
            h.invoice_number == invoice_number and h.id != exclude_id
            for h in self._store.values()
        )

    async def exists_by_id(self, header_id: UUID) -> bool:
        return header_id in self._store

    async def exists_for_customer(self, customer_id: UUID) -> bool:
        return any(h.customer_id == customer_id for h in self._store.values())

    async def exists_for_vendor(self, vendor_id: UUID) -> bool:
        return any(h.vendor_id == vendor_id for h in self._store.values())


class FakeVendorRepository:
    """Tracks which vendor ids are considered to exist."""

    def __init__(self) -> None:
        self.existing: set[UUID] = set()

    async def get_by_id(self, vendor_id: UUID):
        return object() if vendor_id in self.existing else None


class FakeCustomerRepository:
    """Tracks which customer ids are considered to exist."""

    def __init__(self) -> None:
        self.existing: set[UUID] = set()

    async def get_by_id(self, customer_id: UUID):
        return object() if customer_id in self.existing else None


class FakeProductRepository:
    """Tracks which product detail ids are considered to exist."""

    def __init__(self) -> None:
        self.existing: set[UUID] = set()

    async def get_detail_by_id(self, detail_id: UUID):
        return object() if detail_id in self.existing else None


class FakeAgreementRepository:
    """Returns active agreements covering a vendor + product detail."""

    def __init__(self) -> None:
        self._agreements: list[AgreementEntity] = []

    def add(self, agreement: AgreementEntity) -> None:
        self._agreements.append(agreement)

    async def find_overlapping_active(
        self,
        vendor_id: UUID,
        product_detail_id: UUID,
        from_date: date,
        to_date: date,
        exclude_id: UUID | None = None,
    ) -> list[AgreementEntity]:
        return [
            a
            for a in self._agreements
            if a.vendor_id == vendor_id
            and a.product_detail_id == product_detail_id
            and a.status == AgreementStatus.Active
            and a.from_date is not None
            and a.to_date is not None
            and a.from_date <= to_date
            and from_date <= a.to_date
        ]


# ─── Fixtures ───


@pytest.fixture
def invoice_repo() -> FakeInvoiceRepository:
    return FakeInvoiceRepository()


@pytest.fixture
def vendor_repo() -> FakeVendorRepository:
    return FakeVendorRepository()


@pytest.fixture
def customer_repo() -> FakeCustomerRepository:
    return FakeCustomerRepository()


@pytest.fixture
def product_repo() -> FakeProductRepository:
    return FakeProductRepository()


@pytest.fixture
def agreement_repo() -> FakeAgreementRepository:
    return FakeAgreementRepository()


@pytest.fixture
def service(
    invoice_repo: FakeInvoiceRepository,
    vendor_repo: FakeVendorRepository,
    customer_repo: FakeCustomerRepository,
    product_repo: FakeProductRepository,
    agreement_repo: FakeAgreementRepository,
) -> InvoiceService:
    return InvoiceService(
        session=None,  # type: ignore[arg-type]
        invoice_repo=invoice_repo,  # type: ignore[arg-type]
        vendor_repo=vendor_repo,  # type: ignore[arg-type]
        customer_repo=customer_repo,  # type: ignore[arg-type]
        product_repo=product_repo,  # type: ignore[arg-type]
        agreement_repo=agreement_repo,  # type: ignore[arg-type]
    )


@pytest.fixture
def actor() -> User:
    return User(id=uuid4(), username="admin", is_active=True)


@pytest.fixture
def vendor_id(vendor_repo: FakeVendorRepository) -> UUID:
    vid = uuid4()
    vendor_repo.existing.add(vid)
    return vid


@pytest.fixture
def customer_id(customer_repo: FakeCustomerRepository) -> UUID:
    cid = uuid4()
    customer_repo.existing.add(cid)
    return cid


@pytest.fixture
def product_detail_id(product_repo: FakeProductRepository) -> UUID:
    pid = uuid4()
    product_repo.existing.add(pid)
    return pid


def _valid_input(
    vendor_id: UUID,
    customer_id: UUID,
    product_detail_id: UUID,
    **overrides: object,
) -> InvoiceCreateInput:
    base: dict[str, object] = {
        "invoice_number": "INV-001",
        "invoice_date": date(2024, 1, 10),
        "vendor_id": vendor_id,
        "customer_id": customer_id,
        "bill_amount_excl_gst": Decimal("100.00"),
        "lines": [InvoiceLineInput(product_detail_id=product_detail_id)],
    }
    base.update(overrides)
    return InvoiceCreateInput(**base)  # type: ignore[arg-type]


# ─── Create: defaults (Req 16.5) ───


async def test_create_applies_defaults(
    service: InvoiceService,
    actor: User,
    vendor_id: UUID,
    customer_id: UUID,
    product_detail_id: UUID,
) -> None:
    created = await service.create_invoice(
        _valid_input(vendor_id, customer_id, product_detail_id), actor
    )
    assert created.amount_deducted == Decimal("0")
    assert created.tds_value == Decimal("0")
    assert created.invoice_status == InvoiceStatus.Open
    assert created.created_by == "admin"
    assert len(created.lines) == 1


async def test_create_persists_lines_linked_to_header(
    service: InvoiceService,
    actor: User,
    vendor_id: UUID,
    customer_id: UUID,
    product_detail_id: UUID,
) -> None:
    created = await service.create_invoice(
        _valid_input(vendor_id, customer_id, product_detail_id), actor
    )
    assert created.lines[0].invoice_header_id == created.id
    assert created.lines[0].product_detail_id == product_detail_id


# ─── Create: uniqueness (Req 16.2) ───


async def test_create_rejects_duplicate_invoice_number(
    service: InvoiceService,
    actor: User,
    vendor_id: UUID,
    customer_id: UUID,
    product_detail_id: UUID,
) -> None:
    await service.create_invoice(
        _valid_input(vendor_id, customer_id, product_detail_id), actor
    )
    with pytest.raises(MasterConflictError):
        await service.create_invoice(
            _valid_input(vendor_id, customer_id, product_detail_id), actor
        )


async def test_duplicate_invoice_number_persists_nothing(
    service: InvoiceService,
    invoice_repo: FakeInvoiceRepository,
    actor: User,
    vendor_id: UUID,
    customer_id: UUID,
    product_detail_id: UUID,
) -> None:
    await service.create_invoice(
        _valid_input(vendor_id, customer_id, product_detail_id), actor
    )
    with pytest.raises(MasterConflictError):
        await service.create_invoice(
            _valid_input(vendor_id, customer_id, product_detail_id), actor
        )
    assert await invoice_repo.count() == 1


# ─── Create: reference existence (Req 16.3, 16.4) ───


async def test_create_rejects_missing_vendor(
    service: InvoiceService,
    actor: User,
    customer_id: UUID,
    product_detail_id: UUID,
) -> None:
    with pytest.raises(MasterValidationError) as exc:
        await service.create_invoice(
            _valid_input(uuid4(), customer_id, product_detail_id), actor
        )
    assert exc.value.field == "vendor_id"


async def test_create_rejects_missing_customer(
    service: InvoiceService,
    actor: User,
    vendor_id: UUID,
    product_detail_id: UUID,
) -> None:
    with pytest.raises(MasterValidationError) as exc:
        await service.create_invoice(
            _valid_input(vendor_id, uuid4(), product_detail_id), actor
        )
    assert exc.value.field == "customer_id"


async def test_create_rejects_missing_product_detail(
    service: InvoiceService,
    actor: User,
    vendor_id: UUID,
    customer_id: UUID,
) -> None:
    with pytest.raises(MasterValidationError) as exc:
        await service.create_invoice(
            _valid_input(vendor_id, customer_id, uuid4()), actor
        )
    assert "product_detail_id" in exc.value.field


async def test_create_missing_reference_persists_nothing(
    service: InvoiceService,
    invoice_repo: FakeInvoiceRepository,
    actor: User,
    customer_id: UUID,
    product_detail_id: UUID,
) -> None:
    with pytest.raises(MasterValidationError):
        await service.create_invoice(
            _valid_input(uuid4(), customer_id, product_detail_id), actor
        )
    assert await invoice_repo.count() == 0


# ─── Create: required-field validation ───


async def test_create_rejects_empty_invoice_number(
    service: InvoiceService,
    actor: User,
    vendor_id: UUID,
    customer_id: UUID,
    product_detail_id: UUID,
) -> None:
    with pytest.raises(MasterValidationError) as exc:
        await service.create_invoice(
            _valid_input(
                vendor_id, customer_id, product_detail_id, invoice_number="  "
            ),
            actor,
        )
    assert exc.value.field == "invoice_number"


async def test_create_rejects_no_lines(
    service: InvoiceService,
    actor: User,
    vendor_id: UUID,
    customer_id: UUID,
) -> None:
    with pytest.raises(MasterValidationError) as exc:
        await service.create_invoice(
            InvoiceCreateInput(
                invoice_number="INV-002",
                invoice_date=date(2024, 1, 10),
                vendor_id=vendor_id,
                customer_id=customer_id,
                bill_amount_excl_gst=Decimal("10"),
                lines=[],
            ),
            actor,
        )
    assert exc.value.field == "lines"


async def test_create_rejects_negative_amount(
    service: InvoiceService,
    actor: User,
    vendor_id: UUID,
    customer_id: UUID,
    product_detail_id: UUID,
) -> None:
    with pytest.raises(MasterValidationError) as exc:
        await service.create_invoice(
            _valid_input(
                vendor_id,
                customer_id,
                product_detail_id,
                bill_amount_excl_gst=Decimal("-1"),
            ),
            actor,
        )
    assert exc.value.field == "bill_amount_excl_gst"


# ─── Create: due-date resolution (Req 16.6, 16.7, 16.8) ───


async def test_due_date_uses_supplied_value(
    service: InvoiceService,
    actor: User,
    vendor_id: UUID,
    customer_id: UUID,
    product_detail_id: UUID,
) -> None:
    supplied = date(2024, 3, 1)
    created = await service.create_invoice(
        _valid_input(
            vendor_id, customer_id, product_detail_id, due_date=supplied
        ),
        actor,
    )
    assert created.due_date == supplied


async def test_due_date_computed_from_agreement_credit_days(
    service: InvoiceService,
    agreement_repo: FakeAgreementRepository,
    actor: User,
    vendor_id: UUID,
    customer_id: UUID,
    product_detail_id: UUID,
) -> None:
    invoice_date = date(2024, 1, 10)
    agreement_repo.add(
        AgreementEntity(
            id=uuid4(),
            vendor_id=vendor_id,
            product_detail_id=product_detail_id,
            from_date=date(2024, 1, 1),
            to_date=date(2024, 12, 31),
            credit_days=30,
            status=AgreementStatus.Active,
        )
    )
    created = await service.create_invoice(
        _valid_input(
            vendor_id,
            customer_id,
            product_detail_id,
            invoice_date=invoice_date,
        ),
        actor,
    )
    assert created.due_date == invoice_date + timedelta(days=30)


async def test_due_date_unset_when_no_agreement(
    service: InvoiceService,
    actor: User,
    vendor_id: UUID,
    customer_id: UUID,
    product_detail_id: UUID,
) -> None:
    created = await service.create_invoice(
        _valid_input(vendor_id, customer_id, product_detail_id), actor
    )
    assert created.due_date is None


async def test_supplied_due_date_overrides_agreement(
    service: InvoiceService,
    agreement_repo: FakeAgreementRepository,
    actor: User,
    vendor_id: UUID,
    customer_id: UUID,
    product_detail_id: UUID,
) -> None:
    agreement_repo.add(
        AgreementEntity(
            id=uuid4(),
            vendor_id=vendor_id,
            product_detail_id=product_detail_id,
            from_date=date(2024, 1, 1),
            to_date=date(2024, 12, 31),
            credit_days=30,
            status=AgreementStatus.Active,
        )
    )
    supplied = date(2024, 2, 2)
    created = await service.create_invoice(
        _valid_input(
            vendor_id, customer_id, product_detail_id, due_date=supplied
        ),
        actor,
    )
    assert created.due_date == supplied


# ─── Read / not-found (Req 17.4) ───


async def test_get_unknown_raises_not_found(service: InvoiceService) -> None:
    with pytest.raises(MasterNotFoundError):
        await service.get_invoice(uuid4())


# ─── Delete cascade (Req 16.9) ───


async def test_delete_removes_header(
    service: InvoiceService,
    invoice_repo: FakeInvoiceRepository,
    actor: User,
    vendor_id: UUID,
    customer_id: UUID,
    product_detail_id: UUID,
) -> None:
    created = await service.create_invoice(
        _valid_input(vendor_id, customer_id, product_detail_id), actor
    )
    await service.delete_invoice(created.id, actor)
    assert await invoice_repo.get_by_id(created.id) is None


async def test_delete_unknown_raises_not_found(
    service: InvoiceService, actor: User
) -> None:
    with pytest.raises(MasterNotFoundError):
        await service.delete_invoice(uuid4(), actor)


# ─── Status lifecycle (Req 17.1, 17.2, 17.4) ───


async def test_record_sap_payment_sets_payment_cleared(
    service: InvoiceService,
    actor: User,
    vendor_id: UUID,
    customer_id: UUID,
    product_detail_id: UUID,
) -> None:
    created = await service.create_invoice(
        _valid_input(vendor_id, customer_id, product_detail_id), actor
    )
    clearing_date = date(2024, 2, 15)
    updated = await service.record_sap_payment(
        SapPaymentInput(
            invoice_id=created.id,
            payment_clearing_date=clearing_date,
            sap_clearing_document_no="SAP-123",
        ),
        actor,
    )
    assert updated.invoice_status == InvoiceStatus.PaymentCleared
    assert updated.payment_clearing_date == clearing_date
    assert updated.sap_clearing_document_no == "SAP-123"


async def test_record_sap_payment_by_invoice_number(
    service: InvoiceService,
    actor: User,
    vendor_id: UUID,
    customer_id: UUID,
    product_detail_id: UUID,
) -> None:
    await service.create_invoice(
        _valid_input(vendor_id, customer_id, product_detail_id), actor
    )
    updated = await service.record_sap_payment(
        SapPaymentInput(
            invoice_number="INV-001",
            payment_clearing_date=date(2024, 2, 15),
            sap_clearing_document_no="SAP-9",
        ),
        actor,
    )
    assert updated.invoice_status == InvoiceStatus.PaymentCleared


async def test_record_sap_payment_unknown_raises_not_found(
    service: InvoiceService, actor: User
) -> None:
    with pytest.raises(MasterNotFoundError):
        await service.record_sap_payment(
            SapPaymentInput(
                invoice_id=uuid4(),
                payment_clearing_date=date(2024, 2, 15),
                sap_clearing_document_no="SAP-1",
            ),
            actor,
        )


async def test_mark_settled_sets_status(
    service: InvoiceService,
    actor: User,
    vendor_id: UUID,
    customer_id: UUID,
    product_detail_id: UUID,
) -> None:
    created = await service.create_invoice(
        _valid_input(vendor_id, customer_id, product_detail_id), actor
    )
    updated = await service.mark_settled(created.id, actor)
    assert updated.invoice_status == InvoiceStatus.Settled


async def test_mark_settled_unknown_raises_not_found(
    service: InvoiceService, actor: User
) -> None:
    with pytest.raises(MasterNotFoundError):
        await service.mark_settled(uuid4(), actor)


# ─── List / pagination ───


async def test_list_returns_slice_and_total(
    service: InvoiceService,
    actor: User,
    vendor_id: UUID,
    customer_id: UUID,
    product_detail_id: UUID,
) -> None:
    for i in range(5):
        await service.create_invoice(
            _valid_input(
                vendor_id,
                customer_id,
                product_detail_id,
                invoice_number=f"INV-{i:03d}",
            ),
            actor,
        )
    items, total = await service.list_invoices(skip=1, limit=2)
    assert total == 5
    assert len(items) == 2
    assert [h.invoice_number for h in items] == ["INV-001", "INV-002"]


# ─── Update (partial header) ───


async def test_update_due_date_overrides_stored(
    service: InvoiceService,
    actor: User,
    vendor_id: UUID,
    customer_id: UUID,
    product_detail_id: UUID,
) -> None:
    created = await service.create_invoice(
        _valid_input(vendor_id, customer_id, product_detail_id), actor
    )
    new_due = date(2024, 5, 5)
    updated = await service.update_invoice(
        created.id, InvoiceUpdateInput(due_date=new_due), actor
    )
    assert updated.due_date == new_due


async def test_update_unknown_raises_not_found(
    service: InvoiceService, actor: User
) -> None:
    with pytest.raises(MasterNotFoundError):
        await service.update_invoice(
            uuid4(), InvoiceUpdateInput(tds_value=Decimal("5")), actor
        )
