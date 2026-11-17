"""
Unit tests for LoginService: throttle -> authenticate -> audit.

The authenticator and the audit sink are small hand-written fakes; the throttle is the real
`LoginThrottleService` over `FakeLoginAttemptStore`, so these tests pin down how the three
cooperate (what is counted, what is audited, what is never reached) rather than re-testing
the limiter itself.
"""

from dataclasses import dataclass, field
from typing import Any

import pytest
from login_throttle_fakes import FakeLoginAttemptStore

from src.application.exceptions.auth_exceptions import (
    AuthenticationError,
    AuthServiceUnavailableError,
    InvalidCredentialsError,
    UserBlockedError,
    UserInactiveError,
)
from src.application.ports.session_authenticator import AuthTokenResponse
from src.application.services.login_service import (
    LoginRejected,
    LoginService,
    LoginSucceeded,
    LoginThrottled,
)
from src.application.services.login_throttle_service import (
    LoginThrottlePolicy,
    LoginThrottleService,
)

POLICY = LoginThrottlePolicy(
    window_seconds=300,
    max_attempts_per_account_ip=3,
    max_attempts_per_account=6,
    max_failures_per_ip=5,
    lockout_seconds=60,
)
IP = "10.0.0.1"


class FakeAuthenticator:
    """Accepts one password, or raises whatever a test sets."""

    def __init__(self) -> None:
        self.error: AuthenticationError | None = None
        self.calls: list[tuple[str, str]] = []

    async def login(self, username: str, password: str) -> AuthTokenResponse:
        self.calls.append((username, password))
        if self.error is not None:
            raise self.error
        return AuthTokenResponse(
            access_token="access", refresh_token="refresh", user_id=7, username=username
        )

    async def microsoft_login(self, profile: dict[str, Any]) -> AuthTokenResponse:
        raise NotImplementedError

    async def refresh(self, refresh_token: str) -> AuthTokenResponse:
        raise NotImplementedError

    async def revoke_session(self, refresh_token: str) -> None:
        raise NotImplementedError


@dataclass
class FakeAuditor:
    """Records what the use case audited."""

    logins: list[dict[str, Any]] = field(default_factory=list)
    lockouts: list[dict[str, Any]] = field(default_factory=list)

    async def log_login(self, **kwargs: Any) -> None:
        self.logins.append(kwargs)

    async def log_login_locked(self, **kwargs: Any) -> None:
        self.lockouts.append(kwargs)


@pytest.fixture
def authenticator() -> FakeAuthenticator:
    return FakeAuthenticator()


@pytest.fixture
def auditor() -> FakeAuditor:
    return FakeAuditor()


@pytest.fixture
def service(authenticator: FakeAuthenticator, auditor: FakeAuditor) -> LoginService:
    throttle = LoginThrottleService(FakeLoginAttemptStore(), POLICY)
    return LoginService(authenticator, throttle, auditor)


async def attempt(service: LoginService, username: str = "alice", ip: str = IP) -> object:
    return await service.login(username, "pw", client_ip=ip, user_agent="UA")


class TestSuccess:
    async def test_returns_the_session(self, service: LoginService) -> None:
        result = await attempt(service)

        assert isinstance(result, LoginSucceeded)
        assert result.tokens.access_token == "access"

    async def test_audits_the_success_with_the_resolved_user(
        self, service: LoginService, auditor: FakeAuditor
    ) -> None:
        await attempt(service)

        assert auditor.logins == [
            {
                "user_id": 7,
                "username": "alice",
                "success": True,
                "ip_address": IP,
                "user_agent": "UA",
            }
        ]

    async def test_a_success_clears_the_misses_from_that_address(
        self, service: LoginService, authenticator: FakeAuthenticator
    ) -> None:
        authenticator.error = InvalidCredentialsError()
        for _ in range(POLICY.max_attempts_per_account_ip - 1):
            await attempt(service)
        authenticator.error = None
        await attempt(service)

        authenticator.error = InvalidCredentialsError()
        results = [await attempt(service) for _ in range(POLICY.max_attempts_per_account_ip)]

        assert all(isinstance(r, LoginRejected) for r in results)


