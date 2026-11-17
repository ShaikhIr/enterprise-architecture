"""
Integration tests for the Employee AD (Darwin) proxy endpoints under /services/employee-ad.

The Darwin client is replaced through `app.dependency_overrides[get_employee_ad_client]`, the
one seam every route in the controller takes it from, so no request leaves the process.

The part that matters most is `POST /validate-credentials`: it is a password oracle for
anyone holding the permission, so it must be throttled like the login form.
"""

from typing import Any

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from src.api.v1.dependencies import get_employee_ad_client
from src.infrastructure.database.models.user_model import UserModel
from src.infrastructure.external.employee_ad.employee_ad_client import (
    EmployeeADAuthError,
    EmployeeADError,
    EmployeeADUnavailableError,
    EmployeeValidationResult,
)
from src.infrastructure.security.jwt_provider import JWTProvider
from src.main import app

BASE = "/api/v1/services/employee-ad"
VALIDATE = f"{BASE}/validate-credentials"


class StubDarwin:
    """What the controller sees of Darwin; every answer is set by the test."""

    is_configured = True
    base_url = "https://darwin.example/rest/v1"

    def __init__(self) -> None:
        self.valid = True
        self.error: EmployeeADError | None = None
        self.validations: list[tuple[str, str]] = []
        self.payload: dict[str, Any] = {"employeeData": []}

    async def validate_credentials(
        self, employee_id: str, password: str
    ) -> EmployeeValidationResult:
        self.validations.append((employee_id, password))
        if self.error is not None:
            raise self.error
        return EmployeeValidationResult(
            is_success=True, is_valid_user=self.valid, raw_response={"IsValidUser": self.valid}
        )

    async def health_check(self) -> dict[str, Any]:
        return {"status": "reachable", "status_code": 200}

    async def get_selected_employees(self, employee_ids: list[str]) -> dict[str, Any]:
        if self.error is not None:
            raise self.error
        return self.payload

    async def get_employees(self) -> dict[str, Any]:
        if self.error is not None:
            raise self.error
        return self.payload

    async def get_hierarchy_data(self) -> dict[str, Any]:
        if self.error is not None:
            raise self.error
        return self.payload


@pytest.fixture
def darwin(admin_client: AsyncClient) -> StubDarwin:
    stub = StubDarwin()
    app.dependency_overrides[get_employee_ad_client] = lambda: stub
    return stub


async def validate(client: AsyncClient, employee_id: str = "E1001", password: str = "pw") -> Any:
    return await client.post(VALIDATE, json={"employee_id": employee_id, "password": password})


class TestAccess:
    async def test_anonymous_callers_are_rejected(self, client: AsyncClient) -> None:
        response = await client.post(VALIDATE, json={"employee_id": "E1", "password": "pw"})

        assert response.status_code in (401, 403)

    async def test_a_signed_in_user_without_the_permission_is_forbidden(
        self, client: AsyncClient, db_session: AsyncSession
    ) -> None:
        """Authenticated but holding no role: reaching Darwin needs `services.employee_ad`."""
        stub = StubDarwin()
        app.dependency_overrides[get_employee_ad_client] = lambda: stub
        outsider = UserModel(username="outsider", password_hash="x", is_validate_ad=False)
        db_session.add(outsider)
        await db_session.flush()
        token = JWTProvider().create_access_token(outsider.username, outsider.id)

        response = await client.post(
            VALIDATE,
            json={"employee_id": "E1", "password": "pw"},
            headers={"Authorization": f"Bearer {token}"},
        )

        assert response.status_code == 403, response.text
        assert stub.validations == []


class TestValidateCredentials:
    async def test_a_valid_pair_is_reported(
        self, admin_client: AsyncClient, darwin: StubDarwin
    ) -> None:
        response = await validate(admin_client)

        assert response.status_code == 200, response.text
        assert response.json()["is_valid_user"] is True
        assert darwin.validations == [("E1001", "pw")]

    async def test_an_invalid_pair_is_reported_not_an_error(
        self, admin_client: AsyncClient, darwin: StubDarwin
    ) -> None:
        darwin.valid = False

        response = await validate(admin_client)

        assert response.status_code == 200, response.text
        assert response.json()["is_valid_user"] is False


