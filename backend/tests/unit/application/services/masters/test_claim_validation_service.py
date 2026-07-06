"""
Unit tests for :class:`ClaimValidationService` (Claim Validation Triangle).

These exercise the per-line three-check evaluation (active agreement, active
mapping, Payment Cleared status), the specific error codes (vendor-inactive,
agreement-expired, invoice-settled), one-error-per-failed-check aggregation, and
per-line independence — all against lightweight in-memory fakes that duck-type
the repository ports, so the tests validate real service logic.
"""

from __future__ import annotations

from datetime import date
from uuid import UUID, uuid4

import pytest

from src.application.exceptions.application_exceptions import MasterNotFoundError
from src.application.services.masters.claim_validation_service import (
    CODE_AGREEMENT_EXPIRED,
    CODE_INVOICE_NOT_CLEARED,
    CODE_INVOICE_SETTLED,
    CODE_NO_ACTIVE_AGREEMENT,
    CODE_NO_ACTIVE_MAPPING,
    CODE_VENDOR_INACTIVE,
    ClaimValidationService,
)
from src.domain.entities.masters.agreement import AgreementEntity
from src.domain.entities.masters.invoice import (
    InvoiceHeaderEntity,
    InvoiceLineEntity,
)
from src.domain.entities.masters.mapping import MappingEntity
from src.domain.entities.masters.vendor import VendorEntity
from src.domain.enums.masters import (
    AgreementStatus,
    InvoiceStatus,
    MappingStatus,
    VendorStatus,
)

INVOICE_DATE = date(2024, 6, 15)


# ─── In-memory fakes (duck-typed against the repository ports) ───


class FakeInvoiceRepository:
    """Stores invoice headers and exposes their lines by id."""

    def __init__(self) -> None:
        self._headers: dict[UUID, InvoiceHeaderEntity] = {}

    def add_header(self, header: InvoiceHeaderEntity) -> None:
        self._headers[header.id] = header

    async def get_by_id(self, header_id: UUID) -> InvoiceHeaderEntity | None:
        return self._headers.get(header_id)

    async def get_lines_by_ids(
        self, line_ids: list[UUID]
    ) -> list[InvoiceLineEntity]:
        wanted = set(line_ids)
        result: list[InvoiceLineEntity] = []
        for header in self._headers.values():
            result.extend(line for line in header.lines if line.id in wanted)
        return result


class FakeAgreementRepository:
    """Returns active overlapping agreements and detects expired ones."""

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

    async def exists_expired_for_vendor_and_detail(
        self, vendor_id: UUID, product_detail_id: UUID, on_date: date
    ) -> bool:
        return any(
            a.vendor_id == vendor_id
            and a.product_detail_id == product_detail_id
            and a.to_date is not None
            and a.to_date < on_date
            for a in self._agreements
        )


class FakeMappingRepository:
    """Returns active overlapping mappings for a vendor + customer."""

    def __init__(self) -> None:
        self._mappings: list[MappingEntity] = []

    def add(self, mapping: MappingEntity) -> None:
        self._mappings.append(mapping)

    async def find_overlapping_active(
        self,
        vendor_id: UUID,
        customer_id: UUID,
        validity_from: date,
        validity_to: date,
        exclude_id: UUID | None = None,
    ) -> list[MappingEntity]:
        return [
            m
            for m in self._mappings
            if m.vendor_id == vendor_id
            and m.customer_id == customer_id
            and m.status == MappingStatus.Active
            and m.validity_from <= validity_to
            and validity_from <= m.validity_to
        ]


class FakeVendorRepository:
    """Stores vendors by id."""

    def __init__(self) -> None:
        self._vendors: dict[UUID, VendorEntity] = {}

    def add(self, vendor: VendorEntity) -> None:
        self._vendors[vendor.id] = vendor

    async def get_by_id(self, vendor_id: UUID) -> VendorEntity | None:
        return self._vendors.get(vendor_id)


# ─── Fixtures ───


@pytest.fixture
def invoice_repo() -> FakeInvoiceRepository:
    return FakeInvoiceRepository()


@pytest.fixture
def agreement_repo() -> FakeAgreementRepository:
    return FakeAgreementRepository()


@pytest.fixture
def mapping_repo() -> FakeMappingRepository:
    return FakeMappingRepository()


@pytest.fixture
def vendor_repo() -> FakeVendorRepository:
    return FakeVendorRepository()


@pytest.fixture
def service(
    invoice_repo: FakeInvoiceRepository,
    agreement_repo: FakeAgreementRepository,
    mapping_repo: FakeMappingRepository,
    vendor_repo: FakeVendorRepository,
) -> ClaimValidationService:
    return ClaimValidationService(
        session=None,  # type: ignore[arg-type]
        invoice_repo=invoice_repo,  # type: ignore[arg-type]
        agreement_repo=agreement_repo,  # type: ignore[arg-type]
        mapping_repo=mapping_repo,  # type: ignore[arg-type]
        vendor_repo=vendor_repo,  # type: ignore[arg-type]
    )


