"""
Authentication Application Service.
Orchestrates login, logout, Microsoft SSO, and audit trail logic.
Controllers delegate here; this layer calls repositories and infrastructure.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from src.config.settings import settings
from src.domain.entities.user import User
from src.domain.repositories.user_repository import IUserRepository
from src.infrastructure.security.audit_service import AuditService
from src.infrastructure.security.auth_manager import (
    AuthManager,
    AuthenticationError,
    InvalidCredentialsError,
    UserBlockedError,
    UserInactiveError,
)
from src.infrastructure.security.jwt_provider import JWTProvider

logger = logging.getLogger(__name__)


@dataclass
class TokenResult:
    """DTO for authentication token responses."""

    access_token: str
    refresh_token: str
    token_type: str = "Bearer"
    expires_in: int = 0


class AuthService:
    """
    Application service for authentication operations.

    Responsibilities:
    - Orchestrate login/logout flows with audit logging
    - Handle Microsoft SSO code exchange and user resolution
    - Issue JWT token pairs
    """

    def __init__(
        self,
        session: AsyncSession,
        user_repo: IUserRepository,
        auth_manager: AuthManager,
        jwt_provider: JWTProvider,
    ) -> None:
        self._session = session
        self._user_repo = user_repo
        self._auth_manager = auth_manager
        self._jwt_provider = jwt_provider

    # ─── Login ───

    async def login(
        self,
        username: str,
        password: str,
        ip_address: str = "",
        user_agent: str = "",
    ) -> TokenResult:
        """
        Authenticate user with credentials and log the event.

        Raises:
            InvalidCredentialsError: Wrong username/password.
            UserInactiveError: Account is deactivated.
            UserBlockedError: Account is blocked.
        """
        audit = AuditService(self._session)

        try:
            result = await self._auth_manager.login(
                username=username,
                password=password,
            )
        except (InvalidCredentialsError, UserInactiveError, UserBlockedError) as e:
            reason = type(e).__name__.replace("Error", "").replace("Invalid", "Invalid ")
            await audit.log_login(
                user_id=None,
                username=username,
                success=False,
                ip_address=ip_address,
                user_agent=user_agent,
                reason=reason,
            )
            raise

        # Log successful login
        user = await self._user_repo.get_by_username(username)
        if user:
            await audit.log_login(
                user_id=user.id,
                username=user.username,
                success=True,
                ip_address=ip_address,
                user_agent=user_agent,
            )

        return TokenResult(
            access_token=result.access_token,
            refresh_token=result.refresh_token,
            token_type=result.token_type,
            expires_in=result.expires_in,
        )

    # ─── Logout ───

    async def logout(
        self,
        current_user: User,
        ip_address: str = "",
        user_agent: str = "",
    ) -> None:
        """Record logout event in audit trail."""
        audit = AuditService(self._session)
        await audit.log(
            actor_id=current_user.id,
            actor_username=current_user.username,
            action="LOGOUT",
            resource_type="Authentication",
            resource_id=current_user.username,
            ip_address=ip_address,
            user_agent=user_agent,
        )

    # ─── Refresh Token ───

    async def refresh(self, refresh_token: str) -> TokenResult:
        """
        Exchange a valid refresh token for a new token pair.

        Raises:
            AuthenticationError: Invalid or expired refresh token.
        """
        result = await self._auth_manager.refresh(refresh_token=refresh_token)
        return TokenResult(
            access_token=result.access_token,
            refresh_token=result.refresh_token,
            token_type=result.token_type,
            expires_in=result.expires_in,
        )

    # ─── Microsoft SSO ───

    async def microsoft_login_url(self) -> dict[str, str]:
        """
        Get the Azure AD authorization URL.

        Raises:
            ValueError: If Azure SSO is not configured.
        """
        from src.infrastructure.external.azure_sso import AzureSsoClient

        client = AzureSsoClient()
        if not client.is_configured:
            raise ValueError("Microsoft SSO is not configured on this server")

        auth_url, redirect_uri = client.build_authorization_url()
        return {"auth_url": auth_url, "redirect_uri": redirect_uri}

    async def microsoft_callback(self, code: str) -> TokenResult:
        """
        Exchange Microsoft authorization code for application JWT pair.

        Flow:
        1. Exchange code for Microsoft access_token via AzureSsoClient
        2. Fetch Graph profile (UPN, email, employeeId, name)
        3. Resolve local user by multiple fallback strategies
        4. Validate user is active/not blocked
        5. Issue application JWT pair

        Raises:
            ValueError: Missing code, exchange failure, user not found, or account issues.
        """
        from src.infrastructure.external.azure_sso import (
            AzureAuthError,
            AzureSsoClient,
            AzureTokenMissingError,
            AzureUnavailableError,
        )

        client = AzureSsoClient()
        if not client.is_configured:
            raise ValueError("Microsoft SSO is not configured on this server")

        if not code.strip():
            raise ValueError("Authorization code is required")

        # Exchange code for Microsoft tokens + Graph profile
        try:
            ms_user = await client.exchange_code_for_profile(code)
        except AzureTokenMissingError:
            raise ValueError("Failed to obtain access token from Microsoft")
        except AzureAuthError as exc:
            raise ValueError(f"Microsoft authentication failed: {exc.detail}")
        except AzureUnavailableError:
            raise ValueError("Could not reach Microsoft authentication service")

        # Resolve local user
        user = await self._resolve_microsoft_user(ms_user)

        # Validate user state
        if not user.is_active:
            raise ValueError("User account is inactive")
        if user.is_blocked:
            raise ValueError("User account is blocked")

        # Issue application JWT pair
        access_token = self._jwt_provider.create_access_token(user.username, user.id)
        refresh_token = self._jwt_provider.create_refresh_token(user.username, user.id)

        return TokenResult(
            access_token=access_token,
            refresh_token=refresh_token,
            token_type="Bearer",
            expires_in=settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60,
        )

    # ─── Private Helpers ───

    async def _resolve_microsoft_user(self, ms_user: dict[str, Any]) -> User:
        """
        Resolve a local user from Microsoft Graph profile using multiple strategies.

        Strategy order:
        1. Match by email (userPrincipalName or mail) as username
        2. Match by email in user_details table
        3. Match by employeeId as username
        4. Match by email prefix (part before @) as username

        Raises:
            ValueError: If no matching user is found.
        """
        upn = ms_user.get("userPrincipalName") or ms_user.get("mail") or ""
        email = (ms_user.get("mail") or upn or "").lower().strip()

        logger.info(
            "[SSO] Microsoft Graph profile: mail=%s, upn=%s, displayName=%s, employeeId=%s",
            ms_user.get("mail"),
            ms_user.get("userPrincipalName"),
            ms_user.get("displayName"),
            ms_user.get("employeeId"),
        )

        if not email:
            raise ValueError("Microsoft account has no email — cannot map to a user")

        # Strategy 1: Match by email as username
        user = await self._user_repo.get_by_username(email)

        # Strategy 2: Match by email in user_details table
        if user is None:
            logger.info("[SSO] Username didn't match, trying user_details.email='%s'", email)
            user = await self._user_repo.get_by_email(email)

        # Strategy 3: Match by employeeId as username
        if user is None:
            employee_id = ms_user.get("employeeId") or ""
            if employee_id:
                logger.info("[SSO] Email didn't match, trying employeeId='%s'", employee_id)
                user = await self._user_repo.get_by_username(employee_id)

        # Strategy 4: Match by email prefix as username
        if user is None:
            email_prefix = email.split("@")[0] if "@" in email else ""
            if email_prefix:
                logger.info("[SSO] Still no match, trying email prefix='%s'", email_prefix)
                user = await self._user_repo.get_by_username(email_prefix)

        if user is None:
            logger.warning("[SSO] No user found for email='%s' in database", email)
            raise ValueError(
                f"No account found for '{email}'. Please contact your administrator to create an account first."
            )

        return user
