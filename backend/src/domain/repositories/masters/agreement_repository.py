"""
Agreement repository interface (Port).

Defines the contract for Agreement persistence operations, including the
overlap-detection query used to enforce the no-overlapping-active-agreements
rule and the due-for-expiry query used by the daily expiry job. The domain
layer owns this interface; infrastructure implements it.
"""

from abc import ABC, abstractmethod
from datetime import date
from uuid import UUID

from src.domain.entities.masters.agreement import AgreementEntity


class IAgreementRepository(ABC):
    """Abstract repository for Agreement aggregate persistence."""

    @abstractmethod
    async def get_by_id(self, agreement_id: UUID) -> AgreementEntity | None:
        """Retrieve an agreement by its unique identifier."""
        ...

    @abstractmethod
    async def create(self, agreement: AgreementEntity) -> AgreementEntity:
        """Persist a new agreement entity."""
        ...

    @abstractmethod
    async def update(self, agreement: AgreementEntity) -> AgreementEntity:
        """Update an existing agreement entity."""
        ...

    @abstractmethod
    async def delete(self, agreement_id: UUID) -> None:
        """Delete an agreement by ID."""
        ...

    @abstractmethod
    async def list_all(
        self, skip: int = 0, limit: int = 20, vendor_id: UUID | None = None
    ) -> list[AgreementEntity]:
        """List agreements with pagination, optionally filtered by vendor."""
        ...

    @abstractmethod
    async def count_all(self, vendor_id: UUID | None = None) -> int:
        """Count agreements, optionally filtered by vendor."""
        ...

    @abstractmethod
    async def find_overlapping_active(
        self,
        vendor_id: UUID,
        product_master_id: UUID,
        from_date: date,
        to_date: date,
        exclude_id: UUID | None = None,
    ) -> list[AgreementEntity]:
        """
        Return active agreements for the same vendor and product detail whose
        validity period overlaps the supplied period (inclusive of both
        endpoints). When ``exclude_id`` is supplied that agreement is excluded
        from the result, enabling overlap checks during updates.
        """
        ...

    @abstractmethod
    async def list_due_for_expiry(self, today: date) -> list[AgreementEntity]:
        """
        Return active agreements whose To Date is strictly before ``today``,
        i.e. agreements that are past their validity and due to be expired.
        """
        ...

    @abstractmethod
    async def exists_expired_for_vendor_and_detail(
        self, vendor_id: UUID, product_master_id: UUID, on_date: date
    ) -> bool:
        """
        Return ``True`` when an Agreement for the given Vendor and Product Detail
        has a To Date strictly earlier than ``on_date`` (any status).

        Used by the Claim Validation Triangle to distinguish an *expired*
        agreement (a claim whose invoice date falls after an agreement's To
        Date, Req 13.5) from the case where no agreement was ever defined for
        the Vendor + Product Detail.
        """
        ...
