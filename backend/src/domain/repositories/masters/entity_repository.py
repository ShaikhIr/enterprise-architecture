"""
Entity repository interface (Port).
Defines the contract for Entity master persistence operations.
The domain layer owns this interface; infrastructure implements it.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from uuid import UUID

from src.domain.entities.masters.entity import EntityEntity


class IEntityRepository(ABC):
    """Abstract repository for Entity aggregate persistence."""

    @abstractmethod
    async def get_by_id(self, entity_id: UUID) -> EntityEntity | None:
        """Retrieve an entity by its unique identifier."""
        ...

    @abstractmethod
    async def create(self, entity: EntityEntity) -> EntityEntity:
        """Persist a new entity."""
        ...

    @abstractmethod
    async def update(self, entity: EntityEntity) -> EntityEntity:
        """Update an existing entity."""
        ...

    @abstractmethod
    async def delete(self, entity_id: UUID) -> None:
        """Delete an entity by ID."""
        ...

    @abstractmethod
    async def list(
        self,
        skip: int = 0,
        limit: int = 20,
        search: str | None = None,
        is_active: bool | None = None,
    ) -> tuple[list[EntityEntity], int]:
        """
        List entities with pagination, optional trimmed case-insensitive
        substring search (over entity_name/short_code/company_code) and an
        optional active-status filter.

        Returns a tuple of (page items, total count of matching records).
        """
        ...

    @abstractmethod
    async def list_active(self) -> list[EntityEntity]:
        """List every active entity (used for dropdowns)."""
        ...

    @abstractmethod
    async def get_by_name(self, entity_name: str) -> EntityEntity | None:
        """
        Resolve an entity by Entity Name, compared case-insensitively after
        trimming surrounding whitespace. Returns ``None`` when no match exists.
        Used by HR import entity resolution (Requirement 3.2).
        """
        ...

    @abstractmethod
    async def get_by_company_code(self, company_code: str) -> EntityEntity | None:
        """
        Resolve an entity by Company Code, compared case-insensitively after
        trimming surrounding whitespace. Returns ``None`` when no match exists.
        Used by HR import entity resolution (Requirement 3.2).
        """
        ...

    @abstractmethod
    async def exists_by_name(
        self, entity_name: str, exclude_id: UUID | None = None
    ) -> bool:
        """
        Check whether an entity with the given Entity Name already exists,
        compared case-insensitively after trimming surrounding whitespace.

        ``exclude_id`` excludes a specific record (used during updates).
        """
        ...

    @abstractmethod
    async def exists_by_company_code(
        self, company_code: str, exclude_id: UUID | None = None
    ) -> bool:
        """
        Check whether an entity with the given Company Code already exists,
        compared case-insensitively after trimming surrounding whitespace.

        ``exclude_id`` excludes a specific record (used during updates).
        """
        ...
