"""
State repository interface (Port).
Defines the contract for state master persistence.
"""

from abc import abstractmethod
from uuid import UUID

from src.domain.entities.state import State
from src.domain.repositories.base_repository import IRepository


class IStateRepository(IRepository[State]):
    """Abstract repository for the State master."""

    @abstractmethod
    async def list_all(
        self,
        skip: int = 0,
        limit: int = 100,
        search: str | None = None,
        is_active: bool | None = None,
        country_id: UUID | None = None,
    ) -> list[State]:
        """List states, optionally narrowed to a single country."""
        ...

    @abstractmethod
    async def count(
        self,
        search: str | None = None,
        is_active: bool | None = None,
        country_id: UUID | None = None,
    ) -> int:
        """Count states matching the same criteria as `list_all`."""
        ...

    @abstractmethod
    async def exists_by_name(
        self, name: str, country_id: UUID, exclude_id: UUID | None = None
    ) -> bool:
        """Check whether a state name is already used within the given country."""
        ...

    @abstractmethod
    async def has_dependents(self, state_id: UUID) -> bool:
        """Check whether any category, legislation or rule references this state."""
        ...
