"""
Customer repository interface (Port).
Defines the contract for Customer master persistence operations.
The domain layer owns this interface; infrastructure implements it.
"""

from abc import ABC, abstractmethod
from uuid import UUID

from src.domain.entities.masters.customer import CustomerEntity


class ICustomerRepository(ABC):
    """Abstract repository for Customer aggregate persistence."""

    @abstractmethod
    async def get_by_id(self, customer_id: UUID) -> CustomerEntity | None:
        """Retrieve a customer by their unique identifier."""
        ...

    @abstractmethod
    async def get_by_customer_code(self, customer_code: str) -> CustomerEntity | None:
        """Retrieve a customer by their business Customer Code."""
        ...

    @abstractmethod
    async def create(self, customer: CustomerEntity) -> CustomerEntity:
        """Persist a new customer entity."""
        ...

    @abstractmethod
    async def update(self, customer: CustomerEntity) -> CustomerEntity:
        """Update an existing customer entity."""
        ...

    @abstractmethod
    async def delete(self, customer_id: UUID) -> None:
        """Delete a customer by ID."""
        ...

    @abstractmethod
    async def list_customers(
        self,
        skip: int = 0,
        limit: int = 20,
        customer_code: str | None = None,
        customer_name: str | None = None,
    ) -> list[CustomerEntity]:
        """List customers with pagination and optional filters."""
        ...

    @abstractmethod
    async def count(
        self,
        customer_code: str | None = None,
        customer_name: str | None = None,
    ) -> int:
        """Return the total count of customer records matching the given filters."""
        ...

    @abstractmethod
    async def exists_by_customer_code(self, customer_code: str) -> bool:
        """Check whether a Customer Code is already in use."""
        ...

    @abstractmethod
    async def is_referenced_by_active_mapping(self, customer_id: UUID) -> bool:
        """
        Return True if the customer is referenced by at least one active
        Vendor-Customer Mapping. Used by the delete guard (Req 8.6).
        """
        ...

    @abstractmethod
    async def is_referenced_by_invoice_header(self, customer_id: UUID) -> bool:
        """
        Return True if the customer is referenced by at least one Invoice
        Header. Used by the delete guard (Req 8.6).
        """
        ...
