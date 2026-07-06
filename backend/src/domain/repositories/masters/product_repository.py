"""
Product Master repository interface (Port).

A single repository covers the merged Product Master entity (the former
two-level hierarchy has been collapsed into one table/entity).
"""

from abc import ABC, abstractmethod
from uuid import UUID

from src.domain.entities.masters.product import ProductMasterEntity


class IProductRepository(ABC):
    """Abstract repository for Product Master persistence."""

    @abstractmethod
    async def create(self, product: ProductMasterEntity) -> ProductMasterEntity:
        """Persist a new Product Master."""
        ...

    @abstractmethod
    async def update(self, product: ProductMasterEntity) -> ProductMasterEntity:
        """Update an existing Product Master."""
        ...

    @abstractmethod
    async def get_by_id(self, product_id: UUID) -> ProductMasterEntity | None:
        """Retrieve a Product Master by its unique identifier."""
        ...

    @abstractmethod
    async def delete(self, product_id: UUID) -> None:
        """Delete a Product Master by ID."""
        ...

    @abstractmethod
    async def list(
        self, skip: int = 0, limit: int = 20
    ) -> list[ProductMasterEntity]:
        """List Product Masters with pagination."""
        ...

    @abstractmethod
    async def count(self) -> int:
        """Count all Product Masters."""
        ...

    @abstractmethod
    async def exists_by_child_code(
        self, child_code: str, exclude_id: UUID | None = None
    ) -> bool:
        """Check whether a Product Master with the given Child Code exists."""
        ...

    @abstractmethod
    async def get_by_child_code(
        self, child_code: str
    ) -> ProductMasterEntity | None:
        """Resolve a Product Master by its Child Code.

        Used by bulk upload and agreement resolution.
        """
        ...

    @abstractmethod
    async def get_by_basic_material_code(
        self, basic_material_code: str
    ) -> ProductMasterEntity | None:
        """Resolve a Product Master by Basic Material Code.

        Used by bulk upload to resolve a product row's parent reference.
        """
        ...