def _build_scenario(
    *,
    invoice_repo: FakeInvoiceRepository,
    agreement_repo: FakeAgreementRepository,
    mapping_repo: FakeMappingRepository,
    vendor_repo: FakeVendorRepository,
    vendor_status: VendorStatus = VendorStatus.Active,
    invoice_status: InvoiceStatus = InvoiceStatus.PaymentCleared,
    with_active_agreement: bool = True,
    with_expired_agreement: bool = False,
    with_active_mapping: bool = True,
) -> UUID:
    """Wire up one invoice line and return its id."""
    vendor_id = uuid4()
    customer_id = uuid4()
    product_detail_id = uuid4()
    header_id = uuid4()
    line_id = uuid4()

    vendor_repo.add(
        VendorEntity(
            id=vendor_id,
            vendor_code="V001",
            vendor_name="Acme",
            vendor_email="acme@example.com",
            status=vendor_status,
        )
    )

    line = InvoiceLineEntity(
        id=line_id,
        invoice_header_id=header_id,
        product_detail_id=product_detail_id,
    )
    invoice_repo.add_header(
        InvoiceHeaderEntity(
            id=header_id,
            invoice_number="INV-1",
            invoice_date=INVOICE_DATE,
            vendor_id=vendor_id,
            customer_id=customer_id,
            invoice_status=invoice_status,
            lines=[line],
        )
    )

    if with_active_agreement:
        agreement_repo.add(
            AgreementEntity(
                id=uuid4(),
                vendor_id=vendor_id,
                product_detail_id=product_detail_id,
                from_date=date(2024, 1, 1),
                to_date=date(2024, 12, 31),
                status=AgreementStatus.Active,
            )
        )
    if with_expired_agreement:
        agreement_repo.add(
            AgreementEntity(
                id=uuid4(),
                vendor_id=vendor_id,
                product_detail_id=product_detail_id,
                from_date=date(2023, 1, 1),
                to_date=date(2023, 12, 31),
                status=AgreementStatus.Expired,
            )
        )
    if with_active_mapping:
        mapping_repo.add(
            MappingEntity(
                id=uuid4(),
                vendor_id=vendor_id,
                customer_id=customer_id,
                validity_from=date(2024, 1, 1),
                validity_to=date(2024, 12, 31),
                status=MappingStatus.Active,
            )
        )
    return line_id


# ─── All checks pass (Req 18.4) ───


async def test_line_allowed_when_all_checks_pass(
    service: ClaimValidationService,
    invoice_repo: FakeInvoiceRepository,
    agreement_repo: FakeAgreementRepository,
    mapping_repo: FakeMappingRepository,
    vendor_repo: FakeVendorRepository,
) -> None:
    line_id = _build_scenario(
        invoice_repo=invoice_repo,
        agreement_repo=agreement_repo,
        mapping_repo=mapping_repo,
        vendor_repo=vendor_repo,
    )
    [result] = await service.validate_lines([line_id])
    assert result.allowed is True
    assert result.errors == []


# ─── Single-check failures (Req 18.1, 18.2, 18.3) ───


async def test_no_active_agreement_blocks(
    service: ClaimValidationService,
    invoice_repo: FakeInvoiceRepository,
    agreement_repo: FakeAgreementRepository,
    mapping_repo: FakeMappingRepository,
    vendor_repo: FakeVendorRepository,
) -> None:
    line_id = _build_scenario(
        invoice_repo=invoice_repo,
        agreement_repo=agreement_repo,
        mapping_repo=mapping_repo,
        vendor_repo=vendor_repo,
        with_active_agreement=False,
    )
    [result] = await service.validate_lines([line_id])
    assert result.allowed is False
    assert [e.code for e in result.errors] == [CODE_NO_ACTIVE_AGREEMENT]


async def test_no_active_mapping_blocks(
    service: ClaimValidationService,
    invoice_repo: FakeInvoiceRepository,
    agreement_repo: FakeAgreementRepository,
    mapping_repo: FakeMappingRepository,
    vendor_repo: FakeVendorRepository,
) -> None:
    line_id = _build_scenario(
        invoice_repo=invoice_repo,
        agreement_repo=agreement_repo,
        mapping_repo=mapping_repo,
        vendor_repo=vendor_repo,
        with_active_mapping=False,
    )
    [result] = await service.validate_lines([line_id])
    assert result.allowed is False
    assert [e.code for e in result.errors] == [CODE_NO_ACTIVE_MAPPING]


async def test_invoice_not_cleared_blocks(
    service: ClaimValidationService,
    invoice_repo: FakeInvoiceRepository,
    agreement_repo: FakeAgreementRepository,
    mapping_repo: FakeMappingRepository,
    vendor_repo: FakeVendorRepository,
) -> None:
    line_id = _build_scenario(
        invoice_repo=invoice_repo,
        agreement_repo=agreement_repo,
        mapping_repo=mapping_repo,
        vendor_repo=vendor_repo,
        invoice_status=InvoiceStatus.Open,
    )
    [result] = await service.validate_lines([line_id])
    assert result.allowed is False
    assert [e.code for e in result.errors] == [CODE_INVOICE_NOT_CLEARED]


