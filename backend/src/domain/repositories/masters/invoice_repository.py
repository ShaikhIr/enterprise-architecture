"""
Invoice repository interface (Port).

A single repository covers both the Invoice Header and Invoice Line entities,
since they form one two-level aggregate. The domain layer owns this interface;
infrastructure implements it.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from uuid import UUID

from src.domain.entities.masters.invoice import (
    InvoiceHeaderEntity,
    InvoiceLineEntity,
)


class IInvoiceRepository(ABC):
    """Abstract repository for Invoice Header and Invoice Line persistence."""

    @abstractmethod
    async def create(
        self, header: InvoiceHeaderEntity, lines: list[InvoiceLineEntity]
    ) -> InvoiceHeaderEntity:
        """Atomically persist a new Invoice Header together with its lines."""
        ...

    @abstractmethod
    async def get_by_id(self, header_id: UUID) -> InvoiceHeaderEntity | None:
        """Retrieve an Invoice Header (with its lines) by its unique identifier."""
        ...

    @abstractmethod
    async def get_by_invoice_number(
        self, invoice_number: str
    ) -> InvoiceHeaderEntity | None:
        """Retrieve an Invoice Header (with its lines) by its Invoice Number."""
        ...

    @abstractmethod
    async def update(self, header: InvoiceHeaderEntity) -> InvoiceHeaderEntity:
        """Update an existing Invoice Header's own fields (not its lines)."""
        ...

    @abstractmethod
    async def delete(self, header_id: UUID) -> None:
        """Delete an Invoice Header by ID, cascading to its lines."""
        ...

    @abstractmethod
    async def list(
        self, skip: int = 0, limit: int = 20
    ) -> list[InvoiceHeaderEntity]:
        """List Invoice Headers with pagination."""
        ...

    @abstractmethod
    async def count(self) -> int:
        """Count all Invoice Headers."""
        ...

    @abstractmethod
    async def get_lines_by_ids(
        self, line_ids: list[UUID]
    ) -> list[InvoiceLineEntity]:
        """Retrieve Invoice Lines matching the supplied identifiers."""
        ...

    @abstractmethod
    async def exists_by_invoice_number(
        self, invoice_number: str, exclude_id: UUID | None = None
    ) -> bool:
        """Check whether an Invoice Header with the given Invoice Number exists."""
        ...

    @abstractmethod
    async def exists_by_id(self, header_id: UUID) -> bool:
        """Check whether an Invoice Header with the given ID exists."""
        ...

    @abstractmethod
    async def exists_for_customer(self, customer_id: UUID) -> bool:
        """Check whether any Invoice Header references the given Customer."""
        ...

    @abstractmethod
    async def exists_for_vendor(self, vendor_id: UUID) -> bool:
        """Check whether any Invoice Header references the given Vendor."""
        ...
