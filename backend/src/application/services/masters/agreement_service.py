"""
Agreement Master application service.

Orchestrates Agreement business rules — create, read, partial update, paginated
(vendor-scoped) list, renewal, deletion, the daily expiry sweep, and applicable-
commission computation — delegating persistence to ``IAgreementRepository`` and
cross-master existence checks to ``IVendorRepository`` / ``IProductRepository``.

The commission-slab rule (Requirement 12) is delegated to the pure-domain
``Commission_Calculator`` (``src/domain/services/commission_calculator.py``);
the service owns no slab arithmetic itself.

Design notes / decoupling
--------------------------
The design's service contract is expressed in terms of API response schemas
(``AgreementResponse``, ``PaginatedResponse``). Those schema/controller files are
owned by a sibling task (10.3), so to avoid coupling this service to schemas that
may still be in flux, the service is **Pydantic-agnostic**:

* CRUD/renew methods accept primitive arguments / lightweight input dataclasses
  defined in this module.
* CRUD/renew methods return the :class:`AgreementEntity` domain object.
* ``list_agreements`` returns an ``(items, total)`` tuple.
* ``expire_due_agreements`` returns the count of agreements expired.

The controller task adapts these to the API request/response schemas and maps
the requesting vendor agent's own Vendor to the ``vendor_id`` filter to satisfy
the vendor-scoping rule (Req 20.4).

Partial updates use a dedicated ``UNSET`` sentinel so that "field not supplied"
is distinguished from "field explicitly set to null" — the controller populates
:class:`AgreementUpdateInput` from the Pydantic request's ``model_fields_set``.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from typing import Final
from uuid import UUID, uuid4

from sqlalchemy.ext.asyncio import AsyncSession

from src.application.exceptions.application_exceptions import (
    MasterConflictError,
    MasterNotFoundError,
    MasterValidationError,
)
from src.domain.entities.masters.agreement import AgreementEntity
from src.domain.entities.user import User
from src.domain.enums.masters import AgreementStatus, AgreementType
from src.domain.repositories.masters.agreement_repository import IAgreementRepository
from src.domain.repositories.masters.product_repository import IProductRepository
from src.domain.repositories.masters.vendor_repository import IVendorRepository
from src.domain.services.commission_calculator import (
    compute_applicable_commission,
    compute_delay_days,
)

# ─── Percentage bounds (per Requirement 11.5) ───
_MIN_PERCENT: Final[Decimal] = Decimal("0")
_MAX_PERCENT: Final[Decimal] = Decimal("100")

# ─── Agreement document limits (per Requirement 11.9) ───
_MAX_DOCUMENT_BYTES: Final[int] = 10 * 1024 * 1024  # 10 MB
_ALLOWED_DOCUMENT_CONTENT_TYPES: Final[frozenset[str]] = frozenset(
    {
        "application/pdf",
        "image/jpeg",
        "image/jpg",
        "image/png",
    }
)


class _UnsetType:
    """Sentinel marking an update field that was not supplied at all.

    Distinct from ``None``, which represents an explicit request to clear a
    nullable field. Singleton: there is only ever one ``UNSET`` instance.
    """

    _instance: _UnsetType | None = None

    def __new__(cls) -> _UnsetType:
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    def __repr__(self) -> str:  # pragma: no cover - cosmetic
        return "UNSET"

    def __bool__(self) -> bool:  # pragma: no cover - guard against truthiness use
        return False


UNSET: Final[_UnsetType] = _UnsetType()


@dataclass(frozen=True)
class AgreementDocumentInput:
    """Metadata for an uploaded Agreement Document (Req 11.9).

    The service validates the document's ``content_type`` and ``size_bytes``;
    the persisted reference (e.g. an S3 key) is supplied via ``storage_ref`` by
    the controller once the file is stored.
    """

    content_type: str
    size_bytes: int
    storage_ref: str | None = None


@dataclass(frozen=True)
class AgreementCreateInput:
    """Payload for creating an Agreement.

    ``agreement_type`` and ``status`` default to ``None`` so the service applies
    the ``Original`` / ``Active`` defaults (Req 11.8) before field validation.
    """

    vendor_id: UUID | None
    product_detail_id: UUID | None
    from_date: date | None
    to_date: date | None
    slab_in_days: int | None = None
    reduction_percent: Decimal | None = None
    max_commission_percent: Decimal | None = None
    min_commission_percent: Decimal | None = None
    credit_days: int | None = None
    document: AgreementDocumentInput | None = None


@dataclass(frozen=True)
class AgreementUpdateInput:
    """Partial-update payload for an Agreement.

    Each field defaults to :data:`UNSET`; only supplied fields are applied,
    leaving unsupplied fields unchanged.
    """

    vendor_id: UUID | _UnsetType = UNSET
    product_detail_id: UUID | _UnsetType = UNSET
    from_date: date | _UnsetType = UNSET
    to_date: date | _UnsetType = UNSET
    slab_in_days: int | _UnsetType = UNSET
    reduction_percent: Decimal | _UnsetType = UNSET
    max_commission_percent: Decimal | _UnsetType = UNSET
    min_commission_percent: Decimal | _UnsetType = UNSET
    credit_days: int | _UnsetType = UNSET
    document: AgreementDocumentInput | None | _UnsetType = UNSET


@dataclass(frozen=True)
class AgreementRenewalInput:
    """Payload for the renewal Agreement created from a prior Agreement.

    ``vendor_id`` / ``product_detail_id`` default to ``None`` so the service can
    inherit them from the prior Agreement when the caller omits them.
    """

    from_date: date | None
    to_date: date | None
    slab_in_days: int | None = None
    reduction_percent: Decimal | None = None
    max_commission_percent: Decimal | None = None
    min_commission_percent: Decimal | None = None
    credit_days: int | None = None
    vendor_id: UUID | None = None
    product_detail_id: UUID | None = None
    document: AgreementDocumentInput | None = None


class AgreementService:
    """Application service for Agreement Master management."""

    def __init__(
        self,
        session: AsyncSession,
        agreement_repo: IAgreementRepository,
        vendor_repo: IVendorRepository,
        product_repo: IProductRepository,
    ) -> None:
        self._session = session
        self._agreement_repo = agreement_repo
        self._vendor_repo = vendor_repo
        self._product_repo = product_repo

    # ─────────────────────────────── Create ───────────────────────────────

    async def create_agreement(
        self, data: AgreementCreateInput, actor: User
    ) -> AgreementEntity:
        """Validate and persist a new Agreement.

        Defaults Type=``Original`` and Status=``Active`` are conceptually applied
        before field validation (Req 11.8). Enforces Vendor + Product Detail
        existence (Req 11.2), From ≤ To (Req 11.3), Min ≤ Max (Req 11.4),
        percentage ranges 0–100 (Req 11.5), Slab > 0 and Credit Days ≥ 0
        (Req 11.6), and document type/size (Req 11.9). Rejects when the active
        validity period overlaps an existing active Agreement for the same
        Vendor + Product Detail (Req 11.7). Validation runs before any write, so
        a rejected request persists nothing.
        """
        slab = self._coalesce_int(data.slab_in_days, 0)
        reduction = self._coalesce_decimal(data.reduction_percent)
        max_commission = self._coalesce_decimal(data.max_commission_percent)
        min_commission = self._coalesce_decimal(data.min_commission_percent)
        credit_days = self._coalesce_int(data.credit_days, 0)

        vendor_id = await self._validate_vendor(data.vendor_id)
        detail_id = await self._validate_product_detail(data.product_detail_id)
        from_date, to_date = self._validate_period(data.from_date, data.to_date)
        self._validate_commission_bounds(reduction, max_commission, min_commission)
        self._validate_slab_and_credit(slab, credit_days)
        self._validate_document(data.document)

        await self._ensure_no_overlap(vendor_id, detail_id, from_date, to_date)

        agreement = AgreementEntity(
            id=uuid4(),
            vendor_id=vendor_id,
            product_detail_id=detail_id,
            from_date=from_date,
            to_date=to_date,
            slab_in_days=slab,
            reduction_percent=reduction,
            max_commission_percent=max_commission,
            min_commission_percent=min_commission,
            credit_days=credit_days,
            agreement_type=AgreementType.Original,
            prior_agreement_id=None,
            agreement_document_ref=(
                data.document.storage_ref if data.document else None
            ),
            status=AgreementStatus.Active,
            created_by=actor.username,
            modified_by=actor.username,
        )
        return await self._agreement_repo.create(agreement)

    # ──────────────────────────────── Read ────────────────────────────────

    async def get_agreement(self, agreement_id: UUID) -> AgreementEntity:
        """Return an Agreement by ID or raise not-found (Req 11.11)."""
        agreement = await self._agreement_repo.get_by_id(agreement_id)
        if agreement is None:
            raise MasterNotFoundError("Agreement", agreement_id)
        return agreement

    # ─────────────────────────── Update (partial) ─────────────────────────

    async def update_agreement(
        self, agreement_id: UUID, patch: AgreementUpdateInput, actor: User
    ) -> AgreementEntity:
        """Apply a partial update to an existing Agreement.

        Only supplied fields are changed; unsupplied fields are left untouched.
        Re-validates supplied fields (Req 11.2–11.6, 11.9) and re-checks the
        overlap rule against the resulting active period (Req 11.7). Unknown
        ID → not-found (Req 11.11).
        """
        agreement = await self._agreement_repo.get_by_id(agreement_id)
        if agreement is None:
            raise MasterNotFoundError("Agreement", agreement_id)

        if not isinstance(patch.vendor_id, _UnsetType):
            agreement.vendor_id = await self._validate_vendor(patch.vendor_id)

        if not isinstance(patch.product_detail_id, _UnsetType):
            agreement.product_detail_id = await self._validate_product_detail(
                patch.product_detail_id
            )

        if not isinstance(patch.from_date, _UnsetType):
            agreement.from_date = patch.from_date
        if not isinstance(patch.to_date, _UnsetType):
            agreement.to_date = patch.to_date
        # Re-validate the (possibly) changed period as a pair.
        agreement.from_date, agreement.to_date = self._validate_period(
            agreement.from_date, agreement.to_date
        )

        if not isinstance(patch.slab_in_days, _UnsetType):
            agreement.slab_in_days = self._coalesce_int(patch.slab_in_days, 0)
        if not isinstance(patch.reduction_percent, _UnsetType):
            agreement.reduction_percent = self._coalesce_decimal(
                patch.reduction_percent
            )
        if not isinstance(patch.max_commission_percent, _UnsetType):
            agreement.max_commission_percent = self._coalesce_decimal(
                patch.max_commission_percent
            )
        if not isinstance(patch.min_commission_percent, _UnsetType):
            agreement.min_commission_percent = self._coalesce_decimal(
                patch.min_commission_percent
            )
        if not isinstance(patch.credit_days, _UnsetType):
            agreement.credit_days = self._coalesce_int(patch.credit_days, 0)

        # Re-validate the resulting commission/slab/credit values as a whole.
        self._validate_commission_bounds(
            agreement.reduction_percent,
            agreement.max_commission_percent,
            agreement.min_commission_percent,
        )
        self._validate_slab_and_credit(agreement.slab_in_days, agreement.credit_days)

        if not isinstance(patch.document, _UnsetType):
            self._validate_document(patch.document)
            agreement.agreement_document_ref = (
                patch.document.storage_ref if patch.document else None
            )

        # Overlap is only meaningful for an active agreement (Req 11.7).
        if agreement.status == AgreementStatus.Active:
            await self._ensure_no_overlap(
                agreement.vendor_id,
                agreement.product_detail_id,
                agreement.from_date,
                agreement.to_date,
                exclude_id=agreement.id,
            )

        agreement.mark_modified(actor.username)
        return await self._agreement_repo.update(agreement)

    # ──────────────────────────────── List ────────────────────────────────

    async def list_agreements(
        self, skip: int = 0, limit: int = 20, vendor_id: UUID | None = None
    ) -> tuple[list[tuple[AgreementEntity, str | None, str | None, str | None]], int]:
        """Return a page of Agreements (with denormalized names) and the total count.

        Each item is a tuple ``(entity, vendor_name, child_code, product_name)``.
        When ``vendor_id`` is supplied only Agreements belonging to that Vendor
        are returned and counted (Req 11.10).
        """
        items = await self._agreement_repo.list_with_names(
            skip=skip, limit=limit, vendor_id=vendor_id
        )
        total = await self._agreement_repo.count_all(vendor_id=vendor_id)
        return items, total

    # ─────────────────────────────── Renewal ──────────────────────────────

    async def renew_agreement(
        self, agreement_id: UUID, data: AgreementRenewalInput, actor: User
    ) -> AgreementEntity:
        """Renew an existing Agreement atomically.

        Marks the prior Agreement ``Renewed`` (Req 13.1) and creates a new
        Agreement with Type ``Renewal`` whose ``prior_agreement_id`` points to
        the prior Agreement (Req 13.2). Both writes occur within the caller's
        single transaction so they commit or roll back together. Unknown
        ID → not-found (Req 13.6). The renewal Agreement is fully validated like
        a create, inheriting Vendor / Product Detail from the prior Agreement
        when not supplied.
        """
        prior = await self._agreement_repo.get_by_id(agreement_id)
        if prior is None:
            raise MasterNotFoundError("Agreement", agreement_id)

        vendor_id = await self._validate_vendor(
            data.vendor_id if data.vendor_id is not None else prior.vendor_id
        )
        detail_id = await self._validate_product_detail(
            data.product_detail_id
            if data.product_detail_id is not None
            else prior.product_detail_id
        )
        from_date, to_date = self._validate_period(data.from_date, data.to_date)
        slab = self._coalesce_int(data.slab_in_days, 0)
        reduction = self._coalesce_decimal(data.reduction_percent)
        max_commission = self._coalesce_decimal(data.max_commission_percent)
        min_commission = self._coalesce_decimal(data.min_commission_percent)
        credit_days = self._coalesce_int(data.credit_days, 0)
        self._validate_commission_bounds(reduction, max_commission, min_commission)
        self._validate_slab_and_credit(slab, credit_days)
        self._validate_document(data.document)

        # The prior agreement is about to become Renewed (no longer Active), so
        # exclude it from the overlap check against the renewal period.
        await self._ensure_no_overlap(
            vendor_id, detail_id, from_date, to_date, exclude_id=prior.id
        )

        # Mark the prior agreement renewed first (same transaction).
        prior.mark_renewed(actor.username)
        await self._agreement_repo.update(prior)

        renewal = AgreementEntity(
            id=uuid4(),
            vendor_id=vendor_id,
            product_detail_id=detail_id,
            from_date=from_date,
            to_date=to_date,
            slab_in_days=slab,
            reduction_percent=reduction,
            max_commission_percent=max_commission,
            min_commission_percent=min_commission,
            credit_days=credit_days,
            agreement_type=AgreementType.Renewal,
            prior_agreement_id=prior.id,
            agreement_document_ref=(
                data.document.storage_ref if data.document else None
            ),
            status=AgreementStatus.Active,
            created_by=actor.username,
            modified_by=actor.username,
        )
        return await self._agreement_repo.create(renewal)

    # ─────────────────────────────── Delete ───────────────────────────────

    async def delete_agreement(self, agreement_id: UUID, actor: User) -> None:
        """Delete an Agreement by ID.

        Unknown ID → not-found (Req 11.11). Any Renewal Agreement that
        references the deleted Agreement as its prior has its
        ``prior_agreement_id`` nulled by the database ``ON DELETE SET NULL``
        rule (Req 13.3).
        """
        agreement = await self._agreement_repo.get_by_id(agreement_id)
        if agreement is None:
            raise MasterNotFoundError("Agreement", agreement_id)
        await self._agreement_repo.delete(agreement_id)

    # ─────────────────────────── Scheduler entry ──────────────────────────

    async def expire_due_agreements(self, today: date) -> int:
        """Expire every active Agreement past its To Date (Req 13.4).

        Sets Status to ``Expired`` for each active Agreement whose To Date is
        strictly before ``today`` and returns the number of Agreements expired.
        Intended to be invoked by the daily Scheduler job inside a transaction
        with a system audit actor.
        """
        due = await self._agreement_repo.list_due_for_expiry(today)
        for agreement in due:
            agreement.mark_expired("system")
            await self._agreement_repo.update(agreement)
        return len(due)

    # ─────────────────────── Commission computation ───────────────────────

    def compute_applicable_commission(
        self,
        agreement: AgreementEntity,
        due_date: date,
        payment_clearing_date: date,
    ) -> Decimal:
        """Compute the Applicable Commission % for an Agreement and payment.

        Delegates the slab arithmetic to the pure-domain ``Commission_Calculator``
        (Req 12): Delay Days = Payment Clearing Date − Due Date, then the slab
        reduction rule floored at Min Commission %.
        """
        delay_days = compute_delay_days(due_date, payment_clearing_date)
        return compute_applicable_commission(
            delay_days=delay_days,
            slab_in_days=agreement.slab_in_days,
            max_commission=agreement.max_commission_percent,
            min_commission=agreement.min_commission_percent,
            reduction=agreement.reduction_percent,
        )

    # ─────────────────────────── Validation helpers ───────────────────────

    async def _validate_vendor(self, vendor_id: object) -> UUID:
        """Vendor reference: required, valid UUID, and must exist (Req 11.2)."""
        if vendor_id is None:
            raise MasterValidationError(
                "vendor_id", "Vendor reference is required and must not be empty"
            )
        if not isinstance(vendor_id, UUID):
            raise MasterValidationError(
                "vendor_id", "Vendor reference must be a valid identifier"
            )
        if await self._vendor_repo.get_by_id(vendor_id) is None:
            raise MasterValidationError(
                "vendor_id", f"Referenced Vendor '{vendor_id}' does not exist"
            )
        return vendor_id

    async def _validate_product_detail(self, detail_id: object) -> UUID:
        """Product Detail reference: required, valid UUID, must exist (Req 11.2)."""
        if detail_id is None:
            raise MasterValidationError(
                "product_detail_id",
                "Product Detail reference is required and must not be empty",
            )
        if not isinstance(detail_id, UUID):
            raise MasterValidationError(
                "product_detail_id",
                "Product Detail reference must be a valid identifier",
            )
        if await self._product_repo.get_by_id(detail_id) is None:
            raise MasterValidationError(
                "product_detail_id",
                f"Referenced Product Detail '{detail_id}' does not exist",
            )
        return detail_id

    @staticmethod
    def _validate_period(from_date: object, to_date: object) -> tuple[date, date]:
        """From/To Date: required dates with From ≤ To (Req 11.3)."""
        if not isinstance(from_date, date):
            raise MasterValidationError(
                "from_date", "From Date is required and must be a valid date"
            )
        if not isinstance(to_date, date):
            raise MasterValidationError(
                "to_date", "To Date is required and must be a valid date"
            )
        if from_date > to_date:
            raise MasterValidationError(
                "from_date", "From Date must be on or before To Date"
            )
        return from_date, to_date

    @classmethod
    def _validate_commission_bounds(
        cls, reduction: Decimal, max_commission: Decimal, min_commission: Decimal
    ) -> None:
        """Percentages within 0–100 (Req 11.5) and Min ≤ Max (Req 11.4)."""
        cls._validate_percent("reduction_percent", reduction)
        cls._validate_percent("max_commission_percent", max_commission)
        cls._validate_percent("min_commission_percent", min_commission)
        if min_commission > max_commission:
            raise MasterValidationError(
                "min_commission_percent",
                "Min Commission % must not exceed Max Commission %",
            )

    @staticmethod
    def _validate_percent(field_name: str, value: Decimal) -> None:
        """A single percentage must lie within 0–100 inclusive (Req 11.5)."""
        if value < _MIN_PERCENT or value > _MAX_PERCENT:
            raise MasterValidationError(
                field_name, f"{field_name} must be between 0 and 100 inclusive"
            )

    @staticmethod
    def _validate_slab_and_credit(slab_in_days: int, credit_days: int) -> None:
        """Slab > 0 and Credit Days ≥ 0 (Req 11.6)."""
        if slab_in_days <= 0:
            raise MasterValidationError(
                "slab_in_days", "Slab in Days must be greater than 0"
            )
        if credit_days < 0:
            raise MasterValidationError(
                "credit_days", "Credit Days must be greater than or equal to 0"
            )

    @staticmethod
    def _validate_document(document: AgreementDocumentInput | None) -> None:
        """Agreement Document type must be PDF/JPEG/PNG, size ≤ 10 MB (Req 11.9)."""
        if document is None:
            return
        content_type = (document.content_type or "").strip().lower()
        if content_type not in _ALLOWED_DOCUMENT_CONTENT_TYPES:
            raise MasterValidationError(
                "document",
                "Agreement Document must be a PDF, JPEG, or PNG file",
            )
        if document.size_bytes < 0:
            raise MasterValidationError(
                "document", "Agreement Document size is invalid"
            )
        if document.size_bytes > _MAX_DOCUMENT_BYTES:
            raise MasterValidationError(
                "document", "Agreement Document must not exceed 10 MB"
            )

    async def _ensure_no_overlap(
        self,
        vendor_id: UUID,
        product_detail_id: UUID,
        from_date: date,
        to_date: date,
        exclude_id: UUID | None = None,
    ) -> None:
        """Reject when the active period overlaps another active one (Req 11.7)."""
        overlapping = await self._agreement_repo.find_overlapping_active(
            vendor_id=vendor_id,
            product_detail_id=product_detail_id,
            from_date=from_date,
            to_date=to_date,
            exclude_id=exclude_id,
        )
        if overlapping:
            raise MasterConflictError(
                "An active Agreement already covers an overlapping validity "
                "period for this Vendor and Product Detail"
            )

    @staticmethod
    def _coalesce_int(value: int | None, default: int) -> int:
        """Return ``value`` when supplied, otherwise ``default``."""
        return default if value is None else value

    @staticmethod
    def _coalesce_decimal(value: Decimal | None) -> Decimal:
        """Return ``value`` when supplied, otherwise ``Decimal('0')``."""
        return Decimal("0") if value is None else value
