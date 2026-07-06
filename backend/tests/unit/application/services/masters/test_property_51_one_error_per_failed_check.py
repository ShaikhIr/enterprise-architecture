# Feature: lacm-masters, Property 51: Each failed check yields one distinct error.
"""Property-based test for Claim Validation error aggregation.

Property 51: Each failed check yields one distinct error.

**Validates: Requirements 18.6**

Requirement 18.6: WHEN an invoice line fails more than one of the Agreement,
Mapping, and Invoice Status checks, THE Claim_Validation_Service SHALL evaluate
all three checks and SHALL return one distinct error for each failed check.

For *any* invoice line that fails ``k`` of the three triangle checks (Agreement,
Mapping, Invoice Status), :meth:`ClaimValidationService.validate_lines` returns
exactly ``k`` distinct errors — one per failed check — and the line is allowed
if and only if ``k == 0``.

The service is exercised end-to-end through lightweight in-memory fakes that
duck-type the repository ports (no mocks), so the property validates the real
per-line aggregation logic. The vendor is kept Active throughout so each of the
three checks is toggled independently via its own lever (an active agreement, an
active mapping, and the invoice status), which lets the test assert a clean
one-error-per-failed-check correspondence.
"""

from __future__ import annotations

import asyncio
from datetime import date
from uuid import UUID, uuid4

from hypothesis import given, settings
from hypothesis import strategies as st

from src.application.services.masters.claim_validation_service import (
    CODE_INVOICE_NOT_CLEARED,
    CODE_INVOICE_SETTLED,
    CODE_NO_ACTIVE_AGREEMENT,
    CODE_NO_ACTIVE_MAPPING,
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


class _FakeInvoiceRepository:
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


class _FakeAgreementRepository:
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


class _FakeMappingRepository:
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


class _FakeVendorRepository:
    def __init__(self) -> None:
        self._vendors: dict[UUID, VendorEntity] = {}

    def add(self, vendor: VendorEntity) -> None:
        self._vendors[vendor.id] = vendor

    async def get_by_id(self, vendor_id: UUID) -> VendorEntity | None:
        return self._vendors.get(vendor_id)


def _build_line(
    *,
    invoice_repo: _FakeInvoiceRepository,
    agreement_repo: _FakeAgreementRepository,
    mapping_repo: _FakeMappingRepository,
    vendor_repo: _FakeVendorRepository,
    agreement_passes: bool,
    mapping_passes: bool,
    invoice_status: InvoiceStatus,
) -> UUID:
    """Wire up one invoice line with each triangle check toggled and return its id."""
    vendor_id = uuid4()
    customer_id = uuid4()
    product_detail_id = uuid4()
    header_id = uuid4()
    line_id = uuid4()

    # Vendor is always Active so the Agreement check is governed solely by the
    # presence of an active agreement (no VENDOR_INACTIVE short-circuit).
    vendor_repo.add(
        VendorEntity(
            id=vendor_id,
            vendor_code="V001",
            vendor_name="Acme",
            vendor_email="acme@example.com",
            status=VendorStatus.Active,
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

    if agreement_passes:
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
    if mapping_passes:
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


# The expected code for each failed check, given how the levers are set.
_AGREEMENT_FAIL_CODE = CODE_NO_ACTIVE_AGREEMENT
_MAPPING_FAIL_CODE = CODE_NO_ACTIVE_MAPPING
_INVOICE_FAIL_CODE = {
    InvoiceStatus.Open: CODE_INVOICE_NOT_CLEARED,
    InvoiceStatus.Settled: CODE_INVOICE_SETTLED,
}


@settings(max_examples=20)
@given(
    agreement_passes=st.booleans(),
    mapping_passes=st.booleans(),
    invoice_status=st.sampled_from(list(InvoiceStatus)),
)
def test_each_failed_check_yields_one_distinct_error(
    agreement_passes: bool,
    mapping_passes: bool,
    invoice_status: InvoiceStatus,
) -> None:
    """Exactly one distinct error per failed triangle check (Req 18.6).

    The three checks are toggled independently. The expected error codes are
    derived directly from the levers, so the test asserts both the *count*
    (one per failed check) and the *identity* (the specific code) of each error,
    plus that ``allowed`` holds iff no check failed.
    """
    invoice_passes = invoice_status == InvoiceStatus.PaymentCleared

    expected_codes: set[str] = set()
    if not agreement_passes:
        expected_codes.add(_AGREEMENT_FAIL_CODE)
    if not mapping_passes:
        expected_codes.add(_MAPPING_FAIL_CODE)
    if not invoice_passes:
        expected_codes.add(_INVOICE_FAIL_CODE[invoice_status])

    async def scenario() -> None:
        invoice_repo = _FakeInvoiceRepository()
        agreement_repo = _FakeAgreementRepository()
        mapping_repo = _FakeMappingRepository()
        vendor_repo = _FakeVendorRepository()
        service = ClaimValidationService(
            session=None,  # type: ignore[arg-type]  # unused by the in-memory ports
            invoice_repo=invoice_repo,  # type: ignore[arg-type]
            agreement_repo=agreement_repo,  # type: ignore[arg-type]
            mapping_repo=mapping_repo,  # type: ignore[arg-type]
            vendor_repo=vendor_repo,  # type: ignore[arg-type]
        )

        line_id = _build_line(
            invoice_repo=invoice_repo,
            agreement_repo=agreement_repo,
            mapping_repo=mapping_repo,
            vendor_repo=vendor_repo,
            agreement_passes=agreement_passes,
            mapping_passes=mapping_passes,
            invoice_status=invoice_status,
        )

        [result] = await service.validate_lines([line_id])

        failed_count = len(expected_codes)

        # One error per failed check: count matches the number of failed checks.
        assert len(result.errors) == failed_count
        # The errors are distinct (no duplicate codes).
        codes = [e.code for e in result.errors]
        assert len(set(codes)) == len(codes)
        # Each failed check is represented by its specific code.
        assert set(codes) == expected_codes
        # Every error refers to the offending line.
        assert all(e.invoice_line_id == line_id for e in result.errors)
        # Allowed iff no check failed.
        assert result.allowed is (failed_count == 0)

    asyncio.run(scenario())
