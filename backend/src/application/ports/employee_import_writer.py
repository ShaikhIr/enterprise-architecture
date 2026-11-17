"""
Bulk write port for the employee (Darwin AD) importer.

The service that orchestrates the import holds no SQLAlchemy import; the adapter behind
this port owns both the actual persistence and the per-employee savepoint isolation —
one bad record (e.g. an employee id that overflows `users.username`) must not fail the
employees already written earlier in the same batch.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Literal

__all__ = ["EmployeeImportOutcome", "IEmployeeImportWriter"]


@dataclass(frozen=True)
class EmployeeImportOutcome:
    """What happened to one employee record from the Darwin response."""

    employee_id: str
    status: Literal["created", "updated", "failed"]
    message: str = field(default="")


class IEmployeeImportWriter(ABC):
    """Upserts one employee (user + profile) at a time, isolated per record."""

    @abstractmethod
    async def upsert_employee(
        self,
        *,
        employee_id: str,
        details_fields: dict[str, Any],
        new_user_password_hash: str,
        actor: str,
    ) -> EmployeeImportOutcome:
        """
        Find-or-create the user keyed by `username == employee_id`, then upsert their
        profile from `details_fields`.

        Runs inside its own SAVEPOINT: a database error here (e.g. a value too long for
        a column) is caught and reported as a `"failed"` outcome rather than raised,
        leaving the surrounding request-scoped transaction — and every employee already
        written in this batch — intact.

        `new_user_password_hash` is only used when no existing user is found; an
        existing user's password is left untouched, matching the pre-existing import
        contract (Darwin validates AD users, so the local hash is otherwise unused).
        """
        ...
