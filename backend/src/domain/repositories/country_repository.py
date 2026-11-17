"""
Country repository interface (Port).
Defines the contract for country master persistence.
"""

from abc import abstractmethod

from src.domain.entities.country import Country
from src.domain.repositories.base_repository import IRepository


class ICountryRepository(IRepository[Country]):
    """Abstract repository for the Country master."""

    @abstractmethod
    async def exists_by_name(self, name: str, exclude_id: int | None = None) -> bool:
        """Check whether a country name is already taken."""
        ...

    @abstractmethod
    async def has_dependents(self, country_id: int) -> bool:
        """Check whether any state, legislation or rule references this country."""
        ...
