"""
Azure AD / Microsoft SSO integration client.

Handles:
- Building the OAuth2 authorization URL (login.microsoftonline.com/.../authorize)
- Exchanging an authorization code for tokens at the /token endpoint
- Fetching user profile from Microsoft Graph (/v1.0/me)

Uses httpx for async HTTP calls. No business logic — only Microsoft API interaction.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import logging
import secrets
import urllib.parse
from dataclasses import dataclass
from typing import Any

from src.config.settings import settings

logger = logging.getLogger(__name__)


class AzureSsoError(Exception):
    """Base class for Azure SSO adapter errors."""


class AzureTokenMissingError(AzureSsoError):
    """Token endpoint responded without an access_token."""


class AzureAuthError(AzureSsoError):
    """Microsoft returned an HTTP error status during the auth flow."""

    def __init__(self, detail: str) -> None:
        super().__init__(detail)
        self.detail = detail


class AzureUnavailableError(AzureSsoError):
    """Microsoft identity service could not be reached."""


@dataclass(frozen=True)
class SsoTransaction:
    """
    The per-sign-in secrets: kept by the server side of the browser session, never trusted
    from the callback request.
    """

    state: str
    code_verifier: str

    @property
    def code_challenge(self) -> str:
        """PKCE S256 challenge derived from the verifier (RFC 7636)."""
        digest = hashlib.sha256(self.code_verifier.encode("ascii")).digest()
        return base64.urlsafe_b64encode(digest).rstrip(b"=").decode("ascii")

    def to_cookie_value(self) -> str:
        """Serialise for the HttpOnly cookie. Both parts are URL-safe base64, so `.` is free."""
        return f"{self.state}.{self.code_verifier}"

    @classmethod
    def from_cookie_value(cls, value: str | None) -> SsoTransaction | None:
        """Parse a cookie written by `to_cookie_value`; None when absent or malformed."""
        if not value:
            return None
        state, sep, verifier = value.partition(".")
        if not sep or not state or not verifier:
            return None
        return cls(state=state, code_verifier=verifier)

    @classmethod
    def start(cls) -> SsoTransaction:
        """New random state and PKCE verifier (256 bits each)."""
        return cls(
            state=secrets.token_urlsafe(32),
            code_verifier=secrets.token_urlsafe(48),
        )

    def matches_state(self, presented: str) -> bool:
        """Constant-time comparison of the state the callback presented."""
        return hmac.compare_digest(self.state.encode("utf-8"), presented.encode("utf-8"))


class AzureSsoClient:
    """Client for Azure AD / Microsoft OAuth2 SSO."""

    def __init__(self) -> None:
        self._client_id = settings.AZURE_CLIENT_ID
        self._client_secret = settings.AZURE_CLIENT_SECRET
        self._tenant_id = settings.AZURE_TENANT_ID
        self._redirect_uri = settings.AZURE_REDIRECT_URI or "http://localhost:6769/auth/microsoft/callback"

    @property
    def is_configured(self) -> bool:
        """True when client_id and tenant_id are present."""
        return bool(self._client_id and self._tenant_id)

    @property
    def redirect_uri(self) -> str:
        return self._redirect_uri

    def build_authorization_url(self, *, state: str, code_challenge: str) -> tuple[str, str]:
        """
        Build the Azure AD OAuth2 authorization URL.

        Args:
            state: Unguessable value the browser must bring back unchanged. The caller keeps
                its own copy and rejects the callback if they differ (login CSRF defence).
            code_challenge: PKCE S256 challenge for the verifier the caller keeps, so an
                authorization code stolen in transit cannot be redeemed without it.

        Returns:
            Tuple of (auth_url, redirect_uri)
        """
        params = {
            "client_id": self._client_id,
            "response_type": "code",
            "redirect_uri": self._redirect_uri,
            "response_mode": "query",
            "scope": "openid profile email User.Read",
            "prompt": "select_account",
            "state": state,
            "code_challenge": code_challenge,
            "code_challenge_method": "S256",
        }
        base_url = f"https://login.microsoftonline.com/{self._tenant_id}/oauth2/v2.0/authorize"
        auth_url = base_url + "?" + urllib.parse.urlencode(params)
        return auth_url, self._redirect_uri

    async def exchange_code_for_profile(self, code: str, code_verifier: str) -> dict[str, Any]:
        """
        Exchange an authorization code for tokens and return the Microsoft Graph profile.

        Flow:
        1. POST to Azure /token endpoint with the authorization code
        2. Extract access_token from the response
        3. GET Microsoft Graph /v1.0/me with the access token
        4. Return the user profile dict

        Raises:
            AzureTokenMissingError: Token response lacked an access_token.
            AzureAuthError: Microsoft returned an HTTP error status.
            AzureUnavailableError: Microsoft was unreachable.
        """
        import httpx

        token_url = f"https://login.microsoftonline.com/{self._tenant_id}/oauth2/v2.0/token"
        token_data = {
            "client_id": self._client_id,
            "client_secret": self._client_secret,
            "code": code,
            "code_verifier": code_verifier,
            "redirect_uri": self._redirect_uri,
            "grant_type": "authorization_code",
            "scope": "openid profile email User.Read",
        }

        try:
            async with httpx.AsyncClient(timeout=15) as http_client:
                # Step 1: Exchange code for tokens
                token_resp = await http_client.post(token_url, data=token_data)
                token_resp.raise_for_status()
                token_json = token_resp.json()

                ms_access_token = token_json.get("access_token")
                if not ms_access_token:
                    raise AzureTokenMissingError()

                # Step 2: Fetch user profile from Microsoft Graph
                graph_resp = await http_client.get(
                    "https://graph.microsoft.com/v1.0/me",
                    headers={"Authorization": f"Bearer {ms_access_token}"},
                )
                graph_resp.raise_for_status()
                profile: dict[str, Any] = graph_resp.json()
                return profile

        except AzureTokenMissingError:
            raise
        except httpx.HTTPStatusError as exc:
            # Microsoft's error body can carry tenant and application ids, trace ids and
            # error codes. It goes to the log; the caller (and so the browser) gets a fixed
            # message.
            logger.error(
                "Microsoft authentication failed: status=%s body=%s",
                exc.response.status_code,
                exc.response.text,
            )
            raise AzureAuthError("Microsoft authentication failed") from exc
        except httpx.RequestError as exc:
            logger.error(f"Microsoft unreachable: {exc}")
            raise AzureUnavailableError() from exc
