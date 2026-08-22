"""
Unit tests for EmployeeADClient (the Darwin AD adapter).

All HTTP is served by an in-process MockTransport via the `stub_http` fixture:
these tests never reach the network. That matters more than usual here, because
`EMPLOYEE_AD_BASE_URL` defaults to a real internal production host, so an
un-stubbed test would issue live requests against Darwin.

Coverage focus is the adapter's contract: the request it builds, the parsing of
Darwin's PascalCase payload, and the mapping of transport/status failures onto
the three adapter exception types.
"""

from collections.abc import Callable

import httpx
import pytest

from src.config.settings import settings
from src.infrastructure.external.employee_ad.employee_ad_client import (
    EmployeeADAuthError,
    EmployeeADClient,
    EmployeeADError,
    EmployeeADUnavailableError,
)

BASE_URL = "http://darwin.test/adintegratorservices/rest/v1"

StubHttp = Callable[[Callable[[httpx.Request], httpx.Response]], list[httpx.Request]]


@pytest.fixture
def ad_client(monkeypatch: pytest.MonkeyPatch) -> EmployeeADClient:
    """A client pointed at a fake host, so a stub miss cannot hit production."""
    monkeypatch.setattr(settings, "EMPLOYEE_AD_BASE_URL", BASE_URL)
    return EmployeeADClient()


def _raiser(exc: Exception) -> Callable[[httpx.Request], httpx.Response]:
    """Handler that fails at the transport layer, as an unreachable host would."""

    def _handler(request: httpx.Request) -> httpx.Response:
        raise exc

    return _handler


# ─────────────────────────── Configuration ───────────────────────────


def test_base_url_strips_trailing_slash(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "EMPLOYEE_AD_BASE_URL", f"{BASE_URL}/")
    assert EmployeeADClient().base_url == BASE_URL


def test_is_configured_reflects_base_url(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "EMPLOYEE_AD_BASE_URL", BASE_URL)
    assert EmployeeADClient().is_configured is True

    monkeypatch.setattr(settings, "EMPLOYEE_AD_BASE_URL", "")
    assert EmployeeADClient().is_configured is False


# ─────────────────────────── health_check ───────────────────────────


@pytest.mark.asyncio
async def test_health_check_reports_reachable(
    ad_client: EmployeeADClient, stub_http: StubHttp
) -> None:
    requests = stub_http(lambda req: httpx.Response(200, text="up"))

    result = await ad_client.health_check()

    assert result == {
        "status": "reachable",
        "status_code": 200,
        "url": BASE_URL,
    }
    assert str(requests[0].url) == BASE_URL


@pytest.mark.asyncio
async def test_health_check_reports_non_200_as_reachable(
    ad_client: EmployeeADClient, stub_http: StubHttp
) -> None:
    """A 404 still proves the host answered, so it is reachable, not an error."""
    stub_http(lambda req: httpx.Response(404))

    result = await ad_client.health_check()

    assert result["status"] == "reachable"
    assert result["status_code"] == 404


@pytest.mark.asyncio
async def test_health_check_reports_unreachable_without_raising(
    ad_client: EmployeeADClient, stub_http: StubHttp
) -> None:
    stub_http(_raiser(httpx.ConnectError("no route to host")))

    result = await ad_client.health_check()

    assert result["status"] == "unreachable"
    assert "no route to host" in result["error"]
    assert result["url"] == BASE_URL


# ─────────────────────────── validate_credentials ───────────────────────────


@pytest.mark.asyncio
async def test_validate_credentials_sends_multipart_and_parses_result(
    ad_client: EmployeeADClient, stub_http: StubHttp
) -> None:
    requests = stub_http(
        lambda req: httpx.Response(
            200, json={"IsSuccess": True, "IsValidUser": True, "Message": "ok"}
        )
    )

    result = await ad_client.validate_credentials("E123", "secret")

    assert result.is_success is True
    assert result.is_valid_user is True
    assert result.raw_response["Message"] == "ok"

    sent = requests[0]
    assert sent.method == "POST"
    assert str(sent.url) == f"{BASE_URL}/validatecredentials"
    assert sent.headers["content-type"].startswith("multipart/form-data")
    body = sent.content.decode()
    assert "E123" in body
    assert "secret" in body


@pytest.mark.asyncio
async def test_validate_credentials_rejects_invalid_user_without_raising(
    ad_client: EmployeeADClient, stub_http: StubHttp
) -> None:
    """A wrong password is a 200 with IsValidUser=false, not an HTTP error."""
    stub_http(
        lambda req: httpx.Response(200, json={"IsSuccess": True, "IsValidUser": False})
    )

    result = await ad_client.validate_credentials("E123", "wrong")

    assert result.is_success is True
    assert result.is_valid_user is False


@pytest.mark.asyncio
async def test_validate_credentials_defaults_missing_flags_to_false(
    ad_client: EmployeeADClient, stub_http: StubHttp
) -> None:
    stub_http(lambda req: httpx.Response(200, json={}))

    result = await ad_client.validate_credentials("E123", "secret")

    assert result.is_success is False
    assert result.is_valid_user is False
    assert result.raw_response == {}


@pytest.mark.parametrize("status_code", [401, 403])
@pytest.mark.asyncio
async def test_validate_credentials_maps_auth_statuses(
    ad_client: EmployeeADClient, stub_http: StubHttp, status_code: int
) -> None:
    stub_http(lambda req: httpx.Response(status_code, text="denied"))

    with pytest.raises(EmployeeADAuthError) as exc_info:
        await ad_client.validate_credentials("E123", "secret")

    assert str(status_code) in exc_info.value.detail
    assert "denied" in exc_info.value.detail


