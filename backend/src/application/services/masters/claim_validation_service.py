"""
Claim Validation Triangle application service.

Evaluates each submitted Invoice Line against the three-check "triangle" that
governs commission-claim eligibility:

1. **Agreement** — an *active* Agreement for the line's Vendor and Product
   Detail whose validity period (From Date through To Date, inclusive) covers
   the invoice date must exist (Req 18.1).
2. **Mapping** — an *active* Vendor–Customer Mapping for the line's Vendor and
   Customer whose validity period (Validity From through Validity To,
   inclusive) covers the invoice date must exist (Req 18.2).
3. **Invoice status** — the line's Invoice Header Status must be
   ``Payment Cleared`` (Req 18.3).

A line is allowed only when all three checks pass (Req 18.4). Each line is
evaluated independently and all three checks are always evaluated, so a line
that fails more than one check yields one distinct error per failed check
(Req 18.6) and valid lines proceed alongside blocked ones without rejecting the
whole claim (Req 18.5).

Beyond the three generic failure codes the service surfaces three *specific*
codes that refine a failed check for clearer reporting:

* ``VENDOR_INACTIVE`` — the line's Vendor is ``Inactive``; an inactive vendor's
  claims are rejected outright (Req 7.5). This refines the Agreement check: an
  inactive vendor can never satisfy it.
* ``AGREEMENT_EXPIRED`` — no active agreement covers the invoice date *and* an
  agreement for the Vendor + Product Detail has a To Date earlier than the
  invoice date, i.e. the invoice date falls after an agreement's validity
  (Req 13.5).
* ``INVOICE_SETTLED`` — the Invoice Header Status is ``Settled``; a settled
  invoice cannot be reused in a new claim (Req 17.3). This refines the Invoice
  status check.

Design notes / decoupling
--------------------------
Mirroring the sibling master services, this service is **Pydantic-agnostic** so
it is not coupled to the API response schemas owned by the controller task
(13.2). ``validate_lines`` returns the lightweight :class:`LineValidationResult`
dataclasses defined in this module; the controller adapts them to the API
``LineValidationResult`` / ``LineValidationError`` response schemas.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from src.application.exceptions.application_exceptions import MasterNotFoundError
from src.domain.entities.masters.invoice import (
    InvoiceHeaderEntity,
    InvoiceLineEntity,
)
from src.domain.enums.masters import InvoiceStatus, VendorStatus
from src.domain.repositories.masters.agreement_repository import (
    IAgreementRepository,
)
from src.domain.repositories.masters.invoice_repository import IInvoiceRepository
from src.domain.repositories.masters.mapping_repository import IMappingRepository
from src.domain.repositories.masters.vendor_repository import IVendorRepository


# ─── Error codes (see module docstring) ───
CODE_NO_ACTIVE_AGREEMENT = "NO_ACTIVE_AGREEMENT"
CODE_NO_ACTIVE_MAPPING = "NO_ACTIVE_MAPPING"
CODE_INVOICE_NOT_CLEARED = "INVOICE_NOT_CLEARED"
CODE_AGREEMENT_EXPIRED = "AGREEMENT_EXPIRED"
CODE_INVOICE_SETTLED = "INVOICE_SETTLED"
CODE_VENDOR_INACTIVE = "VENDOR_INACTIVE"


@dataclass(frozen=True)
class LineValidationError:
    """A single failed-check error for one invoice line."""

    invoice_line_id: UUID
    code: str
    message: str


@dataclass
class LineValidationResult:
    """The eligibility outcome for one invoice line.

    ``allowed`` is ``True`` only when ``errors`` is empty, i.e. all three checks
    passed.
    """

    invoice_line_id: UUID
    allowed: bool
    errors: list[LineValidationError] = field(default_factory=list)


class ClaimValidationService:
    """Application service implementing the Claim Validation Triangle."""

    def __init__(
        self,
        session: AsyncSession,
        invoice_repo: IInvoiceRepository,
        agreement_repo: IAgreementRepository,
        mapping_repo: IMappingRepository,
        vendor_repo: IVendorRepository,
    ) -> None:
        self._session = session
        self._invoice_repo = invoice_repo
        self._agreement_repo = agreement_repo
        self._mapping_repo = mapping_repo
        self._vendor_repo = vendor_repo

    async def validate_lines(
        self, invoice_line_ids: list[UUID]
    ) -> list[LineValidationResult]:
        """Validate each invoice line independently against the triangle.

        Returns one :class:`LineValidationResult` per supplied id, preserving the
        input order (including duplicate ids). Every line is evaluated through
        all three checks; a line is allowed only when all pass (Req 18.4) and
        otherwise carries one distinct error per failed check (Req 18.6). Valid
        and blocked lines coexist in the result without rejecting the whole claim
        (Req 18.5).

        An unknown invoice line id raises :class:`MasterNotFoundError`: the lines
        submitted for a claim are expected to reference existing invoice lines.
        """
        lines = await self._invoice_repo.get_lines_by_ids(
            self._distinct_preserving_order(invoice_line_ids)
        )
        line_by_id = {line.id: line for line in lines}

        # Cache headers so multiple lines on the same invoice resolve once.
        header_cache: dict[UUID, InvoiceHeaderEntity] = {}

        results: list[LineValidationResult] = []
        for line_id in invoice_line_ids:
            line = line_by_id.get(line_id)
            if line is None:
                raise MasterNotFoundError("Invoice Line", line_id)
            header = await self._resolve_header(line, header_cache)
            results.append(await self._validate_one(line, header))
        return results

    # ─── Per-line evaluation ───

    async def _validate_one(
        self, line: InvoiceLineEntity, header: InvoiceHeaderEntity
    ) -> LineValidationResult:
        """Run all three checks for a single line and aggregate the errors."""
        errors: list[LineValidationError] = []

        agreement_error = await self._check_agreement(line, header)
        if agreement_error is not None:
            errors.append(agreement_error)

        mapping_error = await self._check_mapping(line, header)
        if mapping_error is not None:
            errors.append(mapping_error)

        invoice_error = self._check_invoice_status(line, header)
        if invoice_error is not None:
            errors.append(invoice_error)

        return LineValidationResult(
            invoice_line_id=line.id,
            allowed=not errors,
            errors=errors,
        )

    async def _check_agreement(
        self, line: InvoiceLineEntity, header: InvoiceHeaderEntity
    ) -> LineValidationError | None:
        """Agreement / Vendor gate (Req 18.1, 13.5, 7.5).

        An inactive vendor fails this check outright with ``VENDOR_INACTIVE``
        regardless of any agreement (Req 7.5). Otherwise the check passes only
        when an active agreement covers the invoice date; failure is reported as
        ``AGREEMENT_EXPIRED`` when an agreement for the Vendor + Product Detail
        has lapsed before the invoice date (Req 13.5), else
        ``NO_ACTIVE_AGREEMENT`` (Req 18.1).
        """
        vendor = await self._vendor_repo.get_by_id(header.vendor_id)
        if vendor is not None and vendor.status == VendorStatus.Inactive:
            return LineValidationError(
                invoice_line_id=line.id,
                code=CODE_VENDOR_INACTIVE,
                message="The vendor is inactive and cannot submit claims",
            )

        active = await self._agreement_repo.find_overlapping_active(
            vendor_id=header.vendor_id,
            product_master_id=line.product_master_id,
            from_date=header.invoice_date,
            to_date=header.invoice_date,
        )
        if active:
            return None

        expired = await self._agreement_repo.exists_expired_for_vendor_and_detail(
            vendor_id=header.vendor_id,
            product_master_id=line.product_master_id,
            on_date=header.invoice_date,
        )
        if expired:
            return LineValidationError(
                invoice_line_id=line.id,
                code=CODE_AGREEMENT_EXPIRED,
                message="The agreement has expired for the invoice date",
            )
        return LineValidationError(
            invoice_line_id=line.id,
            code=CODE_NO_ACTIVE_AGREEMENT,
            message="No active agreement covers the invoice date",
        )

    async def _check_mapping(
        self, line: InvoiceLineEntity, header: InvoiceHeaderEntity
    ) -> LineValidationError | None:
        """Vendor–Customer Mapping gate (Req 18.2).

        Passes only when an active mapping for the Vendor + Customer covers the
        invoice date; otherwise reports ``NO_ACTIVE_MAPPING``.
        """
        active = await self._mapping_repo.find_overlapping_active(
            vendor_id=header.vendor_id,
            customer_id=header.customer_id,
            validity_from=header.invoice_date,
            validity_to=header.invoice_date,
        )
        if active:
            return None
        return LineValidationError(
            invoice_line_id=line.id,
            code=CODE_NO_ACTIVE_MAPPING,
            message="No active mapping covers the invoice date",
        )

    @staticmethod
    def _check_invoice_status(
        line: InvoiceLineEntity, header: InvoiceHeaderEntity
    ) -> LineValidationError | None:
        """Invoice status gate (Req 18.3, 17.3).

        Passes only when the Invoice Header Status is ``Payment Cleared``; a
        ``Settled`` invoice fails with the specific ``INVOICE_SETTLED`` code
        (Req 17.3), any other non-cleared status with ``INVOICE_NOT_CLEARED``.
        """
        if header.invoice_status == InvoiceStatus.PaymentCleared:
            return None
        if header.invoice_status == InvoiceStatus.Settled:
            return LineValidationError(
                invoice_line_id=line.id,
                code=CODE_INVOICE_SETTLED,
                message="The invoice is already settled",
            )
        return LineValidationError(
            invoice_line_id=line.id,
            code=CODE_INVOICE_NOT_CLEARED,
            message="The invoice is not eligible for claim",
        )

    # ─── Helpers ───

    async def _resolve_header(
        self,
        line: InvoiceLineEntity,
        header_cache: dict[UUID, InvoiceHeaderEntity],
    ) -> InvoiceHeaderEntity:
        """Resolve (and cache) the Invoice Header owning ``line``."""
        header_id = line.invoice_header_id
        if header_id is None:
            raise MasterNotFoundError("Invoice Header", header_id)
        cached = header_cache.get(header_id)
        if cached is not None:
            return cached
        header = await self._invoice_repo.get_by_id(header_id)
        if header is None:
            raise MasterNotFoundError("Invoice Header", header_id)
        header_cache[header_id] = header
        return header

    @staticmethod
    def _distinct_preserving_order(ids: list[UUID]) -> list[UUID]:
        """Return the unique ids in first-seen order (for the batch fetch)."""
        seen: set[UUID] = set()
        unique: list[UUID] = []
        for line_id in ids:
            if line_id not in seen:
                seen.add(line_id)
                unique.append(line_id)
        return unique
