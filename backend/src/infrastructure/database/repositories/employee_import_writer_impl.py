"""
Bulk write adapter for the employee (Darwin AD) importer.

Uses the ORM, unlike a Core-based bulk importer: a comma-separated list of employee ids
is a handful to a few hundred rows per request, not tens of thousands, so the
identity-map overhead a bulk importer avoids by using Core does not apply here. Sticking
with the ORM also means this adapter can reuse `UserRepositoryImpl` mapping conventions
directly.

Each employee is written inside its own SAVEPOINT via `UnitOfWork.savepoint()`. Without
that, a database error on one record (e.g. an employee id long enough to overflow
`users.username`) leaves the request's session unusable and every later employee in the
same batch fails too.
"""

import logging
from typing import Any

from sqlalchemy.exc import SQLAlchemyError

from src.application.ports.employee_import_writer import (
    EmployeeImportOutcome,
    IEmployeeImportWriter,
)
from src.domain.entities.user import User
from src.domain.entities.user_details import UserDetails
from src.domain.repositories.user_details_repository import IUserDetailsRepository
from src.domain.repositories.user_repository import IUserRepository
from src.infrastructure.database.unit_of_work import UnitOfWork

__all__ = ["EmployeeImportWriterImpl"]

logger = logging.getLogger(__name__)


class EmployeeImportWriterImpl(IEmployeeImportWriter):
    """Find-or-create a user plus their Darwin profile, one record at a time."""

    def __init__(
        self,
        uow: UnitOfWork,
        user_repo: IUserRepository,
        user_details_repo: IUserDetailsRepository,
    ) -> None:
        """
        Args:
            uow: Owns the transaction boundary and the SAVEPOINT per record. Must
                already have an active session — constructed via
                `UnitOfWork.from_session(session)` for the request-scoped session
                `get_db_session` will commit once, at the end of the request.
            user_repo: Repository bound to the same session as `uow`.
            user_details_repo: Repository bound to the same session as `uow`.
        """
        self._uow = uow
        self._users = user_repo
        self._details = user_details_repo

    async def upsert_employee(
        self,
        *,
        employee_id: str,
        details_fields: dict[str, Any],
        new_user_password_hash: str,
        actor: str,
    ) -> EmployeeImportOutcome:
        try:
            async with self._uow.savepoint():
                return await self._upsert(
                    employee_id=employee_id,
                    details_fields=details_fields,
                    new_user_password_hash=new_user_password_hash,
                    actor=actor,
                )
        except SQLAlchemyError as exc:
            logger.warning("Import failed for employee %s: %s", employee_id, exc)
            return EmployeeImportOutcome(
                employee_id=employee_id,
                status="failed",
                message=str(exc)[:200],
            )

    async def _upsert(
        self,
        *,
        employee_id: str,
        details_fields: dict[str, Any],
        new_user_password_hash: str,
        actor: str,
    ) -> EmployeeImportOutcome:
        user = await self._users.get_by_username(employee_id)
        created = user is None

        if user is None:
            user = await self._users.create(
                User(
                    username=employee_id,
                    password_hash=new_user_password_hash,
                    is_active=True,
                    is_blocked=False,
                    created_by=actor,
                    modified_by=actor,
                )
            )

        existing_details = await self._details.get_by_user_id(user.id)
        details = UserDetails(
            # Reuse the existing row's id on update; 0 lets the DB assign one on insert.
            id=existing_details.id if existing_details else 0,
            user_id=user.id,
            created_by=existing_details.created_by if existing_details else actor,
            modified_by=actor,
            **details_fields,
        )
        if existing_details is None:
            await self._details.create(details)
        else:
            await self._details.update(details)

        return EmployeeImportOutcome(
            employee_id=employee_id,
            status="created" if created else "updated",
        )
