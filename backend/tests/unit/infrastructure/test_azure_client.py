"""
Unit tests for AzureSsoClient (the Microsoft OAuth2 / Graph adapter).

`exchange_code_for_profile` is a two-hop flow: token endpoint, then Graph. Both
hops are stubbed through one MockTransport and dispatched on host, so the tests
can prove the second hop actually carries the token from the first — a bug that
would otherwise only surface as a live 401 during a real SSO login.
"""

import urllib.parse
from collections.abc import Callable

import httpx
import pytest

from src.config.settings import settings
from src.infrastructure.external.azure_sso.azure_client import (
    AzureAuthError,
    AzureSsoClient,
    AzureTokenMissingError,
    AzureUnavailableError,
)

StubHttp = Callable[[Callable[[httpx.Request], httpx.Response]], list[httpx.Request]]

TENANT_ID = "tenant-abc"
CLIENT_ID = "client-xyz"
REDIRECT_URI = "http://localhost:6769/auth/microsoft/callback"

GRAPH_PROFILE = {
    "id": "ms-oid-1",
    "displayName": "Test User",
    "mail": "test.user@example.com",
    "userPrincipalName": "test.user@example.com",
}


@pytest.fixture
def azure_client(monkeypatch: pytest.MonkeyPatch) -> AzureSsoClient:
    monkeypatch.setattr(settings, "AZURE_CLIENT_ID", CLIENT_ID)
    monkeypatch.setattr(settings, "AZURE_CLIENT_SECRET", "client-secret")
    monkeypatch.setattr(settings, "AZURE_TENANT_ID", TENANT_ID)
    monkeypatch.setattr(settings, "AZURE_REDIRECT_URI", REDIRECT_URI)
    return AzureSsoClient()


def _two_hop(
    token_response: httpx.Response,
    graph_response: httpx.Response | None = None,
) -> Callable[[httpx.Request], httpx.Response]:
    """Dispatch on host: login.microsoftonline.com then graph.microsoft.com."""

    def _handler(request: httpx.Request) -> httpx.Response:
        if request.url.host == "login.microsoftonline.com":
            return token_response
        if request.url.host == "graph.microsoft.com":
            assert graph_response is not None, "Graph was called unexpectedly"
            return graph_response
        raise AssertionError(f"Unexpected host: {request.url.host}")

    return _handler


def _raiser(exc: Exception) -> Callable[[httpx.Request], httpx.Response]:
    def _handler(request: httpx.Request) -> httpx.Response:
        raise exc

    return _handler


# ─────────────────────────── Configuration ───────────────────────────


