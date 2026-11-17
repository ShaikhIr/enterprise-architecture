"""
Refresh token repository interface (Port).

Persistence for the server-side record of issued refresh tokens. The domain owns the
contract; infrastructure implements it.
"""

from abc import ABC, abstractmethod
from datetime import datetime

from src.domain.entities.refresh_token import RefreshToken


class IRefreshTokenRepository(ABC):
    """Abstract repository for RefreshToken persistence."""

    @abstractmethod
    async def create(self, token: RefreshToken) -> RefreshToken:
        """Persist a newly issued token and return it with its database id."""
        ...

    @abstractmethod
    async def get_by_jti(self, jti: str) -> RefreshToken | None:
        """Retrieve a token record by its JWT id."""
        ...

    @abstractmethod
    async def mark_used(self, jti: str, used_at: datetime) -> bool:
        """
        Spend a token, atomically.

        Returns True only for the one caller that moved the token from unused to used.
        A token that is already used or revoked (or unknown) returns False, which is how
        two concurrent refreshes of the same token are told apart.
        """
        ...

    @abstractmethod
    async def revoke_family(self, family_id: str, revoked_at: datetime) -> None:
        """Revoke every not-yet-revoked token of one session."""
        ...

    @abstractmethod
    async def delete_expired(self, before: datetime) -> int:
        """Delete tokens that expired before `before`. Returns how many were removed."""
        ...
