"""
Authentication manager.
Coordinates login flow: user lookup, password verification, status checks, token issuance.
Supports dual authentication:
  - is_validate_ad=True: Validate via Darwin AD service
  - is_validate_ad=False: Validate via local bcrypt password

Refresh tokens are single-use and tracked server-side. Every login starts a *family* of
tokens; each refresh spends the presented token and issues its successor in the same family.
Presenting a token that was already spent (outside a short grace window for two tabs refreshing
at once) means it was copied, so the whole family is revoked and the user must sign in again.
"""

import logging
import uuid
from datetime import UTC, datetime, timedelta
from functools import cache
from typing import Any

from src.application.exceptions.auth_exceptions import (
    AuthenticationError,
    AuthServiceUnavailableError,
    InvalidCredentialsError,
    InvalidTokenError,
    MicrosoftEmailMissingError,
    SsoUserNotProvisionedError,
    UserBlockedError,
    UserInactiveError,
)
from src.application.ports.directory_credentials import IDirectoryCredentialValidator
from src.application.ports.session_authenticator import AuthTokenResponse
from src.config.settings import settings
from src.domain.entities.refresh_token import RefreshToken
from src.domain.entities.user import User
from src.domain.repositories.refresh_token_repository import IRefreshTokenRepository
from src.domain.repositories.user_details_repository import IUserDetailsRepository
from src.domain.repositories.user_repository import IUserRepository
from src.infrastructure.external.employee_ad.employee_ad_client import (
    EmployeeADError,
)
from src.infrastructure.security.jwt_provider import JWTProvider
from src.infrastructure.security.password_encoder import hash_password, verify_password

logger = logging.getLogger(__name__)

# The exceptions and `AuthTokenResponse` used to be defined here. They moved to the application
# layer so the login use case can handle them without importing infrastructure; the names stay
# importable from this module.
__all__ = [
    "AuthManager",
    "AuthServiceUnavailableError",
    "AuthTokenResponse",
    "AuthenticationError",
    "InvalidCredentialsError",
    "InvalidTokenError",
    "MicrosoftEmailMissingError",
    "SsoUserNotProvisionedError",
    "UserBlockedError",
    "UserInactiveError",
]


@cache
def _dummy_password_hash() -> str:
    """
    A bcrypt hash nobody has the password for, built once.

    Verifying against it makes the unknown-username path cost about the same as a wrong
    password for a real account, so response time does not reveal which usernames exist.
    """
    return hash_password(uuid.uuid4().hex)


