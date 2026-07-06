"""
Application-level exceptions for the LACM master domain.

Services raise these instead of bare ``ValueError`` so that the offending
field/reason/resource is preserved. Controllers map them to HTTP responses:

* ``MasterValidationError`` -> 422 Unprocessable Entity
* ``MasterConflictError``   -> 409 Conflict
* ``MasterNotFoundError``   -> 404 Not Found
"""


class MasterError(Exception):
    """Base class for master application exceptions."""


class MasterValidationError(MasterError):
    """Raised when a required/format/range/reference validation fails."""

    def __init__(self, field: str, reason: str) -> None:
        self.field = field
        self.reason = reason
        super().__init__(f"Validation failed for '{field}': {reason}")


class MasterConflictError(MasterError):
    """Raised on a uniqueness, overlap, or in-use conflict."""

    def __init__(self, detail: str) -> None:
        self.detail = detail
        super().__init__(detail)


class MasterNotFoundError(MasterError):
    """Raised when a referenced record does not exist."""

    def __init__(self, resource: str, id: object) -> None:
        self.resource = resource
        self.id = id
        super().__init__(f"{resource} with id '{id}' was not found")
