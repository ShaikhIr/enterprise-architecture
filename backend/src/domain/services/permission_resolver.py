"""
Permission resolver interface (Port).

Resolving a user's *effective* permissions is a read model, not a repository:
it walks role assignments, then roles, then parent-role inheritance. The
application layer depends on this interface; `PermissionManager` implements it.
"""

from abc import ABC, abstractmethod
from uuid import UUID

from src.domain.entities.role import Permission, PermissionScope


class IPermissionResolver(ABC):
    """Abstract read model for a user's effective permissions."""

    @abstractmethod
    async def get_user_permissions(
        self,
        user_id: UUID,
        tenant_id: UUID | None = None,
        scope: PermissionScope | None = None,
    ) -> list[Permission]:
        """
        Resolve every permission a user effectively holds.

        Deduplicated across roles, optionally filtered to a single scope.
        """
        ...

    @abstractmethod
    async def has_permission(
        self,
        user_id: UUID,
        permission_code: str,
        tenant_id: UUID | None = None,
    ) -> bool:
        """Whether the user holds a specific permission, by code."""
        ...

    @abstractmethod
    async def get_field_permissions(
        self,
        user_id: UUID,
        resource: str,
        tenant_id: UUID | None = None,
    ) -> dict[str, list[str]]:
        """
        Field-level permissions for a resource.

        Returns a mapping of field name to the actions allowed on it, e.g.
        ``{"salary": ["READ"], "email": ["READ", "UPDATE"]}``.
        """
        ...
