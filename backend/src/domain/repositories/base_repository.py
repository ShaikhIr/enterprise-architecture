"""
Base repository interface - defines common CRUD contract.

Shared by code-keyed reference (master) aggregates. Entity-specific ports
extend this and may add optional filter arguments to `list_all` / `count`,
plus their own query methods.
"""

from abc import ABC, abstractmethod
from typing import Generic, TypeVar
from uuid import UUID

from src.domain.entities.base_entity import BaseEntity

TEntity = TypeVar("TEntity", bound=BaseEntity)


class IRepository(ABC, Generic[TEntity]):
    """Abstract CRUD contract for a single aggregate type."""

    @abstractmethod
    async def get_by_id(self, entity_id: UUID) -> TEntity | None:
        """Retrieve a single record by primary key."""
        ...

    @abstractmethod
    async def get_by_code(self, code: str) -> TEntity | None:
        """Retrieve a single record by its unique business code."""
        ...

    @abstractmethod
    async def create(self, entity: TEntity) -> TEntity:
        """Persist a new record."""
        ...

    @abstractmethod
    async def update(self, entity: TEntity) -> TEntity:
        """Update an existing record."""
        ...

    @abstractmethod
    async def delete(self, entity_id: UUID) -> None:
        """Delete a record by primary key."""
        ...

    @abstractmethod
    async def list_all(
        self,
        skip: int = 0,
        limit: int = 100,
        search: str | None = None,
        is_active: bool | None = None,
    ) -> list[TEntity]:
        """List records with pagination, free-text search and active filter."""
        ...

    @abstractmethod
    async def count(
        self,
        search: str | None = None,
        is_active: bool | None = None,
    ) -> int:
        """Count records matching the same criteria as `list_all`."""
        ...

    @abstractmethod
    async def exists_by_code(self, code: str, exclude_id: UUID | None = None) -> bool:
        """Check whether a business code is taken, optionally ignoring one row."""
        ...
