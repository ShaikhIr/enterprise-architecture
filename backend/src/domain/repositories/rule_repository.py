"""
Rule repository interface (Port).
Defines the contract for rule master persistence.
"""

from abc import abstractmethod

from src.domain.entities.rule import Rule
from src.domain.repositories.base_repository import IRepository


class IRuleRepository(IRepository[Rule]):
    """Abstract repository for the Rule master."""

    @abstractmethod
    async def list_all(
        self,
        skip: int = 0,
        limit: int = 100,
        search: str | None = None,
        is_active: bool | None = None,
        country_id: int | None = None,
        state_id: int | None = None,
        legislation_id: int | None = None,
    ) -> list[Rule]:
        """List rules, optionally narrowed by jurisdiction or legislation."""
        ...

    @abstractmethod
    async def count(
        self,
        search: str | None = None,
        is_active: bool | None = None,
        country_id: int | None = None,
        state_id: int | None = None,
        legislation_id: int | None = None,
    ) -> int:
        """Count rules matching the same criteria as `list_all`."""
        ...
