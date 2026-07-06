"""
Vendor repository interface (Port).
Defines the contract for Vendor persistence operations.
The domain layer owns this interface; infrastructure implements it.
"""

from abc import ABC, abstractmethod
from uuid import UUID

from src.domain.entities.masters.vendor import VendorEntity


class IVendorRepository(ABC):
    """Abstract repository for Vendor aggregate persistence."""

    @abstractmethod
    async def get_by_id(self, vendor_id: UUID) -> VendorEntity | None:
        """Retrieve a vendor by its unique identifier."""
        ...

    @abstractmethod
    async def get_by_code(self, vendor_code: str) -> VendorEntity | None:
        """Retrieve a vendor by its vendor code."""
        ...

    @abstractmethod
    async def get_by_email(self, vendor_email: str) -> VendorEntity | None:
        """Retrieve a vendor by its email."""
        ...

    @abstractmethod
    async def create(self, vendor: VendorEntity) -> VendorEntity:
        """Persist a new vendor entity."""
        ...

    @abstractmethod
    async def update(self, vendor: VendorEntity) -> VendorEntity:
        """Update an existing vendor entity."""
        ...

    @abstractmethod
    async def delete(self, vendor_id: UUID) -> None:
        """Delete a vendor by ID."""
        ...

    @abstractmethod
    async def list_all(
        self,
        skip: int = 0,
        limit: int = 20,
        vendor_code: str | None = None,
        vendor_name: str | None = None,
        vendor_email: str | None = None,
        city: str | None = None,
        status: str | None = None,
    ) -> list[VendorEntity]:
        """List vendors with pagination and optional filters."""
        ...

    @abstractmethod
    async def count_all(
        self,
        vendor_code: str | None = None,
        vendor_name: str | None = None,
        vendor_email: str | None = None,
        city: str | None = None,
        status: str | None = None,
    ) -> int:
        """Return the total number of vendor records matching the given filters."""
        ...

    @abstractmethod
    async def exists_by_code(self, vendor_code: str) -> bool:
        """Check if a vendor code already exists."""
        ...

    @abstractmethod
    async def exists_by_email(self, vendor_email: str) -> bool:
        """Check if a vendor email already exists."""
        ...