@pytest.mark.parametrize("status_code", [400, 500, 503])
@pytest.mark.asyncio
async def test_validate_credentials_maps_other_statuses_to_generic_error(
    ad_client: EmployeeADClient, stub_http: StubHttp, status_code: int
) -> None:
    stub_http(lambda req: httpx.Response(status_code, text="boom"))

    with pytest.raises(EmployeeADError) as exc_info:
        await ad_client.validate_credentials("E123", "secret")

    assert not isinstance(exc_info.value, EmployeeADAuthError)
    assert not isinstance(exc_info.value, EmployeeADUnavailableError)


@pytest.mark.asyncio
async def test_error_detail_is_truncated(
    ad_client: EmployeeADClient, stub_http: StubHttp
) -> None:
    """Darwin can return an HTML error page; the detail must stay log-sized."""
    stub_http(lambda req: httpx.Response(500, text="x" * 5000))

    with pytest.raises(EmployeeADError) as exc_info:
        await ad_client.validate_credentials("E123", "secret")

    assert exc_info.value.detail.count("x") == 200


@pytest.mark.asyncio
async def test_validate_credentials_maps_transport_failure_to_unavailable(
    ad_client: EmployeeADClient, stub_http: StubHttp
) -> None:
    stub_http(_raiser(httpx.ConnectTimeout("timed out")))

    with pytest.raises(EmployeeADUnavailableError) as exc_info:
        await ad_client.validate_credentials("E123", "secret")

    assert "timed out" in exc_info.value.detail


# ─────────────────────────── get_selected_employees ───────────────────────────


@pytest.mark.asyncio
async def test_get_selected_employees_joins_ids_and_returns_payload(
    ad_client: EmployeeADClient, stub_http: StubHttp
) -> None:
    payload = {"Employees": [{"employee_id": "E1"}, {"employee_id": "E2"}]}
    requests = stub_http(lambda req: httpx.Response(200, json=payload))

    result = await ad_client.get_selected_employees(["E1", "E2", "E3"])

    assert result == payload
    sent = requests[0]
    assert str(sent.url) == f"{BASE_URL}/getselectedemployees"
    assert "E1,E2,E3" in sent.content.decode()


@pytest.mark.asyncio
async def test_get_selected_employees_maps_auth_error(
    ad_client: EmployeeADClient, stub_http: StubHttp
) -> None:
    stub_http(lambda req: httpx.Response(401))

    with pytest.raises(EmployeeADAuthError):
        await ad_client.get_selected_employees(["E1"])


@pytest.mark.asyncio
async def test_get_selected_employees_maps_transport_failure(
    ad_client: EmployeeADClient, stub_http: StubHttp
) -> None:
    stub_http(_raiser(httpx.ReadError("reset")))

    with pytest.raises(EmployeeADUnavailableError):
        await ad_client.get_selected_employees(["E1"])


# ─────────────────────────── get_employees ───────────────────────────


@pytest.mark.asyncio
async def test_get_employees_issues_get_and_returns_payload(
    ad_client: EmployeeADClient, stub_http: StubHttp
) -> None:
    requests = stub_http(lambda req: httpx.Response(200, json={"Employees": []}))

    result = await ad_client.get_employees()

    assert result == {"Employees": []}
    assert requests[0].method == "GET"
    assert str(requests[0].url) == f"{BASE_URL}/getemployees"


@pytest.mark.asyncio
async def test_get_employees_maps_server_error(
    ad_client: EmployeeADClient, stub_http: StubHttp
) -> None:
    stub_http(lambda req: httpx.Response(503, text="unavailable"))

    with pytest.raises(EmployeeADError):
        await ad_client.get_employees()


@pytest.mark.asyncio
async def test_get_employees_maps_transport_failure(
    ad_client: EmployeeADClient, stub_http: StubHttp
) -> None:
    stub_http(_raiser(httpx.ConnectError("down")))

    with pytest.raises(EmployeeADUnavailableError):
        await ad_client.get_employees()


# ─────────────────────────── get_hierarchy_data ───────────────────────────


@pytest.mark.asyncio
async def test_get_hierarchy_data_returns_payload(
    ad_client: EmployeeADClient, stub_http: StubHttp
) -> None:
    requests = stub_http(lambda req: httpx.Response(200, json={"Hierarchy": [1, 2]}))

    result = await ad_client.get_hierarchy_data()

    assert result == {"Hierarchy": [1, 2]}
    assert str(requests[0].url) == f"{BASE_URL}/getHierarchyData"


@pytest.mark.asyncio
async def test_get_hierarchy_data_maps_auth_error(
    ad_client: EmployeeADClient, stub_http: StubHttp
) -> None:
    stub_http(lambda req: httpx.Response(403))

    with pytest.raises(EmployeeADAuthError):
        await ad_client.get_hierarchy_data()


@pytest.mark.asyncio
async def test_get_hierarchy_data_maps_transport_failure(
    ad_client: EmployeeADClient, stub_http: StubHttp
) -> None:
    stub_http(_raiser(httpx.ConnectError("down")))

    with pytest.raises(EmployeeADUnavailableError):
        await ad_client.get_hierarchy_data()


# ─────────────────────────── Exception defaults ───────────────────────────


def test_adapter_exceptions_carry_default_details() -> None:
    assert EmployeeADError().detail == "Employee AD service error"
    assert EmployeeADAuthError().detail == "Employee AD authentication failed"
    assert EmployeeADUnavailableError().detail == "Employee AD service unavailable"