class TestValidateCredentialsThrottle:
    """Guessing a directory password here must cost as much as guessing it at login."""

    async def test_repeated_wrong_guesses_are_refused_with_429_and_retry_after(
        self, admin_client: AsyncClient, darwin: StubDarwin
    ) -> None:
        darwin.valid = False
        statuses = [(await validate(admin_client, password=f"g{n}")).status_code for n in range(8)]

        assert statuses[:5] == [200] * 5
        assert set(statuses[5:]) == {429}
        refused = await validate(admin_client, password="g9")
        assert int(refused.headers["retry-after"]) > 0
        assert refused.json() == {"detail": "Too many attempts. Please try again later."}

    async def test_darwin_is_not_asked_once_the_caller_is_refused(
        self, admin_client: AsyncClient, darwin: StubDarwin
    ) -> None:
        darwin.valid = False
        for n in range(5):
            await validate(admin_client, password=f"g{n}")
        asked = len(darwin.validations)

        for n in range(3):
            assert (await validate(admin_client, password=f"late{n}")).status_code == 429

        assert len(darwin.validations) == asked

    async def test_the_right_password_is_refused_during_a_lockout(
        self, admin_client: AsyncClient, darwin: StubDarwin
    ) -> None:
        darwin.valid = False
        for n in range(5):
            await validate(admin_client, password=f"g{n}")
        darwin.valid = True

        assert (await validate(admin_client, password="right")).status_code == 429

    async def test_another_employee_has_a_budget_of_their_own(
        self, admin_client: AsyncClient, darwin: StubDarwin
    ) -> None:
        darwin.valid = False
        for n in range(8):
            await validate(admin_client, employee_id="E1001", password=f"g{n}")

        assert (await validate(admin_client, employee_id="E2002")).status_code == 200

    async def test_a_darwin_outage_is_a_503_and_never_uses_up_the_budget(
        self, admin_client: AsyncClient, darwin: StubDarwin
    ) -> None:
        darwin.error = EmployeeADUnavailableError("down")
        statuses = [(await validate(admin_client)).status_code for _ in range(12)]
        assert set(statuses) == {503}

        darwin.error = None
        assert (await validate(admin_client)).status_code == 200


class TestDarwinErrorMapping:
    @pytest.mark.parametrize(
        ("error", "status"),
        [
            (EmployeeADAuthError("rejected"), 401),
            (EmployeeADUnavailableError("down"), 503),
            (EmployeeADError("boom"), 502),
        ],
    )
    @pytest.mark.parametrize("path", ["/selected-employees", "/employees", "/hierarchy"])
    async def test_darwin_failures_map_to_http_statuses(
        self,
        admin_client: AsyncClient,
        darwin: StubDarwin,
        error: EmployeeADError,
        status: int,
        path: str,
    ) -> None:
        darwin.error = error

        if path == "/selected-employees":
            response = await admin_client.post(BASE + path, json={"employee_ids": ["E1"]})
        else:
            response = await admin_client.get(BASE + path)

        assert response.status_code == status, response.text


class TestPassThrough:
    async def test_health_reports_the_injected_client(
        self, admin_client: AsyncClient, darwin: StubDarwin
    ) -> None:
        response = await admin_client.get(f"{BASE}/health")

        assert response.status_code == 200, response.text
        body = response.json()
        assert body["configured"] is True
        assert body["base_url"] == darwin.base_url
        assert body["status"] == "reachable"

    async def test_employees_are_returned_as_darwin_sent_them(
        self, admin_client: AsyncClient, darwin: StubDarwin
    ) -> None:
        darwin.payload = {"employeeData": [{"employee_id": "E1"}]}

        response = await admin_client.get(f"{BASE}/employees")

        assert response.json() == darwin.payload

    async def test_selected_employees_and_hierarchy_use_the_injected_client(
        self, admin_client: AsyncClient, darwin: StubDarwin
    ) -> None:
        darwin.payload = {"ok": True}

        selected = await admin_client.post(
            f"{BASE}/selected-employees", json={"employee_ids": ["E1"]}
        )
        hierarchy = await admin_client.get(f"{BASE}/hierarchy")

        assert selected.json() == {"ok": True}
        assert hierarchy.json() == {"ok": True}