# ─── Specific error codes (Req 7.5, 13.5, 17.3) ───


async def test_vendor_inactive_blocks_with_specific_code(
    service: ClaimValidationService,
    invoice_repo: FakeInvoiceRepository,
    agreement_repo: FakeAgreementRepository,
    mapping_repo: FakeMappingRepository,
    vendor_repo: FakeVendorRepository,
) -> None:
    # Even with an otherwise-valid active agreement, an inactive vendor is
    # rejected outright (Req 7.5).
    line_id = _build_scenario(
        invoice_repo=invoice_repo,
        agreement_repo=agreement_repo,
        mapping_repo=mapping_repo,
        vendor_repo=vendor_repo,
        vendor_status=VendorStatus.Inactive,
    )
    [result] = await service.validate_lines([line_id])
    assert result.allowed is False
    assert CODE_VENDOR_INACTIVE in [e.code for e in result.errors]
    assert CODE_NO_ACTIVE_AGREEMENT not in [e.code for e in result.errors]


async def test_agreement_expired_blocks_with_specific_code(
    service: ClaimValidationService,
    invoice_repo: FakeInvoiceRepository,
    agreement_repo: FakeAgreementRepository,
    mapping_repo: FakeMappingRepository,
    vendor_repo: FakeVendorRepository,
) -> None:
    line_id = _build_scenario(
        invoice_repo=invoice_repo,
        agreement_repo=agreement_repo,
        mapping_repo=mapping_repo,
        vendor_repo=vendor_repo,
        with_active_agreement=False,
        with_expired_agreement=True,
    )
    [result] = await service.validate_lines([line_id])
    assert result.allowed is False
    assert [e.code for e in result.errors] == [CODE_AGREEMENT_EXPIRED]


async def test_invoice_settled_blocks_with_specific_code(
    service: ClaimValidationService,
    invoice_repo: FakeInvoiceRepository,
    agreement_repo: FakeAgreementRepository,
    mapping_repo: FakeMappingRepository,
    vendor_repo: FakeVendorRepository,
) -> None:
    line_id = _build_scenario(
        invoice_repo=invoice_repo,
        agreement_repo=agreement_repo,
        mapping_repo=mapping_repo,
        vendor_repo=vendor_repo,
        invoice_status=InvoiceStatus.Settled,
    )
    [result] = await service.validate_lines([line_id])
    assert result.allowed is False
    assert [e.code for e in result.errors] == [CODE_INVOICE_SETTLED]


# ─── One distinct error per failed check (Req 18.6) ───


async def test_multiple_failures_yield_one_error_each(
    service: ClaimValidationService,
    invoice_repo: FakeInvoiceRepository,
    agreement_repo: FakeAgreementRepository,
    mapping_repo: FakeMappingRepository,
    vendor_repo: FakeVendorRepository,
) -> None:
    line_id = _build_scenario(
        invoice_repo=invoice_repo,
        agreement_repo=agreement_repo,
        mapping_repo=mapping_repo,
        vendor_repo=vendor_repo,
        with_active_agreement=False,
        with_active_mapping=False,
        invoice_status=InvoiceStatus.Open,
    )
    [result] = await service.validate_lines([line_id])
    assert result.allowed is False
    codes = sorted(e.code for e in result.errors)
    assert codes == sorted(
        [
            CODE_NO_ACTIVE_AGREEMENT,
            CODE_NO_ACTIVE_MAPPING,
            CODE_INVOICE_NOT_CLEARED,
        ]
    )
    # Each error refers to the offending line.
    assert all(e.invoice_line_id == line_id for e in result.errors)


# ─── Per-line independence (Req 18.5) ───


async def test_per_line_independence_mixes_allowed_and_blocked(
    service: ClaimValidationService,
    invoice_repo: FakeInvoiceRepository,
    agreement_repo: FakeAgreementRepository,
    mapping_repo: FakeMappingRepository,
    vendor_repo: FakeVendorRepository,
) -> None:
    good_line = _build_scenario(
        invoice_repo=invoice_repo,
        agreement_repo=agreement_repo,
        mapping_repo=mapping_repo,
        vendor_repo=vendor_repo,
    )
    bad_line = _build_scenario(
        invoice_repo=invoice_repo,
        agreement_repo=agreement_repo,
        mapping_repo=mapping_repo,
        vendor_repo=vendor_repo,
        with_active_mapping=False,
    )
    results = await service.validate_lines([good_line, bad_line])
    by_id = {r.invoice_line_id: r for r in results}
    assert by_id[good_line].allowed is True
    assert by_id[bad_line].allowed is False
    # Order is preserved.
    assert [r.invoice_line_id for r in results] == [good_line, bad_line]


# ─── Unknown line ───


async def test_unknown_line_raises_not_found(
    service: ClaimValidationService,
) -> None:
    with pytest.raises(MasterNotFoundError):
        await service.validate_lines([uuid4()])
