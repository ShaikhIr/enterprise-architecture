"""Port for checking an employee's credentials against the corporate directory (Darwin AD)."""

from typing import Any, Protocol


class IDirectoryValidationResult(Protocol):
    """What the directory answered. Read-only, so frozen dataclasses satisfy it."""

    @property
    def is_success(self) -> bool:
        """Whether the directory processed the request."""
        ...

    @property
    def is_valid_user(self) -> bool:
        """Whether the employee id and password are valid."""
        ...

    @property
    def raw_response(self) -> dict[str, Any]:
        """The directory's own response body."""
        ...


class IDirectoryCredentialValidator(Protocol):
    """The directory's credential check."""

    async def validate_credentials(
        self, employee_id: str, password: str
    ) -> IDirectoryValidationResult:
        """Ask the directory whether this employee id and password are valid."""
        ...