class TestRejection:
    @pytest.mark.parametrize(
        ("error", "reason"),
        [
            (InvalidCredentialsError(), "Invalid credentials"),
            (UserInactiveError(), "User inactive"),
            (UserBlockedError(), "User blocked"),
        ],
    )
    async def test_is_reported_and_audited_with_its_reason(
        self,
        service: LoginService,
        authenticator: FakeAuthenticator,
        auditor: FakeAuditor,
        error: AuthenticationError,
        reason: str,
    ) -> None:
        authenticator.error = error

        result = await attempt(service)

        assert result == LoginRejected(status_code=error.status_code, message=error.message)
        assert auditor.logins[0]["success"] is False
        assert auditor.logins[0]["reason"] == reason
        assert auditor.logins[0]["user_id"] is None

    async def test_a_directory_outage_is_audited_but_not_counted_as_a_guess(
        self,
        service: LoginService,
        authenticator: FakeAuthenticator,
        auditor: FakeAuditor,
    ) -> None:
        authenticator.error = AuthServiceUnavailableError()

        results = [await attempt(service) for _ in range(POLICY.max_failures_per_ip + 2)]

        assert all(
            isinstance(r, LoginRejected) and r.status_code == 503 for r in results
        ), "an outage must never turn into a 429 for the user"
        assert auditor.logins[0]["reason"] == "Authentication service unavailable"

    async def test_an_unrecognised_failure_is_audited_with_a_default_reason(
        self, service: LoginService, authenticator: FakeAuthenticator, auditor: FakeAuditor
    ) -> None:
        authenticator.error = AuthenticationError("odd", status_code=418)

        result = await attempt(service)

        assert result == LoginRejected(status_code=418, message="odd")
        assert auditor.logins[0]["reason"] == "Rejected"


class TestThrottle:
    async def test_repeated_failures_end_in_a_throttle_before_the_password_is_checked(
        self, service: LoginService, authenticator: FakeAuthenticator
    ) -> None:
        authenticator.error = InvalidCredentialsError()
        for _ in range(POLICY.max_attempts_per_account_ip):
            assert isinstance(await attempt(service), LoginRejected)
        checked_before = len(authenticator.calls)

        result = await attempt(service)

        assert result == LoginThrottled(retry_after_seconds=POLICY.lockout_seconds)
        assert len(authenticator.calls) == checked_before, "no credential may be checked"

    async def test_even_the_right_password_is_refused_during_a_lockout(
        self, service: LoginService, authenticator: FakeAuthenticator
    ) -> None:
        authenticator.error = InvalidCredentialsError()
        for _ in range(POLICY.max_attempts_per_account_ip):
            await attempt(service)
        authenticator.error = None

        assert isinstance(await attempt(service), LoginThrottled)

    async def test_the_start_of_a_lockout_is_audited_once(
        self, service: LoginService, authenticator: FakeAuthenticator, auditor: FakeAuditor
    ) -> None:
        authenticator.error = InvalidCredentialsError()
        for _ in range(POLICY.max_attempts_per_account_ip + 5):
            await attempt(service)

        assert len(auditor.lockouts) == 1
        assert auditor.lockouts[0]["username"] == "alice"
        assert auditor.lockouts[0]["ip_address"] == IP
        assert "account_ip_lockout" in auditor.lockouts[0]["reason"]

    async def test_refused_attempts_are_not_audited_as_logins(
        self, service: LoginService, authenticator: FakeAuthenticator, auditor: FakeAuditor
    ) -> None:
        authenticator.error = InvalidCredentialsError()
        for _ in range(POLICY.max_attempts_per_account_ip):
            await attempt(service)
        audited = len(auditor.logins)

        await attempt(service)
        await attempt(service)

        assert len(auditor.logins) == audited

    async def test_another_address_is_not_locked_out_with_the_attacker(
        self, service: LoginService, authenticator: FakeAuthenticator
    ) -> None:
        authenticator.error = InvalidCredentialsError()
        for _ in range(POLICY.max_attempts_per_account_ip + 1):
            await attempt(service, ip="203.0.113.9")
        authenticator.error = None

        assert isinstance(await attempt(service, ip="198.51.100.4"), LoginSucceeded)
