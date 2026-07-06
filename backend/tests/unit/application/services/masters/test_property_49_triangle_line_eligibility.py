# Feature: lacm-masters, Property 49: Claim Validation Triangle decides line eligibility.
"""Property-based test for the Claim Validation Triangle line decision.

Property 49: Claim Validation Triangle decides line eligibility.

**Validates: Requirements 7.5, 13.5, 17.3, 18.1, 18.2, 18.3, 18.4**

*For any* invoice line, the line is allowed if and only if an active Agreement
for its Vendor and Product Detail covers the invoice date (inclusive), an active
Vendor-Customer Mapping for its Vendor and Customer covers the invoice date
(inclusive), and the Invoice Header Status is ``Payment Cleared``; otherwise the
line is blocked. A vendor that is ``Inactive``, an Agreement whose To Date
precedes the invoice date, and an invoice that is ``Settled`` each cause the
line to be blocked with its specific error.

The property drives the real
:meth:`ClaimValidationService.validate_lines` over lightweight in-memory fakes
that duck-type the repository ports (mirroring the example-based suite in
``test_claim_validation_service.py``), so no database is required. For each
randomly generated triangle state (vendor status, agreement population, mapping
population, invoice status, and invoice date) the test computes the expected
decision and the expected specific error code for each failed check independently
and asserts the service agrees.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from datetime import date
from uuid import UUID, uuid4

from hypothesis import given, settings
from hypothesis import strategies as st

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


# ─── In-memory fakes (duck-typed against the repository ports) ───
#
# These mirror the real repository overlap / expiry queries so the service logic
# under test is exercised for real, but without a database.


class FakeInvoiceRepository:
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
    def __init__(self) -> None:
        self._vendors: dict[UUID, VendorEntity] = {}

    def add(self, vendor: VendorEntity) -> None:
        self._vendors[vendor.id] = vendor

    async def get_by_id(self, vendor_id: UUID) -> VendorEntity | None:
        return self._vendors.get(vendor_id)


# ─── Generated triangle state ───

# A bounded date window so generated agreement / mapping validity periods
# straddle the invoice date often, exercising both the covers and not-covers
# branches.
_dates = st.dates(min_value=date(2023, 1, 1), max_value=date(2026, 12, 31))


@st.composite
def _date_range(draw: st.DrawFn) -> tuple[date, date]:
    """An ordered (from, to) date pair with from <= to."""
    a = draw(_dates)
    b = draw(_dates)
    return (a, b) if a <= b else (b, a)


@dataclass
class _AgreementSpec:
    from_date: date
    to_date: date
    status: AgreementStatus


@dataclass
class _MappingSpec:
    validity_from: date
    validity_to: date
    status: MappingStatus


@st.composite
def _agreement_specs(draw: st.DrawFn) -> list[_AgreementSpec]:
    specs: list[_AgreementSpec] = []
    for _ in range(draw(st.integers(min_value=0, max_value=3))):
        from_date, to_date = draw(_date_range())
        status = draw(st.sampled_from(list(AgreementStatus)))
        specs.append(_AgreementSpec(from_date, to_date, status))
    return specs


@st.composite
def _mapping_specs(draw: st.DrawFn) -> list[_MappingSpec]:
    specs: list[_MappingSpec] = []
    for _ in range(draw(st.integers(min_value=0, max_value=3))):
        validity_from, validity_to = draw(_date_range())
        status = draw(st.sampled_from(list(MappingStatus)))
        specs.append(_MappingSpec(validity_from, validity_to, status))
    return specs


def _build_service(
    *,
    vendor_status: VendorStatus,
    invoice_status: InvoiceStatus,
    invoice_date: date,
    agreements: list[_AgreementSpec],
    mappings: list[_MappingSpec],
) -> tuple[ClaimValidationService, UUID]:
    """Wire one invoice line into fresh fakes; return the service and line id."""
    invoice_repo = FakeInvoiceRepository()
    agreement_repo = FakeAgreementRepository()
    mapping_repo = FakeMappingRepository()
    vendor_repo = FakeVendorRepository()

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
            invoice_date=invoice_date,
            vendor_id=vendor_id,
            customer_id=customer_id,
            invoice_status=invoice_status,
            lines=[line],
        )
    )

    for spec in agreements:
        agreement_repo.add(
            AgreementEntity(
                id=uuid4(),
                vendor_id=vendor_id,
                product_detail_id=product_detail_id,
                from_date=spec.from_date,
                to_date=spec.to_date,
                status=spec.status,
            )
        )
    for spec in mappings:
        mapping_repo.add(
            MappingEntity(
                id=uuid4(),
                vendor_id=vendor_id,
                customer_id=customer_id,
                validity_from=spec.validity_from,
                validity_to=spec.validity_to,
                status=spec.status,
            )
        )

    service = ClaimValidationService(
        session=None,  # type: ignore[arg-type]
        invoice_repo=invoice_repo,  # type: ignore[arg-type]
        agreement_repo=agreement_repo,  # type: ignore[arg-type]
        mapping_repo=mapping_repo,  # type: ignore[arg-type]
        vendor_repo=vendor_repo,  # type: ignore[arg-type]
    )
    return service, line_id


def _expected_agreement_code(
    *,
    vendor_status: VendorStatus,
    invoice_date: date,
    agreements: list[_AgreementSpec],
) -> str | None:
    """The specific Agreement / Vendor gate code (Req 7.5, 13.5, 18.1)."""
    if vendor_status == VendorStatus.Inactive:
        return CODE_VENDOR_INACTIVE
    active_covers = any(
        a.status == AgreementStatus.Active
        and a.from_date <= invoice_date <= a.to_date
        for a in agreements
    )
    if active_covers:
        return None
    expired_exists = any(a.to_date < invoice_date for a in agreements)
    return CODE_AGREEMENT_EXPIRED if expired_exists else CODE_NO_ACTIVE_AGREEMENT


def _expected_mapping_code(
    *, invoice_date: date, mappings: list[_MappingSpec]
) -> str | None:
    """The Mapping gate code (Req 18.2)."""
    active_covers = any(
        m.status == MappingStatus.Active
        and m.validity_from <= invoice_date <= m.validity_to
        for m in mappings
    )
    return None if active_covers else CODE_NO_ACTIVE_MAPPING


def _expected_invoice_code(invoice_status: InvoiceStatus) -> str | None:
    """The Invoice status gate code (Req 17.3, 18.3)."""
    if invoice_status == InvoiceStatus.PaymentCleared:
        return None
    if invoice_status == InvoiceStatus.Settled:
        return CODE_INVOICE_SETTLED
    return CODE_INVOICE_NOT_CLEARED


@settings(max_examples=20, deadline=None)
@given(
    vendor_status=st.sampled_from(list(VendorStatus)),
    invoice_status=st.sampled_from(list(InvoiceStatus)),
    invoice_date=_dates,
    agreements=_agreement_specs(),
    mappings=_mapping_specs(),
)
def test_triangle_decides_line_eligibility(
    vendor_status: VendorStatus,
    invoice_status: InvoiceStatus,
    invoice_date: date,
    agreements: list[_AgreementSpec],
    mappings: list[_MappingSpec],
) -> None:
    """allowed iff all three checks pass; each failure carries its specific code."""
    service, line_id = _build_service(
        vendor_status=vendor_status,
        invoice_status=invoice_status,
        invoice_date=invoice_date,
        agreements=agreements,
        mappings=mappings,
    )

    [result] = asyncio.run(service.validate_lines([line_id]))

    expected_codes = {
        code
        for code in (
            _expected_agreement_code(
                vendor_status=vendor_status,
                invoice_date=invoice_date,
                agreements=agreements,
            ),
            _expected_mapping_code(
                invoice_date=invoice_date, mappings=mappings
            ),
            _expected_invoice_code(invoice_status),
        )
        if code is not None
    }

    # A line is allowed exactly when all three checks pass (Req 18.4).
    assert result.allowed is (len(expected_codes) == 0)
    # Each failed check surfaces exactly its specific error code, and every
    # error refers to the offending line.
    assert {e.code for e in result.errors} == expected_codes
    assert all(e.invoice_line_id == line_id for e in result.errors)
