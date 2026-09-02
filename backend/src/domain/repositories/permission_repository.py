"""
Permission repository interface (Port).
Defines the contract for permission definition persistence.
"""

from abc import ABC, abstractmethod

from src.domain.entities.role import Permission


class IPermissionRepository(ABC):
    """Abstract repository for Permission persistence."""

    @abstractmethod
    async def get_by_id(self, permission_id: int) -> Permission | None:
        """Retrieve a permission by its identifier."""
        ...

    @abstractmethod
    async def get_by_code(self, code: str) -> Permission | None:
        """Retrieve a permission by its unique code."""
        ...

    @abstractmethod
    async def list_active(self, scope: str | None = None) -> list[Permission]:
        """
        List active permissions, optionally narrowed to one scope.

        Ordered by scope then resource so the API returns a stable, grouped list.
        """
        ...

    @abstractmethod
    async def create(self, permission: Permission) -> Permission:
        """Persist a new permission definition."""
        ...
