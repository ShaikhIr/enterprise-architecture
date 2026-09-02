"""
Category of law repository interface (Port).
Defines the contract for category of law master persistence.
"""

from abc import abstractmethod

from src.domain.entities.category_of_law import CategoryOfLaw
from src.domain.repositories.base_repository import IRepository


class ICategoryOfLawRepository(IRepository[CategoryOfLaw]):
    """Abstract repository for the CategoryOfLaw master."""

    @abstractmethod
    async def list_all(
        self,
        skip: int = 0,
        limit: int = 100,
        search: str | None = None,
        is_active: bool | None = None,
        state_id: int | None = None,
    ) -> list[CategoryOfLaw]:
        """List categories, optionally narrowed to a single state."""
        ...

    @abstractmethod
    async def count(
        self,
        search: str | None = None,
        is_active: bool | None = None,
        state_id: int | None = None,
    ) -> int:
        """Count categories matching the same criteria as `list_all`."""
        ...

    @abstractmethod
    async def exists_by_name(
        self, name: str, state_id: int | None, exclude_id: int | None = None
    ) -> bool:
        """Check whether a category name is already used within the state scope."""
        ...

    @abstractmethod
    async def has_dependents(self, category_of_law_id: int) -> bool:
        """Check whether any legislation references this category."""
        ...