class AuthManager:
    """Handles authentication operations: login, token refresh and session revocation."""

    def __init__(
        self,
        user_repository: IUserRepository,
        jwt_provider: JWTProvider,
        user_details_repository: IUserDetailsRepository,
        refresh_token_repository: IRefreshTokenRepository,
        directory: IDirectoryCredentialValidator,
    ) -> None:
        self._user_repo = user_repository
        self._jwt = jwt_provider
        self._user_details_repo = user_details_repository
        self._tokens = refresh_token_repository
        self._directory = directory

    async def login(self, username: str, password: str) -> AuthTokenResponse:
        """
        Authenticate a user with username and password.

        Flow:
        1. Find user by username
        2. If is_validate_ad=True → validate via Darwin AD service
        3. If is_validate_ad=False → verify local password hash
        4. Check is_active
        5. Check is_blocked
        6. Generate token pair

        Raises:
            InvalidCredentialsError: Wrong username or password.
            UserInactiveError: Account is deactivated.
            UserBlockedError: Account is blocked.
            AuthServiceUnavailableError: The corporate directory could not be reached.
        """
        user = await self._user_repo.get_by_username(username)

        if user is None:
            verify_password(password, _dummy_password_hash())
            raise InvalidCredentialsError()

        # Branch: AD validation vs local password
        if user.is_validate_ad:
            await self._validate_with_darwin(username, password)
        else:
            if not verify_password(password, user.password_hash):
                raise InvalidCredentialsError()

        if not user.is_active:
            raise UserInactiveError()

        if user.is_blocked:
            raise UserBlockedError()

        return await self._start_session(user)

    async def microsoft_login(self, profile: dict[str, Any]) -> AuthTokenResponse:
        """
        Authenticate a user from a verified Microsoft Graph profile.

        The Microsoft email is the verification key. It must resolve to a user
        who already exists locally — primarily an employee imported from the
        Darwin AD service, located by the email captured on their user_details
        profile. Microsoft accounts with no matching imported profile (and no
        matching local username) are rejected; the callback never provisions a
        user whose employee details were never imported.

        Flow:
        1. Extract and normalise the email from the Graph profile.
        2. Resolve the local user by user_details.email, then by username.
        3. Reject if no local user is found.
        4. Check is_active / is_blocked.
        5. Issue an application JWT pair.

        Raises:
            MicrosoftEmailMissingError: Profile carried no email.
            SsoUserNotProvisionedError: Email matched no imported/local user.
            UserInactiveError: Account is deactivated.
            UserBlockedError: Account is blocked.
        """
        upn = profile.get("userPrincipalName") or profile.get("mail") or ""
        email = (profile.get("mail") or upn or "").strip().lower()
        if not email:
            raise MicrosoftEmailMissingError()

        user = await self._resolve_sso_user(email)
        if user is None:
            logger.warning("Microsoft SSO rejected: no account for email %s", email)
            raise SsoUserNotProvisionedError()

        if not user.is_active:
            raise UserInactiveError()
        if user.is_blocked:
            raise UserBlockedError()

        return await self._start_session(user)

    async def refresh(self, refresh_token: str) -> AuthTokenResponse:
        """
        Spend a refresh token and issue its successor.

        A token can be spent once. The usual outcome is a new access token plus a new refresh
        token for the same session. If the presented token was already spent:

        - within `REFRESH_REUSE_GRACE_SECONDS`, it is almost certainly a second browser tab
          refreshing at the same moment, so it gets a new access token only (the cookie
          already holds the successor) and the session continues;
        - later than that, it has been copied, so the whole session is revoked.

        Raises:
            InvalidTokenError: Token is malformed, expired, unknown, revoked or replayed.
            UserInactiveError: User is no longer active (the session is revoked).
            UserBlockedError: User has been blocked since token issuance (session revoked).
        """
        try:
            payload = self._jwt.verify_token(refresh_token, expected_type="refresh")
        except Exception as e:
            # The reason (expired, bad signature, wrong type) is for the log, not the client.
            logger.info("Refresh token rejected: %s", e)
            raise InvalidTokenError() from e

        # A token without a jti predates rotation and cannot be tracked, so it is refused.
        if not payload.jti:
            raise InvalidTokenError()

        record = await self._tokens.get_by_jti(payload.jti)
        if record is None or record.revoked_at is not None:
            raise InvalidTokenError()

        user = await self._user_repo.get_by_username(payload.sub)
        if user is None or user.id != record.user_id:
            raise InvalidTokenError()

        now = datetime.now(UTC)
        if not user.is_active or user.is_blocked:
            await self._tokens.revoke_family(record.family_id, now)
            raise UserInactiveError() if not user.is_active else UserBlockedError()

        if record.used_at is None and await self._tokens.mark_used(record.jti, now):
            successor = await self._issue_refresh_token(user, record.family_id, now)
            return AuthTokenResponse(
                access_token=self._jwt.create_access_token(user.username, user.id),
                refresh_token=successor,
                user_id=user.id,
                username=user.username,
            )

        return await self._handle_spent_token(record.jti, user, now)

    async def revoke_session(self, refresh_token: str) -> None:
        """
        End the session a refresh token belongs to.

        Used by logout. A token that is malformed, expired or unknown has nothing to revoke,
        so this never raises for one: logging out must always succeed from the user's side.
        """
        try:
            payload = self._jwt.verify_token(refresh_token, expected_type="refresh")
        except Exception:
            return
        if not payload.jti:
            return
        record = await self._tokens.get_by_jti(payload.jti)
        if record is not None:
            await self._tokens.revoke_family(record.family_id, datetime.now(UTC))

    # ─── internals ───

    async def _start_session(self, user: User) -> AuthTokenResponse:
        """Open a new token family for a freshly authenticated user."""
        now = datetime.now(UTC)
        # Housekeeping rides on logins, the one event that happens regularly and is not on
        # the hot path of every request. Tokens expired for over a day are of no use to
        # reuse detection either.
        await self._tokens.delete_expired(now - timedelta(days=1))
        refresh_token = await self._issue_refresh_token(user, uuid.uuid4().hex, now)
        return AuthTokenResponse(
            access_token=self._jwt.create_access_token(user.username, user.id),
            refresh_token=refresh_token,
            user_id=user.id,
            username=user.username,
        )

    async def _issue_refresh_token(self, user: User, family_id: str, now: datetime) -> str:
        """Create a refresh token in `family_id` and record it so it can be spent and revoked."""
        jti = uuid.uuid4().hex
        token = self._jwt.create_refresh_token(user.username, user.id, jti=jti)
        await self._tokens.create(
            RefreshToken(
                jti=jti,
                family_id=family_id,
                user_id=user.id,
                expires_at=now + timedelta(days=settings.REFRESH_TOKEN_EXPIRE_DAYS),
            )
        )
        return token

    async def _handle_spent_token(self, jti: str, user: User, now: datetime) -> AuthTokenResponse:
        """Decide between "two tabs raced" and "a token was copied" for an already-spent token."""
        # Re-read: when two requests race, the loser's snapshot predates the winner's update.
        record = await self._tokens.get_by_jti(jti)
        if record is None or record.revoked_at is not None:
            raise InvalidTokenError()

        grace = timedelta(seconds=settings.REFRESH_REUSE_GRACE_SECONDS)
        if record.used_at is not None and now - record.used_at <= grace:
            return AuthTokenResponse(
                access_token=self._jwt.create_access_token(user.username, user.id),
                refresh_token=None,
                user_id=user.id,
                username=user.username,
            )

        logger.warning(
            "Refresh token reuse detected: revoking the session of user %s (family %s)",
            user.username,
            record.family_id,
        )
        await self._tokens.revoke_family(record.family_id, now)
        raise InvalidTokenError()

    async def _resolve_sso_user(self, email: str) -> User | None:
        """
        Resolve a Microsoft email to a local user.

        Primary path: the employee profile imported from AD stores the email in
        ``user_details.email`` while the user's ``username`` is their employee
        id, so matching on email is the only way to link the SSO identity to the
        imported account. Falls back to a username match for legacy users whose
        username is itself the email.
        """
        details = await self._user_details_repo.get_by_email(email)
        if details is not None and details.user_id is not None:
            user = await self._user_repo.get_by_id(details.user_id)
            if user is not None:
                return user

        return await self._user_repo.get_by_username(email)

    async def _validate_with_darwin(self, employee_id: str, password: str) -> None:
        """
        Validate credentials against Darwin AD service.

        Raises:
            InvalidCredentialsError: Darwin says the credentials are invalid.
            AuthServiceUnavailableError: Darwin could not be reached or answered with an
                error. That is not evidence about the password, so it is kept apart from
                a rejection and is not counted as a failed guess.
        """
        try:
            result = await self._directory.validate_credentials(employee_id, password)
        except EmployeeADError as exc:
            logger.error("Darwin AD validation failed for %s: %s", employee_id, exc)
            raise AuthServiceUnavailableError() from exc
        if not result.is_valid_user:
            raise InvalidCredentialsError()
