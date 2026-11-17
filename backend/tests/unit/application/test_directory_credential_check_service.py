"""
Unit tests for DirectoryCredentialCheckService: the throttled AD credential check.

The point of the service is that guessing an employee's directory password through the
diagnostics screen costs the same as guessing it at the login form: bounded, and refused
before Darwin is asked.
"""

import pytest
from login_throttle_fakes import FakeLoginAttemptStore
from user_fakes import FakeDirectory

from src.application.services.directory_credential_check_service import (
    THROTTLE_SCOPE,
    DirectoryCredentialCheckService,
)
from src.application.services.login_throttle_service import (
    LoginThrottledError,
    LoginThrottlePolicy,
    LoginThrottleService,
)
from src.infrastructure.external.employee_ad.employee_ad_client import EmployeeADUnavailableError

POLICY = LoginThrottlePolicy(
    window_seconds=300,
    max_attempts_per_account_ip=3,
    max_attempts_per_account=6,
    max_failures_per_ip=5,
    lockout_seconds=60,
)
IP = "10.0.0.1"


@pytest.fixture
def store() -> FakeLoginAttemptStore:
    return FakeLoginAttemptStore()


@pytest.fixture
def directory() -> FakeDirectory:
    return FakeDirectory()


@pytest.fixture
def throttle(store: FakeLoginAttemptStore) -> LoginThrottleService:
    return LoginThrottleService(store, POLICY)


@pytest.fixture
def service(
    directory: FakeDirectory, throttle: LoginThrottleService
) -> DirectoryCredentialCheckService:
    return DirectoryCredentialCheckService(directory, throttle)


class TestCheck:
    async def test_returns_the_directory_answer(
        self, service: DirectoryCredentialCheckService, directory: FakeDirectory
    ) -> None:
        directory.valid = True

        result = await service.check("E1", "pw", client_ip=IP)

        assert result.is_valid_user is True
        assert directory.calls == [("E1", "pw")]

    async def test_an_invalid_answer_is_returned_not_raised(
        self, service: DirectoryCredentialCheckService, directory: FakeDirectory
    ) -> None:
        directory.valid = False

        result = await service.check("E1", "pw", client_ip=IP)

        assert result.is_valid_user is False


class TestThrottle:
    async def test_repeated_wrong_guesses_are_refused_before_the_directory_is_asked(
        self, service: DirectoryCredentialCheckService, directory: FakeDirectory
    ) -> None:
        directory.valid = False
        for _ in range(POLICY.max_attempts_per_account_ip):
            await service.check("E1", "guess", client_ip=IP)
        asked = len(directory.calls)

        with pytest.raises(LoginThrottledError) as refused:
            await service.check("E1", "guess", client_ip=IP)

        assert refused.value.retry_after_seconds == POLICY.lockout_seconds
        assert len(directory.calls) == asked, "Darwin must not be reached once refused"

    async def test_the_correct_password_is_refused_during_a_lockout(
        self, service: DirectoryCredentialCheckService, directory: FakeDirectory
    ) -> None:
        directory.valid = False
        for _ in range(POLICY.max_attempts_per_account_ip):
            await service.check("E1", "guess", client_ip=IP)
        directory.valid = True

        with pytest.raises(LoginThrottledError):
            await service.check("E1", "right", client_ip=IP)

    async def test_another_employee_is_unaffected(
        self, service: DirectoryCredentialCheckService, directory: FakeDirectory
    ) -> None:
        directory.valid = False
        for _ in range(POLICY.max_attempts_per_account_ip + 1):
            try:
                await service.check("E1", "guess", client_ip=IP)
            except LoginThrottledError:
                break

        assert (await service.check("E2", "guess", client_ip=IP)).is_valid_user is False

    async def test_it_has_its_own_budget_apart_from_the_login_form(
        self,
        service: DirectoryCredentialCheckService,
        directory: FakeDirectory,
        throttle: LoginThrottleService,
    ) -> None:
        directory.valid = False
        for _ in range(POLICY.max_attempts_per_account_ip + 1):
            try:
                await service.check("E1", "guess", client_ip=IP)
            except LoginThrottledError:
                break

        # The same person at the login form is not locked by guesses made here.
        ticket = await throttle.begin_attempt("E1", IP)
        assert (
            ticket.account_ip_key
            != (await throttle.begin_attempt(f"{THROTTLE_SCOPE}E1", "10.9.9.9")).account_ip_key
        )

    async def test_a_valid_answer_clears_earlier_misses(
        self, service: DirectoryCredentialCheckService, directory: FakeDirectory
    ) -> None:
        directory.valid = False
        for _ in range(POLICY.max_attempts_per_account_ip - 1):
            await service.check("E1", "typo", client_ip=IP)
        directory.valid = True
        await service.check("E1", "right", client_ip=IP)

        directory.valid = False
        for _ in range(POLICY.max_attempts_per_account_ip):
            await service.check("E1", "typo", client_ip=IP)


class TestDirectoryFailure:
    async def test_an_outage_propagates_untouched(
        self, service: DirectoryCredentialCheckService, directory: FakeDirectory
    ) -> None:
        directory.error = EmployeeADUnavailableError("down")

        with pytest.raises(EmployeeADUnavailableError):
            await service.check("E1", "pw", client_ip=IP)

    async def test_an_outage_is_not_counted_as_a_wrong_guess(
        self, service: DirectoryCredentialCheckService, directory: FakeDirectory
    ) -> None:
        directory.error = EmployeeADUnavailableError("down")
        for _ in range(POLICY.max_failures_per_ip + 2):
            with pytest.raises(EmployeeADUnavailableError):
                await service.check("E1", "pw", client_ip=IP)
        directory.error = None
        directory.valid = True

        assert (await service.check("E1", "pw", client_ip=IP)).is_valid_user is True
