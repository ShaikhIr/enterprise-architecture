"""
Integration tests for POST /api/v1/users/import-employees.

These assert the contract the endpoint advertises: per-employee outcomes, where
one bad record does not prevent the others from importing. Written before the
fix, so they document two defects:

1. New users were constructed with `UserModel(role="USER")`. That column was
   dropped in migration c9d4e2f5a1b7, so every new-employee import raised
   TypeError — reported as a per-row "failed", which made a code bug look like
   an AD data-quality problem.
2. A database-level error inside the loop left the session unusable, so every
   subsequent employee failed too. Without savepoints the advertised
   partial-success contract cannot be honoured.
"""

from collections.abc import Callable, Iterator
from contextlib import AbstractContextManager, contextmanager
from typing import Any
from unittest.mock import AsyncMock

import pytest
from httpx import AsyncClient
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.api.v1.dependencies import get_employee_ad_client
from src.infrastructure.database.models.user_details_model import UserDetailsModel
from src.infrastructure.database.models.user_model import UserModel
from src.infrastructure.security.password_encoder import verify_password
from src.main import app

IMPORT_URL = "/api/v1/users/import-employees"


def _employee(employee_id: str, first: str = "Ada", last: str = "Lovelace") -> dict[str, Any]:
    """A Darwin AD payload in the snake_case shape the extractor expects."""
    return {
        "employee_id": employee_id,
        "first_name": first,
        "last_name": last,
        "company_email_id": f"{first.lower()}.{last.lower()}@corp.com",
        "designation_title": "Engineer",
        "department": "Technology",
        "office_location": "Pune",
        "office_state": "MH",
        "office_city": "Pune",
    }


# Calling the fixture returns a context manager that makes the AD client answer with the
# given employees for the duration of the `with` block.
DarwinStub = Callable[[list[dict[str, Any]]], AbstractContextManager[Any]]


@pytest.fixture
def darwin_returns() -> DarwinStub:
    """Override the injected AD client so no network call is made."""

    @contextmanager
    def _apply(employees: list[dict[str, Any]]) -> Iterator[None]:
        stub = AsyncMock()
        stub.get_selected_employees.return_value = {"employeeData": employees}
        app.dependency_overrides[get_employee_ad_client] = lambda: stub
        try:
            yield
        finally:
            app.dependency_overrides.pop(get_employee_ad_client, None)

    return _apply

class TestSingleEmployeeImport:
    async def test_new_employee_is_created(
        self,
        admin_client: AsyncClient,
        darwin_returns: DarwinStub,
        db_session: AsyncSession,
    ) -> None:
        """A brand-new employee should be created, not reported as failed."""
        with darwin_returns([_employee("E1001")]):
            response = await admin_client.post(
                IMPORT_URL, json={"employee_ids": ["E1001"]}
            )

        assert response.status_code == 200, response.text
        body = response.json()
        assert body["failed"] == 0, body["results"]
        assert body["created"] == 1
        assert body["results"][0]["status"] == "created"

        # The user and their profile must actually be persisted.
        user = (
            await db_session.execute(
                select(UserModel).where(UserModel.username == "E1001")
            )
        ).scalar_one_or_none()
        assert user is not None
        details = (
            await db_session.execute(
                select(UserDetailsModel).where(UserDetailsModel.user_id == user.id)
            )
        ).scalar_one_or_none()
        assert details is not None
        assert details.employee_name == "Ada Lovelace"
        assert details.department == "Technology"

    async def test_existing_employee_is_updated(
        self, admin_client: AsyncClient, darwin_returns: DarwinStub
    ) -> None:
        """Re-importing the same employee updates rather than duplicating."""
        with darwin_returns([_employee("E1002")]):
            first = await admin_client.post(
                IMPORT_URL, json={"employee_ids": ["E1002"]}
            )
        assert first.json()["created"] == 1, first.text

        with darwin_returns([_employee("E1002", first="Grace", last="Hopper")]):
            second = await admin_client.post(
                IMPORT_URL, json={"employee_ids": ["E1002"]}
            )

        assert second.status_code == 200, second.text
        body = second.json()
        assert body["updated"] == 1
        assert body["created"] == 0
        assert body["failed"] == 0

    async def test_missing_employee_id_is_reported(
        self, admin_client: AsyncClient, darwin_returns: DarwinStub
    ) -> None:
        """A payload with no id is a per-row failure, not a request failure."""
        with darwin_returns([{"first_name": "No", "last_name": "Id"}]):
            response = await admin_client.post(IMPORT_URL, json={"employee_ids": ["X"]})

        assert response.status_code == 200, response.text
        body = response.json()
        assert body["failed"] == 1
        assert body["results"][0]["employee_id"] == "unknown"


