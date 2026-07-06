"""
Vendor-Customer Mapping application service.

Orchestrates Mapping business rules — create (with Vendor/Customer existence
checks, From ≤ To validation, and inclusive overlap rejection), read,
dates-only partial update, paginated/combined-filter list, delete, and the
scheduled-expiry entry point — delegating persistence to ``IMappingRepository``
and existence checks to ``IVendorRepository`` / ``ICustomerRepository``.

Design notes / decoupling
--------------------------
Mirroring :class:`VendorService` and :class:`CustomerService`, this service is
**Pydantic-agnostic** so it is not coupled to the API request/response schemas
owned by the controller task (11.3):

* CRUD methods accept primitive arguments / lightweight input dataclasses
  defined in this module (:class:`MappingCreateInput`, :class:`MappingUpdateInput`).
* CRUD methods return the :class:`MappingEntity` domain object.
* ``list_mappings`` returns an ``(items, total)`` tuple.

Per Requirement 14.6 an update changes **only** the validity dates; every other
field — including ``status``, ``vendor_id``, and ``customer_id`` — is left
unchanged. The dates-only update input therefore exposes just the two date
fields, each defaulting to an ``UNSET`` sentinel so "field not supplied" is
distinguished from an explicit value.

List filtering (Req 14.7) supports any combination of ``vendor_id`` and
``customer_id``; for a vendor-agent caller the controller supplies that agent's
own ``vendor_id`` so results stay vendor-scoped (Req 20.4).
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import Final
from uuid import UUID, uuid4

from sqlalchemy.ext.asyncio import AsyncSession

from src.application.exceptions.application_exceptions import (
    MasterConflictError,
    MasterNotFoundError,
    MasterValidationError,
)
from src.domain.entities.masters.mapping import MappingEntity
from src.domain.entities.user import User
from src.domain.enums.masters import MappingStatus
from src.domain.repositories.masters.customer_repository import ICustomerRepository
from src.domain.repositories.masters.mapping_repository import IMappingRepository
from src.domain.repositories.masters.vendor_repository import IVendorRepository


class _UnsetType:
    """Sentinel marking an update field that was not supplied at all.

    Distinct from ``None``; singleton so identity checks are reliable.
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
class MappingCreateInput:
    """Validated-on-the-way-in payload for creating a Mapping.

    ``status`` defaults to ``None`` so the service applies the ``Active`` default
    (Req 14.5) when the caller omits it.
    """

    vendor_id: UUID
    customer_id: UUID
    validity_from: date
    validity_to: date
    status: MappingStatus | None = None


@dataclass(frozen=True)
class MappingUpdateInput:
    """Dates-only partial-update payload (Req 14.6).

    Only the validity dates may change; both default to :data:`UNSET`. Any
    supplied value is applied, and the resulting period is re-validated for
    From ≤ To and overlap. All other fields (including ``status``) are untouched.
    """

    validity_from: date | _UnsetType = UNSET
    validity_to: date | _UnsetType = UNSET