def test_is_configured_requires_client_and_tenant(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(settings, "AZURE_CLIENT_ID", CLIENT_ID)
    monkeypatch.setattr(settings, "AZURE_TENANT_ID", TENANT_ID)
    assert AzureSsoClient().is_configured is True

    monkeypatch.setattr(settings, "AZURE_TENANT_ID", "")
    assert AzureSsoClient().is_configured is False

    monkeypatch.setattr(settings, "AZURE_CLIENT_ID", "")
    monkeypatch.setattr(settings, "AZURE_TENANT_ID", TENANT_ID)
    assert AzureSsoClient().is_configured is False


def test_redirect_uri_falls_back_to_localhost_when_unset(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(settings, "AZURE_REDIRECT_URI", "")
    assert AzureSsoClient().redirect_uri == REDIRECT_URI


def test_redirect_uri_uses_configured_value(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(settings, "AZURE_REDIRECT_URI", "https://app.example/cb")
    assert AzureSsoClient().redirect_uri == "https://app.example/cb"


# ─────────────────────────── build_authorization_url ───────────────────────────


def test_build_authorization_url_targets_the_tenant(
    azure_client: AzureSsoClient,
) -> None:
    auth_url, redirect_uri = azure_client.build_authorization_url()

    assert auth_url.startswith(
        f"https://login.microsoftonline.com/{TENANT_ID}/oauth2/v2.0/authorize?"
    )
    assert redirect_uri == REDIRECT_URI


def test_build_authorization_url_carries_the_oauth_parameters(
    azure_client: AzureSsoClient,
) -> None:
    auth_url, _ = azure_client.build_authorization_url()
    query = urllib.parse.parse_qs(urllib.parse.urlparse(auth_url).query)

    assert query["client_id"] == [CLIENT_ID]
    assert query["response_type"] == ["code"]
    assert query["redirect_uri"] == [REDIRECT_URI]
    assert query["response_mode"] == ["query"]
    assert query["prompt"] == ["select_account"]
    assert query["scope"] == ["openid profile email User.Read"]


def test_build_authorization_url_never_leaks_the_client_secret(
    azure_client: AzureSsoClient,
) -> None:
    """The authorize URL goes to the browser; the secret must stay server-side."""
    auth_url, _ = azure_client.build_authorization_url()
    assert "client-secret" not in auth_url


# ─────────────────────────── exchange_code_for_profile ───────────────────────────


@pytest.mark.asyncio
async def test_exchange_code_returns_graph_profile(
    azure_client: AzureSsoClient, stub_http: StubHttp
) -> None:
    requests = stub_http(
        _two_hop(
            httpx.Response(200, json={"access_token": "ms-token"}),
            httpx.Response(200, json=GRAPH_PROFILE),
        )
    )

    profile = await azure_client.exchange_code_for_profile("auth-code")

    assert profile == GRAPH_PROFILE
    assert len(requests) == 2


@pytest.mark.asyncio
async def test_exchange_code_posts_the_authorization_code_grant(
    azure_client: AzureSsoClient, stub_http: StubHttp
) -> None:
    requests = stub_http(
        _two_hop(
            httpx.Response(200, json={"access_token": "ms-token"}),
            httpx.Response(200, json=GRAPH_PROFILE),
        )
    )

    await azure_client.exchange_code_for_profile("auth-code")

    token_request = requests[0]
    assert token_request.method == "POST"
    assert (
        str(token_request.url)
        == f"https://login.microsoftonline.com/{TENANT_ID}/oauth2/v2.0/token"
    )
    form = urllib.parse.parse_qs(token_request.content.decode())
    assert form["code"] == ["auth-code"]
    assert form["grant_type"] == ["authorization_code"]
    assert form["client_id"] == [CLIENT_ID]
    assert form["client_secret"] == ["client-secret"]
    assert form["redirect_uri"] == [REDIRECT_URI]


@pytest.mark.asyncio
async def test_exchange_code_forwards_the_token_to_graph(
    azure_client: AzureSsoClient, stub_http: StubHttp
) -> None:
    """Guards the hand-off between the two hops."""
    requests = stub_http(
        _two_hop(
            httpx.Response(200, json={"access_token": "ms-token"}),
            httpx.Response(200, json=GRAPH_PROFILE),
        )
    )

    await azure_client.exchange_code_for_profile("auth-code")

    graph_request = requests[1]
    assert graph_request.method == "GET"
    assert str(graph_request.url) == "https://graph.microsoft.com/v1.0/me"
    assert graph_request.headers["authorization"] == "Bearer ms-token"


@pytest.mark.asyncio
async def test_exchange_code_raises_when_token_absent(
    azure_client: AzureSsoClient, stub_http: StubHttp
) -> None:
    """A 200 with no access_token must not fall through to a Graph call."""
    requests = stub_http(_two_hop(httpx.Response(200, json={"token_type": "Bearer"})))

    with pytest.raises(AzureTokenMissingError):
        await azure_client.exchange_code_for_profile("auth-code")

    assert len(requests) == 1


@pytest.mark.asyncio
async def test_exchange_code_maps_token_endpoint_error(
    azure_client: AzureSsoClient, stub_http: StubHttp
) -> None:
    stub_http(
        _two_hop(httpx.Response(400, text='{"error":"invalid_grant"}'))
    )

    with pytest.raises(AzureAuthError) as exc_info:
        await azure_client.exchange_code_for_profile("stale-code")

    assert "invalid_grant" in exc_info.value.detail


@pytest.mark.asyncio
async def test_exchange_code_maps_graph_error(
    azure_client: AzureSsoClient, stub_http: StubHttp
) -> None:
    stub_http(
        _two_hop(
            httpx.Response(200, json={"access_token": "ms-token"}),
            httpx.Response(401, text="unauthorized"),
        )
    )

    with pytest.raises(AzureAuthError) as exc_info:
        await azure_client.exchange_code_for_profile("auth-code")

    assert "unauthorized" in exc_info.value.detail


@pytest.mark.asyncio
async def test_exchange_code_maps_transport_failure_to_unavailable(
    azure_client: AzureSsoClient, stub_http: StubHttp
) -> None:
    stub_http(_raiser(httpx.ConnectError("microsoft down")))

    with pytest.raises(AzureUnavailableError):
        await azure_client.exchange_code_for_profile("auth-code")
