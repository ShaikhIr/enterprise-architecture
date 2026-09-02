"""
Role assignment repository interface (Port).
Defines the contract for the user-to-role link.
"""

from abc import ABC, abstractmethod

from src.domain.entities.role import RoleAssignment


class IRoleAssignmentRepository(ABC):
    """Abstract repository for RoleAssignment persistence."""

    @abstractmethod
    async def get_active(self, user_id: int, role_id: int) -> RoleAssignment | None:
        """Find the active assignment linking a user to a role, if any."""
        ...

    @abstractmethod
    async def list_for_user(self, user_id: int) -> list[RoleAssignment]:
        """List every assignment recorded for a user, active or not."""
        ...

    @abstractmethod
    async def list_active_for_user(self, user_id: int) -> list[RoleAssignment]:
        """List only the currently active assignments for a user."""
        ...

    @abstractmethod
    async def list_active_user_ids_for_role(self, role_id: int) -> list[int]:
        """
        Users who hold a role and are able to act on it.

        Excludes revoked assignments and users who are inactive or blocked, so a
        role-based approval level never routes work to an account that cannot log
        in and clear it.
        """
        ...

    @abstractmethod
    async def deactivate_all_for_user(self, user_id: int, modified_by: str) -> int:
        """
        Soft-revoke every active assignment for a user.

        Returns:
            How many assignments were deactivated.
        """
        ...

    @abstractmethod
    async def create(self, assignment: RoleAssignment) -> RoleAssignment:
        """Persist a new role assignment."""
        ...

    @abstractmethod
    async def deactivate(self, assignment_id: int, modified_by: str) -> None:
        """
        Soft-revoke an assignment by clearing its active flag.

        Assignments are never deleted so the history stays auditable.
        """
        ...
