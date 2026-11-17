"""
Domain exceptions (EntityNotFound, BusinessRuleViolation, etc.).

Services raise these to describe *what* went wrong in business terms. They
deliberately carry no HTTP status: mapping a failure onto a status code is a
transport concern, and `ExceptionHandlerMiddleware` owns that translation.
"""


class DomainError(Exception):
    """Base class for all domain/business rule failures."""

    def __init__(self, message: str) -> None:
        self.message = message
        super().__init__(message)


class EntityNotFoundError(DomainError):
    """A referenced aggregate does not exist."""

    def __init__(self, entity: str, identifier: object) -> None:
        super().__init__(f"{entity} '{identifier}' was not found")
        self.entity = entity
        self.identifier = identifier


class DuplicateEntityError(DomainError):
    """A uniqueness constraint would be violated."""

    def __init__(self, entity: str, field: str, value: object) -> None:
        super().__init__(f"{entity} with {field} '{value}' already exists")
        self.entity = entity
        self.field = field
        self.value = value


class BusinessRuleViolationError(DomainError):
    """An operation is rejected by a business rule (e.g. record still in use)."""
