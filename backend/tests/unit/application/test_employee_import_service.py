"""
Unit tests for EmployeeImportService.

The service orchestrates the Darwin import but holds no database — its only
collaborators are `IEmployeeImportWriter` and `IPasswordHasher`. So this test
hands it a small hand-written fake writer (records every call, scriptable to
fail a given id) and the real `BcryptPasswordHasher`, mirroring the project's
"fakes, not mocks" convention. The password-related assertions use the real
hasher's `verify` to prove the stored hash matches the intended plaintext,
rather than asserting on the opaque hash string itself.
"""

from typing import Any, Literal

import pytest

from src.application.ports.employee_import_writer import (
    EmployeeImportOutcome,
    IEmployeeImportWriter,
)
from src.application.services.employee_import_service import EmployeeImportService
from src.infrastructure.security.password_hasher_impl import BcryptPasswordHasher


class FakeEmployeeImportWriter(IEmployeeImportWriter):
    """Records each upsert; first sighting of an id is 'created', repeats 'updated'."""

    def __init__(self) -> None:
        self.calls: list[dict[str, Any]] = []
        self._seen: set[str] = set()
        # Ids a test wants to force into a 'failed' outcome, without a real DB error.
        self.failing_ids: set[str] = set()

    async def upsert_employee(
        self,
        *,
        employee_id: str,
        details_fields: dict[str, Any],
        new_user_password_hash: str,
        actor: str,
    ) -> EmployeeImportOutcome:
        self.calls.append(
            {
                "employee_id": employee_id,
                "details_fields": details_fields,
                "new_user_password_hash": new_user_password_hash,
                "actor": actor,
            }
        )
        if employee_id in self.failing_ids:
            return EmployeeImportOutcome(
                employee_id=employee_id, status="failed", message="forced failure"
            )
        status: Literal["created", "updated"] = (
            "updated" if employee_id in self._seen else "created"
        )
        self._seen.add(employee_id)
        return EmployeeImportOutcome(employee_id=employee_id, status=status)

    def hash_for(self, employee_id: str) -> str:
        """The password hash recorded for the (first) upsert of this employee."""
        for call in self.calls:
            if call["employee_id"] == employee_id:
                return str(call["new_user_password_hash"])
        raise AssertionError(f"no upsert recorded for {employee_id}")


def _employee(employee_id: str, first: str = "Ada", last: str = "Lovelace") -> dict[str, Any]:
    """A Darwin AD payload in the snake_case shape the extractor expects."""
    return {
        "employee_id": employee_id,
        "first_name": first,
        "last_name": last,
        "company_email_id": f"{first.lower()}.{last.lower()}@corp.com",
    }


@pytest.fixture
def writer() -> FakeEmployeeImportWriter:
    return FakeEmployeeImportWriter()


@pytest.fixture
def hasher() -> BcryptPasswordHasher:
    return BcryptPasswordHasher()


@pytest.fixture
def service(
    writer: FakeEmployeeImportWriter, hasher: BcryptPasswordHasher
) -> EmployeeImportService:
    return EmployeeImportService(writer=writer, password_hasher=hasher)


class TestDefaultPassword:
    async def test_without_default_password_new_user_gets_employee_id_as_password(
        self,
        service: EmployeeImportService,
        writer: FakeEmployeeImportWriter,
        hasher: BcryptPasswordHasher,
    ) -> None:
        await service.import_employees({"employeeData": [_employee("E1001")]}, actor="admin")

        stored = writer.hash_for("E1001")
        assert hasher.verify("E1001", stored) is True

    async def test_default_password_is_applied_to_new_users(
        self,
        service: EmployeeImportService,
        writer: FakeEmployeeImportWriter,
        hasher: BcryptPasswordHasher,
    ) -> None:
        await service.import_employees(
            {"employeeData": [_employee("E1002")]},
            actor="admin",
            default_password="Welcome@123",
        )

        stored = writer.hash_for("E1002")
        assert hasher.verify("Welcome@123", stored) is True
        # The employee id must no longer be accepted as the password.
        assert hasher.verify("E1002", stored) is False

    async def test_blank_default_password_falls_back_to_employee_id(
        self,
        service: EmployeeImportService,
        writer: FakeEmployeeImportWriter,
        hasher: BcryptPasswordHasher,
    ) -> None:
        await service.import_employees(
            {"employeeData": [_employee("E1003")]},
            actor="admin",
            default_password="   ",
        )

        stored = writer.hash_for("E1003")
        assert hasher.verify("E1003", stored) is True

    async def test_default_password_applies_to_every_new_user_in_the_batch(
        self,
        service: EmployeeImportService,
        writer: FakeEmployeeImportWriter,
        hasher: BcryptPasswordHasher,
    ) -> None:
        await service.import_employees(
            {"employeeData": [_employee("E1"), _employee("E2")]},
            actor="admin",
            default_password="Shared#Pass1",
        )

        assert hasher.verify("Shared#Pass1", writer.hash_for("E1")) is True
        assert hasher.verify("Shared#Pass1", writer.hash_for("E2")) is True


class TestOutcomeCounts:
    async def test_created_updated_and_failed_are_tallied(
        self, service: EmployeeImportService, writer: FakeEmployeeImportWriter
    ) -> None:
        writer.failing_ids.add("BAD")
        result = await service.import_employees(
            {"employeeData": [_employee("A"), _employee("A"), _employee("BAD")]},
            actor="admin",
        )

        assert result.total == 3
        assert result.created == 1
        assert result.updated == 1
        assert result.failed == 1

    async def test_record_without_employee_id_is_a_per_row_failure(
        self, service: EmployeeImportService, writer: FakeEmployeeImportWriter
    ) -> None:
        result = await service.import_employees(
            {"employeeData": [{"first_name": "No", "last_name": "Id"}]}, actor="admin"
        )

        assert result.failed == 1
        assert result.results[0]["employee_id"] == "unknown"
        # A record with no id must never reach the writer.
        assert writer.calls == []