class TestDefaultPassword:
    """A new user's stored password hash reflects the chosen default."""

    @staticmethod
    async def _password_hash_for(db_session: AsyncSession, username: str) -> str:
        user = (
            await db_session.execute(
                select(UserModel).where(UserModel.username == username)
            )
        ).scalar_one()
        return user.password_hash

    async def test_default_password_is_hashed_onto_new_users(
        self,
        admin_client: AsyncClient,
        darwin_returns: DarwinStub,
        db_session: AsyncSession,
    ) -> None:
        with darwin_returns([_employee("P1001")]):
            response = await admin_client.post(
                IMPORT_URL,
                json={"employee_ids": ["P1001"], "default_password": "Welcome@123"},
            )

        assert response.status_code == 200, response.text
        assert response.json()["created"] == 1

        stored = await self._password_hash_for(db_session, "P1001")
        assert verify_password("Welcome@123", stored) is True
        assert verify_password("P1001", stored) is False

    async def test_absent_default_password_leaves_a_password_nobody_knows(
        self,
        admin_client: AsyncClient,
        darwin_returns: DarwinStub,
        db_session: AsyncSession,
    ) -> None:
        with darwin_returns([_employee("P1002"), _employee("P1003")]):
            response = await admin_client.post(
                IMPORT_URL, json={"employee_ids": ["P1002", "P1003"]}
            )

        assert response.status_code == 200, response.text
        assert response.json()["created"] == 2

        first = await self._password_hash_for(db_session, "P1002")
        second = await self._password_hash_for(db_session, "P1003")
        # Not the employee id (which every colleague can guess), and not shared.
        assert verify_password("P1002", first) is False
        assert verify_password("P1003", second) is False
        assert first != second

    async def test_blank_default_password_is_treated_as_absent(
        self,
        admin_client: AsyncClient,
        darwin_returns: DarwinStub,
        db_session: AsyncSession,
    ) -> None:
        with darwin_returns([_employee("P1004")]):
            response = await admin_client.post(
                IMPORT_URL, json={"employee_ids": ["P1004"], "default_password": "   "}
            )

        assert response.status_code == 200, response.text
        stored = await self._password_hash_for(db_session, "P1004")
        assert verify_password("   ", stored) is False
        assert verify_password("P1004", stored) is False

    @pytest.mark.parametrize("password", ["short", "1234567", "x" * 73, "é" * 40])
    async def test_an_unusable_default_password_is_rejected(
        self, admin_client: AsyncClient, darwin_returns: DarwinStub, password: str
    ) -> None:
        """Too short to be a password, or too long for bcrypt to read all of it."""
        with darwin_returns([_employee("P1005")]):
            response = await admin_client.post(
                IMPORT_URL, json={"employee_ids": ["P1005"], "default_password": password}
            )

        assert response.status_code == 422, response.text

    async def test_a_default_password_at_the_limits_is_accepted(
        self, admin_client: AsyncClient, darwin_returns: DarwinStub
    ) -> None:
        for index, password in enumerate(["12345678", "x" * 72]):
            employee_id = f"P11{index}"
            with darwin_returns([_employee(employee_id)]):
                response = await admin_client.post(
                    IMPORT_URL,
                    json={"employee_ids": [employee_id], "default_password": password},
                )
            assert response.status_code == 200, response.text


class TestPartialFailureIsolation:
    """The core contract: one bad record must not take down the batch."""

    async def test_bad_record_does_not_block_the_others(
        self,
        admin_client: AsyncClient,
        darwin_returns: DarwinStub,
        db_session: AsyncSession,
    ) -> None:
        """
        The first employee's id exceeds users.username (String(255)), which fails
        at flush time. The second is valid and must still be imported.
        """
        too_long = "E" * 300
        with darwin_returns([_employee(too_long), _employee("E2002")]):
            response = await admin_client.post(
                IMPORT_URL, json={"employee_ids": [too_long, "E2002"]}
            )

        assert response.status_code == 200, response.text
        body = response.json()
        assert body["failed"] == 1, body["results"]
        assert body["created"] == 1, body["results"]

        statuses = {r["employee_id"]: r["status"] for r in body["results"]}
        assert statuses[too_long] == "failed"
        assert statuses["E2002"] == "created"

        # The good record is really there; the bad one is not.
        good = (
            await db_session.execute(
                select(func.count())
                .select_from(UserModel)
                .where(UserModel.username == "E2002")
            )
        ).scalar_one()
        assert good == 1

    async def test_good_records_before_and_after_a_failure_both_survive(
        self, admin_client: AsyncClient, darwin_returns: DarwinStub
    ) -> None:
        """Failure in the middle of the batch isolates to that record only."""
        too_long = "E" * 300
        with darwin_returns(
            [_employee("E3001"), _employee(too_long), _employee("E3003")]
        ):
            response = await admin_client.post(
                IMPORT_URL, json={"employee_ids": ["E3001", too_long, "E3003"]}
            )

        assert response.status_code == 200, response.text
        body = response.json()
        assert body["created"] == 2, body["results"]
        assert body["failed"] == 1, body["results"]
