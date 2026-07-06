"""
Vendor-Customer Mapping repository interface (Port).

Defines the contract for Mapping persistence operations. The domain layer owns
this interface; infrastructure implements it.
"""

from abc import ABC, abstractmethod
from datetime import date
from uuid import UUID

from src.domain.entities.masters.mapping import MappingEntity


class IMappingRepository(ABC):
    """Abstract repository for Vendor-Customer Mapping persistence."""

    @abstractmethod
    async def get_by_id(self, mapping_id: UUID) -> MappingEntity | None:
        """Retrieve a mapping by its unique identifier."""
        ...

    @abstractmethod
    async def create(self, mapping: MappingEntity) -> MappingEntity:
        """Persist a new mapping entity."""
        ...

    @abstractmethod
    async def update(self, mapping: MappingEntity) -> MappingEntity:
        """Update an existing mapping entity."""
        ...

    @abstractmethod
    async def delete(self, mapping_id: UUID) -> None:
        """Delete a mapping by ID."""
        ...

    @abstractmethod
    async def list_mappings(
        self,
        skip: int = 0,
        limit: int = 20,
        vendor_id: UUID | None = None,
        customer_id: UUID | None = None,
    ) -> list[MappingEntity]:
        """
        List mappings with pagination, optionally filtered by vendor and/or
        customer.
        """
        ...

    @abstractmethod
    async def count(
        self,
        vendor_id: UUID | None = None,
        customer_id: UUID | None = None,
    ) -> int:
        """
        Return the total number of mappings matching the optional vendor and/or
        customer filter.
        """
        ...

    @abstractmethod
    async def find_overlapping_active(
        self,
        vendor_id: UUID,
        customer_id: UUID,
        validity_from: date,
        validity_to: date,
        exclude_id: UUID | None = None,
    ) -> list[MappingEntity]:
        """
        Return active mappings for the given Vendor + Customer whose validity
        period overlaps ``[validity_from, validity_to]`` (inclusive).

        Two inclusive periods overlap when
        ``a.validity_from <= b.validity_to AND b.validity_from <= a.validity_to``.
        ``exclude_id`` excludes a given mapping (used when updating that mapping).
        """
        ...

    @abstractmethod
    async def list_active_due_for_expiry(
        self, today: date
    ) -> list[MappingEntity]:
        """
        Return active mappings whose ``validity_to`` is before ``today`` and so
        are due to be moved to ``Expired``.
        """
        ...
