"""Port for the Microsoft (Azure AD) single sign-on provider."""

from typing import Any, Protocol


class ISsoClient(Protocol):
    """What the auth endpoints need from an OAuth2 / OpenID Connect provider."""

    @property
    def is_configured(self) -> bool:
        """Whether the provider has the settings it needs to be used."""
        ...

    def build_authorization_url(self, *, state: str, code_challenge: str) -> tuple[str, str]:
        """The provider URL to send the browser to, and the redirect URI it will return to."""
        ...

    async def exchange_code_for_profile(self, code: str, code_verifier: str) -> dict[str, Any]:
        """Trade an authorization code (and its PKCE verifier) for the user's profile."""
        ...
