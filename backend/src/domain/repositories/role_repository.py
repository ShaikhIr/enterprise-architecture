"""
Role repository interface (Port).
Defines the contract for role persistence, including the role-permission link
that belongs to the Role aggregate.
"""

from abc import ABC, abstractmethod

from src.domain.entities.role import Role


class IRoleRepository(ABC):
    """Abstract repository for the Role aggregate."""

    @abstractmethod
    async def get_by_id(self, role_id: int, *, with_permissions: bool = False) -> Role | None:
        """
        Retrieve a role by identifier.

        `with_permissions` eagerly loads the granted permissions; callers that
        only need the role's own columns can leave it off.
        """
        ...

    @abstractmethod
    async def get_by_code(self, code: str) -> Role | None:
        """Retrieve a role by its unique code."""
        ...

    @abstractmethod
    async def list_active(self, tenant_id: int | None = None) -> list[Role]:
        """
        List active roles with their permissions, ordered by code.

        When `tenant_id` is given, returns that tenant's roles plus global ones.
        """
        ...

    @abstractmethod
    async def list_by_ids(self, role_ids: list[int]) -> list[Role]:
        """Retrieve several roles with their permissions in one query."""
        ...

    @abstractmethod
    async def create(self, role: Role) -> Role:
        """Persist a new role."""
        ...

    @abstractmethod
    async def update(self, role: Role) -> Role:
        """Update an existing role's own columns."""
        ...

    # ─── Role ↔ Permission links ───

    @abstractmethod
    async def is_permission_granted(self, role_id: int, permission_id: int) -> bool:
        """Check whether a permission is already granted to a role."""
        ...

    @abstractmethod
    async def grant_permission(
        self, role_id: int, permission_id: int, granted_by: str
    ) -> None:
        """Link a permission to a role."""
        ...

    @abstractmethod
    async def revoke_permission(self, role_id: int, permission_id: int) -> bool:
        """
        Unlink a permission from a role.

        Returns:
            True if a link existed and was removed, False if there was none.
        """
        ...
