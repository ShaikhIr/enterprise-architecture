# Feature: lacm-masters, Property 50: Claim validation is per-line independent.
"""Property-based test for per-line independence of Claim Validation.

Property 50: Claim validation is per-line independent.

**Validates: Requirements 18.5**

Requirement 18.5: WHEN a claim references multiple Invoice Lines, THE
Claim_Validation_Service SHALL evaluate each line independently so that valid
lines proceed while only the failing lines are blocked, rather than rejecting
the whole claim.

For *any* set of invoice lines submitted together, the outcome of each line is
exactly what it would be if that line were validated on its own:

* the batch result preserves the input order one-to-one (including the result
  for every supplied id),
* each line's ``allowed`` flag and the multiset of its error codes are identical
  whether it is validated alongside other lines or by itself, and
* consequently the set of allowed lines in the batch equals exactly the lines
  that individually pass all three triangle checks — valid and blocked lines
  coexist in one result without the whole claim being rejected.

The service (:class:`ClaimValidationService`) is exercised through real
in-memory implementations of its repository ports (not mocks), so the property
validates the service's batching contract through its real evaluation logic.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from datetime import date
from uuid import UUID, uuid4

from hypothesis import given, settings
from hypothesis import strategies as st

from src.application.services.masters.claim_validation_service import (
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


# ─── In-memory ports (duck-typed against the repository ports) ───


class _FakeInvoiceRepository:
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


class _FakeAgreementRepository:
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


class _FakeMappingRepository:
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


class _FakeVendorRepository:
    """Stores vendors by id."""

    def __init__(self) -> None:
        self._vendors: dict[UUID, VendorEntity] = {}

    def add(self, vendor: VendorEntity) -> None:
        self._vendors[vendor.id] = vendor

    async def get_by_id(self, vendor_id: UUID) -> VendorEntity | None:
        return self._vendors.get(vendor_id)


# ─── Smart generator constrained to the per-line scenario space ───


@dataclass(frozen=True)
class _LineSpec:
    """A self-contained description of one invoice line's validation scenario.

    Each field independently selects whether the corresponding triangle check
    will pass or fail, spanning both the generic and the specific (vendor
    inactive, agreement expired, invoice settled) failure paths.
    """

    vendor_status: VendorStatus
    invoice_status: InvoiceStatus
    with_active_agreement: bool
    with_expired_agreement: bool
    with_active_mapping: bool


_line_specs = st.builds(
    _LineSpec,
    vendor_status=st.sampled_from([VendorStatus.Active, VendorStatus.Inactive]),
    invoice_status=st.sampled_from(
        [InvoiceStatus.PaymentCleared, InvoiceStatus.Open, InvoiceStatus.Settled]
    ),
    with_active_agreement=st.booleans(),
    with_expired_agreement=st.booleans(),
    with_active_mapping=st.booleans(),
)


def _build_line(
    spec: _LineSpec,
    *,
    invoice_repo: _FakeInvoiceRepository,
    agreement_repo: _FakeAgreementRepository,
    mapping_repo: _FakeMappingRepository,
    vendor_repo: _FakeVendorRepository,
) -> UUID:
    """Wire up one independent invoice line from ``spec`` and return its id.

    Every line gets its own Vendor, Customer, Product Detail and Invoice Header
    so that lines never share state — this is essential for the independence
    property to be meaningful.
    """
    vendor_id = uuid4()
    customer_id = uuid4()
    product_detail_id = uuid4()
    header_id = uuid4()
    line_id = uuid4()

    vendor_repo.add(
        VendorEntity(
            id=vendor_id,
            vendor_code=f"V-{vendor_id.hex[:8]}",
            vendor_name="Acme",
            vendor_email=f"{vendor_id.hex[:8]}@example.com",
            status=spec.vendor_status,
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
            invoice_number=f"INV-{header_id.hex[:8]}",
            invoice_date=INVOICE_DATE,
            vendor_id=vendor_id,
            customer_id=customer_id,
            invoice_status=spec.invoice_status,
            lines=[line],
        )
    )

    if spec.with_active_agreement:
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
    if spec.with_expired_agreement:
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
    if spec.with_active_mapping:
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


@settings(max_examples=20, deadline=None)
@given(specs=st.lists(_line_specs, min_size=1, max_size=8))
def test_claim_validation_is_per_line_independent(
    specs: list[_LineSpec],
) -> None:
    """Each line's batch outcome equals its standalone outcome, order preserved.

    A set of independent invoice lines is built from the generated specs and
    validated together in one call. For every line the batch result MUST match,
    one-to-one and in order, the result obtained by validating that line on its
    own — the same ``allowed`` flag and the same multiset of error codes. It
    follows that the allowed lines of the batch are exactly the lines that pass
    individually, so valid and blocked lines coexist without the whole claim
    being rejected (Req 18.5).
    """

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

        line_ids = [
            _build_line(
                spec,
                invoice_repo=invoice_repo,
                agreement_repo=agreement_repo,
                mapping_repo=mapping_repo,
                vendor_repo=vendor_repo,
            )
            for spec in specs
        ]

        # Outcome of each line when validated entirely on its own.
        standalone = {}
        for line_id in line_ids:
            [solo] = await service.validate_lines([line_id])
            standalone[line_id] = (solo.allowed, sorted(e.code for e in solo.errors))

        # Outcome of every line when submitted together as one claim.
        batch = await service.validate_lines(line_ids)

        # Order is preserved one-to-one with the submitted ids.
        assert [r.invoice_line_id for r in batch] == line_ids

        # Each line's batch outcome is identical to its standalone outcome.
        for result in batch:
            expected_allowed, expected_codes = standalone[result.invoice_line_id]
            assert result.allowed is expected_allowed
            assert sorted(e.code for e in result.errors) == expected_codes
            # Every error references the line it belongs to.
            assert all(
                e.invoice_line_id == result.invoice_line_id for e in result.errors
            )

        # The allowed lines of the batch are exactly the individually-passing
        # lines: valid and blocked lines coexist, no whole-claim rejection.
        allowed_in_batch = {r.invoice_line_id for r in batch if r.allowed}
        allowed_standalone = {
            line_id for line_id, (ok, _) in standalone.items() if ok
        }
        assert allowed_in_batch == allowed_standalone

    asyncio.run(scenario())
