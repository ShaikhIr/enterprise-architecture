"""
Legislation repository interface (Port).
Defines the contract for legislation master persistence.
"""

from abc import abstractmethod
from uuid import UUID

from src.domain.entities.legislation import Legislation
from src.domain.repositories.base_repository import IRepository


class ILegislationRepository(IRepository[Legislation]):
    """Abstract repository for the Legislation master."""

    @abstractmethod
    async def list_all(
        self,
        skip: int = 0,
        limit: int = 100,
        search: str | None = None,
        is_active: bool | None = None,
        country_id: UUID | None = None,
        state_id: UUID | None = None,
        category_of_law_id: UUID | None = None,
    ) -> list[Legislation]:
        """List legislations, optionally narrowed by jurisdiction or category."""
        ...

    @abstractmethod
    async def count(
        self,
        search: str | None = None,
        is_active: bool | None = None,
        country_id: UUID | None = None,
        state_id: UUID | None = None,
        category_of_law_id: UUID | None = None,
    ) -> int:
        """Count legislations matching the same criteria as `list_all`."""
        ...

    @abstractmethod
    async def has_dependents(self, legislation_id: UUID) -> bool:
        """Check whether any rule references this legislation."""
        ...
