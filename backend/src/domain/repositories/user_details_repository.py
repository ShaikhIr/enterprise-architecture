"""
User details repository interface (Port).
Employee profile data sourced from the Darwin AD service, one row per user.
"""

from abc import ABC, abstractmethod
from uuid import UUID

from src.domain.entities.user_details import UserDetails


class IUserDetailsRepository(ABC):
    """Abstract repository for UserDetails persistence."""

    @abstractmethod
    async def get_by_user_id(self, user_id: UUID) -> UserDetails | None:
        """Retrieve the profile attached to a user, if one exists."""
        ...

    @abstractmethod
    async def get_many_by_user_ids(
        self, user_ids: list[UUID]
    ) -> dict[UUID, UserDetails]:
        """
        Batch-load profiles for several users, keyed by user id.

        Used to decorate a page of users without issuing a query per row.
        """
        ...

    @abstractmethod
    async def create(self, details: UserDetails) -> UserDetails:
        """Persist a new profile row. Fails if `details.user_id` already has one."""
        ...

    @abstractmethod
    async def update(self, details: UserDetails) -> UserDetails:
        """
        Overwrite an existing profile row's fields.

        Raises:
            ValueError: If `details.id` does not match an existing row.
        """
        ...