class MappingService:
    """Application service for Vendor-Customer Mapping management."""

    def __init__(
        self,
        session: AsyncSession,
        mapping_repo: IMappingRepository,
        vendor_repo: IVendorRepository,
        customer_repo: ICustomerRepository,
    ) -> None:
        self._session = session
        self._mapping_repo = mapping_repo
        self._vendor_repo = vendor_repo
        self._customer_repo = customer_repo

    # ─── Create ───

    async def create_mapping(
        self, data: MappingCreateInput, actor: User
    ) -> MappingEntity:
        """Validate and persist a new Mapping.

        Rejects unknown Vendor/Customer references (Req 14.2) and a Validity From
        later than Validity To (Req 14.3); rejects a request whose validity
        period (inclusive endpoints) overlaps an existing active Mapping for the
        same Vendor + Customer (Req 14.4); defaults Status to ``Active``
        (Req 14.5). Validation runs before any write, so a rejected request
        persists nothing.
        """
        await self._ensure_vendor_exists(data.vendor_id)
        await self._ensure_customer_exists(data.customer_id)
        self._validate_period(data.validity_from, data.validity_to)
        await self._ensure_no_overlap(
            data.vendor_id,
            data.customer_id,
            data.validity_from,
            data.validity_to,
        )

        mapping = MappingEntity(
            id=uuid4(),
            vendor_id=data.vendor_id,
            customer_id=data.customer_id,
            validity_from=data.validity_from,
            validity_to=data.validity_to,
            status=data.status if data.status is not None else MappingStatus.Active,
            created_by=actor.username,
            modified_by=actor.username,
        )
        return await self._mapping_repo.create(mapping)

    # ─── Read ───

    async def get_mapping(self, mapping_id: UUID) -> MappingEntity:
        """Return a Mapping by ID or raise not-found (Req 14.9)."""
        mapping = await self._mapping_repo.get_by_id(mapping_id)
        if mapping is None:
            raise MasterNotFoundError("Mapping", mapping_id)
        return mapping

    # ─── Update (dates only) ───

    async def update_mapping(
        self, mapping_id: UUID, patch: MappingUpdateInput, actor: User
    ) -> MappingEntity:
        """Apply a dates-only update to an existing Mapping (Req 14.6).

        Only Validity From / Validity To may change; Vendor, Customer, and Status
        are left unchanged. The resulting period is re-validated for From ≤ To
        (Req 14.3) and inclusive overlap against other active Mappings for the
        same Vendor + Customer, excluding this record (Req 14.4). Unknown ID →
        not-found (Req 14.9).
        """
        mapping = await self._mapping_repo.get_by_id(mapping_id)
        if mapping is None:
            raise MasterNotFoundError("Mapping", mapping_id)

        new_from = (
            mapping.validity_from
            if isinstance(patch.validity_from, _UnsetType)
            else patch.validity_from
        )
        new_to = (
            mapping.validity_to
            if isinstance(patch.validity_to, _UnsetType)
            else patch.validity_to
        )

        self._validate_period(new_from, new_to)
        await self._ensure_no_overlap(
            mapping.vendor_id,
            mapping.customer_id,
            new_from,
            new_to,
            exclude_id=mapping.id,
        )

        # Dates only — Status and references stay as they are (Req 14.6).
        mapping.validity_from = new_from
        mapping.validity_to = new_to
        mapping.mark_modified(actor.username)
        return await self._mapping_repo.update(mapping)

    # ─── List (combined filters + pagination) ───

    async def list_mappings(
        self,
        skip: int = 0,
        limit: int = 20,
        vendor_id: UUID | None = None,
        customer_id: UUID | None = None,
    ) -> tuple[list[tuple[MappingEntity, str | None, str | None]], int]:
        """Return a page of Mappings (with vendor/customer names) and the total count."""
        items = await self._mapping_repo.list_mappings_with_names(
            skip=skip,
            limit=limit,
            vendor_id=vendor_id,
            customer_id=customer_id,
        )
        total = await self._mapping_repo.count(
            vendor_id=vendor_id, customer_id=customer_id
        )
        return items, total

    # ─── Delete ───

    async def delete_mapping(self, mapping_id: UUID, actor: User) -> None:
        """Delete a Mapping by ID, or raise not-found for an unknown ID (Req 14.9)."""
        mapping = await self._mapping_repo.get_by_id(mapping_id)
        if mapping is None:
            raise MasterNotFoundError("Mapping", mapping_id)
        await self._mapping_repo.delete(mapping_id)

    # ─── Scheduler entry point ───

    async def expire_due_mappings(self, today: date) -> int:
        """Move active Mappings whose validity has passed to ``Expired``.

        Idempotent service entry point used by the end-of-day scheduler
        (the Celery task wrapper is owned by task 11.4). Mappings whose
        ``validity_to`` is on or after ``today`` are left unchanged; only those
        already past due are expired. Returns the number of Mappings expired.
        """
        due = await self._mapping_repo.list_active_due_for_expiry(today)
        for mapping in due:
            mapping.expire("system")
            await self._mapping_repo.update(mapping)
        return len(due)

    # ─── Private helpers ───

    async def _ensure_vendor_exists(self, vendor_id: UUID) -> None:
        """Reject a Mapping referencing a non-existent Vendor (Req 14.2)."""
        if await self._vendor_repo.get_by_id(vendor_id) is None:
            raise MasterValidationError(
                "vendor_id", f"Vendor '{vendor_id}' does not exist"
            )

    async def _ensure_customer_exists(self, customer_id: UUID) -> None:
        """Reject a Mapping referencing a non-existent Customer (Req 14.2)."""
        if await self._customer_repo.get_by_id(customer_id) is None:
            raise MasterValidationError(
                "customer_id", f"Customer '{customer_id}' does not exist"
            )

    async def _ensure_no_overlap(
        self,
        vendor_id: UUID,
        customer_id: UUID,
        validity_from: date,
        validity_to: date,
        exclude_id: UUID | None = None,
    ) -> None:
        """Reject an active Mapping overlapping an existing one (Req 14.4)."""
        overlapping = await self._mapping_repo.find_overlapping_active(
            vendor_id=vendor_id,
            customer_id=customer_id,
            validity_from=validity_from,
            validity_to=validity_to,
            exclude_id=exclude_id,
        )
        if overlapping:
            raise MasterConflictError(
                "An active Mapping for this Vendor and Customer already overlaps "
                "the requested validity period"
            )

    @staticmethod
    def _validate_period(validity_from: date, validity_to: date) -> None:
        """Validity From must be on or before Validity To (Req 14.3)."""
        if not isinstance(validity_from, date) or not isinstance(validity_to, date):
            raise MasterValidationError(
                "validity_from",
                "Validity From and Validity To are required dates",
            )
        if validity_from > validity_to:
            raise MasterValidationError(
                "validity_from",
                "Validity From must be on or before Validity To",
            )
