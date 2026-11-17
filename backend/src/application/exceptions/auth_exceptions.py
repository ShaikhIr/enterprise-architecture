"""
Authentication failures.

They live in the application layer, not beside the adapter that raises them, so the login
use case (`LoginService`) can tell a rejected password from an unavailable directory
without importing infrastructure. Each carries the HTTP status the API boundary answers
with, set by the code that raised it.
"""


class AuthenticationError(Exception):
    """Base authentication error."""

    def __init__(self, message: str, status_code: int = 401) -> None:
        self.message = message
        self.status_code = status_code
        super().__init__(message)


class UserInactiveError(AuthenticationError):
    """Raised when user account is inactive."""

    def __init__(self) -> None:
        super().__init__("User account is inactive", status_code=403)


class UserBlockedError(AuthenticationError):
    """Raised when user account is blocked."""

    def __init__(self) -> None:
        super().__init__("User account is blocked", status_code=403)


class InvalidCredentialsError(AuthenticationError):
    """Raised when credentials are invalid."""

    def __init__(self) -> None:
        super().__init__("Invalid username or password", status_code=401)


class InvalidTokenError(AuthenticationError):
    """Raised when a token is missing, malformed, expired, revoked or reused."""

    def __init__(self, message: str = "Invalid or expired token") -> None:
        super().__init__(message, status_code=401)


class AuthServiceUnavailableError(AuthenticationError):
    """
    Raised when credentials cannot be checked because the directory is unreachable.

    Distinct from `InvalidCredentialsError` on purpose: an outage says nothing about the
    password, so it must not be counted as a failed guess against the user's address.
    """

    def __init__(self) -> None:
        super().__init__(
            "Authentication service is temporarily unavailable. Please try again later.",
            status_code=503,
        )


class MicrosoftEmailMissingError(AuthenticationError):
    """Raised when a Microsoft Graph profile carries no email to verify against."""

    def __init__(self) -> None:
        super().__init__(
            "Microsoft account has no email — cannot map to a user",
            status_code=400,
        )


class SsoUserNotProvisionedError(AuthenticationError):
    """
    Raised when a verified Microsoft email matches no imported employee profile.

    The user authenticated with Microsoft successfully, but their employee
    details were never imported from the Darwin AD service, so there is no
    local account to sign them in to.
    """

    def __init__(self) -> None:
        super().__init__(
            "No account found for this Microsoft email. "
            "Please contact your administrator to import your profile from AD.",
            status_code=403,
        )
