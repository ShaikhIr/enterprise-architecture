"""
Ports for the login use case.

`ISessionAuthenticator` is what the API and `LoginService` need from whatever checks
credentials and issues tokens (today `AuthManager`). `ILoginAuditor` is the slice of the
audit writer the login use case uses. Both are `Protocol`s, so the existing adapters satisfy
them without inheriting from anything.
"""

from dataclasses import dataclass, field
from typing import Any, Protocol

from src.config.settings import settings


@dataclass
class AuthTokenResponse:
    """
    The outcome of a successful authentication.

    `refresh_token` is None when a token was refreshed inside the reuse grace window: the
    caller already holds the rotated token from the first request, so none is issued.
    """

    access_token: str
    refresh_token: str | None
    token_type: str = "Bearer"
    expires_in: int = 0
    user_id: int | None = field(default=None)
    username: str = ""

    def __post_init__(self) -> None:
        if self.expires_in == 0:
            self.expires_in = settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60


class ISessionAuthenticator(Protocol):
    """Checks credentials and issues, rotates and revokes the token pair."""

    async def login(self, username: str, password: str) -> AuthTokenResponse:
        """Authenticate a username/password pair and start a session."""
        ...

    async def microsoft_login(self, profile: dict[str, Any]) -> AuthTokenResponse:
        """Start a session for a verified Microsoft Graph profile."""
        ...

    async def refresh(self, refresh_token: str) -> AuthTokenResponse:
        """Rotate a refresh token into a new access token (and a new refresh token)."""
        ...

    async def revoke_session(self, refresh_token: str) -> None:
        """End the session a refresh token belongs to. Never raises for a bad token."""
        ...


class ILoginAuditor(Protocol):
    """The audit events the login use case writes."""

    async def log_login(
        self,
        *,
        user_id: int | None,
        username: str,
        success: bool,
        ip_address: str = "",
        user_agent: str = "",
        reason: str = "",
    ) -> None:
        """Record a login attempt, successful or not."""
        ...

    async def log_login_locked(
        self,
        *,
        username: str,
        ip_address: str = "",
        user_agent: str = "",
        reason: str = "",
    ) -> None:
        """Record that repeated failures started a lockout."""
        ...
