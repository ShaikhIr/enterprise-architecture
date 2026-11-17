"""
Throttled credential check against the corporate directory.

`POST /services/employee-ad/validate-credentials` tests an employee's AD password. Left
unthrottled it is a password-guessing oracle for anyone who holds the permission to call it,
and every guess reaches Darwin AD. It therefore goes through the same limiter as login, under
its own key scope so its budget is separate from the account's login budget.

Raises `LoginThrottledError` (from the limiter) when refused. Errors from the directory itself
propagate untouched and are not counted: an outage says nothing about the password, so the
attempt is given back to the caller's budget.
"""

from src.application.ports.directory_credentials import (
    IDirectoryCredentialValidator,
    IDirectoryValidationResult,
)
from src.application.services.login_throttle_service import LoginThrottleService

# Prefixes the employee id before it becomes a limiter key, so guesses made here and
# guesses made at the login form are counted separately.
THROTTLE_SCOPE = "directory-check:"


class DirectoryCredentialCheckService:
    """Checks one employee id / password pair with the limiter in front."""

    def __init__(
        self,
        directory: IDirectoryCredentialValidator,
        throttle: LoginThrottleService,
    ) -> None:
        self._directory = directory
        self._throttle = throttle

    async def check(
        self, employee_id: str, password: str, *, client_ip: str
    ) -> IDirectoryValidationResult:
        """
        Validate the credentials, or raise `LoginThrottledError` before asking the directory.

        A valid result clears this caller's earlier misses; an invalid one counts as a failure.
        """
        ticket = await self._throttle.begin_attempt(f"{THROTTLE_SCOPE}{employee_id}", client_ip)
        try:
            result = await self._directory.validate_credentials(employee_id, password)
        except Exception:
            # The directory failed, so the guess was never evaluated: give the attempt back.
            await self._throttle.release_attempt(ticket)
            raise
        if result.is_valid_user:
            await self._throttle.record_success(ticket)
        else:
            await self._throttle.record_failure(ticket)
        return result
