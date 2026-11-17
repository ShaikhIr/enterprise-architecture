"""
The login use case: throttle, authenticate, audit.

The order is the point. The throttle runs before anything is looked up or verified, so a
refused request costs no bcrypt and never reaches the corporate AD service; failures are
counted and audited after the fact; an outage of the directory is reported but is not
counted as a guess, because it says nothing about the password.

No HTTP concepts here. The caller gets one of three results and decides how to present it.
"""

from dataclasses import dataclass

from src.application.exceptions.auth_exceptions import (
    AuthenticationError,
    AuthServiceUnavailableError,
    InvalidCredentialsError,
    UserBlockedError,
    UserInactiveError,
)
from src.application.ports.session_authenticator import (
    AuthTokenResponse,
    ILoginAuditor,
    ISessionAuthenticator,
)
from src.application.services.login_throttle_service import (
    LoginThrottledError,
    LoginThrottleService,
)

__all__ = [
    "LoginRejected",
    "LoginResult",
    "LoginService",
    "LoginSucceeded",
    "LoginThrottled",
]

# Why a rejected login was rejected, for the audit trail. Never sent to the client.
_REJECTION_REASONS: dict[type[AuthenticationError], str] = {
    InvalidCredentialsError: "Invalid credentials",
    UserInactiveError: "User inactive",
    UserBlockedError: "User blocked",
    AuthServiceUnavailableError: "Authentication service unavailable",
}
_DEFAULT_REASON = "Rejected"

# Failures that say something about the guess. An unavailable directory does not.
_COUNTED_AS_FAILURE = (InvalidCredentialsError, UserInactiveError, UserBlockedError)


@dataclass(frozen=True)
class LoginSucceeded:
    """Credentials accepted; `tokens` is the new session."""

    tokens: AuthTokenResponse


@dataclass(frozen=True)
class LoginRejected:
    """Credentials refused (or could not be checked). `message` is safe to show the user."""

    status_code: int
    message: str


@dataclass(frozen=True)
class LoginThrottled:
    """A limit refused the attempt before any credential was checked."""

    retry_after_seconds: int


LoginResult = LoginSucceeded | LoginRejected | LoginThrottled


class LoginService:
    """Runs one login attempt end to end."""

    def __init__(
        self,
        authenticator: ISessionAuthenticator,
        throttle: LoginThrottleService,
        auditor: ILoginAuditor,
    ) -> None:
        self._authenticator = authenticator
        self._throttle = throttle
        self._auditor = auditor

    async def login(
        self,
        username: str,
        password: str,
        *,
        client_ip: str,
        user_agent: str,
    ) -> LoginResult:
        """
        Attempt a login.

        Args:
            client_ip: The caller's address, as resolved at the API boundary (the socket peer,
                or `X-Forwarded-For` counted from the trusted end). It is both what attempts
                are rate-limited under and what the audit row records, so the audit trail
                cannot be steered by a forged header.
            user_agent: Recorded on the audit row.
        """
        try:
            ticket = await self._throttle.begin_attempt(username, client_ip)
        except LoginThrottledError as e:
            if e.lockout_started:
                await self._auditor.log_login_locked(
                    username=username,
                    ip_address=client_ip,
                    user_agent=user_agent,
                    reason=f"Locked for {e.retry_after_seconds}s after repeated failed "
                    f"logins ({e.reason.value})",
                )
            return LoginThrottled(retry_after_seconds=e.retry_after_seconds)

        try:
            tokens = await self._authenticator.login(username, password)
        except AuthenticationError as e:
            if isinstance(e, _COUNTED_AS_FAILURE):
                await self._throttle.record_failure(ticket)
            elif isinstance(e, AuthServiceUnavailableError):
                # Nothing was learned about the password, so the attempt is not held against
                # the user: retrying through an outage must not lock them out.
                await self._throttle.release_attempt(ticket)
            await self._auditor.log_login(
                user_id=None,
                username=username,
                success=False,
                ip_address=client_ip,
                user_agent=user_agent,
                reason=_REJECTION_REASONS.get(type(e), _DEFAULT_REASON),
            )
            return LoginRejected(status_code=e.status_code, message=e.message)

        await self._throttle.record_success(ticket)
        await self._auditor.log_login(
            user_id=tokens.user_id,
            username=tokens.username or username,
            success=True,
            ip_address=client_ip,
            user_agent=user_agent,
        )
        return LoginSucceeded(tokens=tokens)
