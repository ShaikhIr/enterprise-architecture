"""
Integration tests for authentication API endpoints.
Tests the full request/response cycle through the ASGI app.

Dependencies are swapped via `app.dependency_overrides`, not `unittest.mock.patch`.
FastAPI resolves `Depends(...)` targets when routes are declared, so patching the
module attribute has no effect on an already-registered route — the override
registry is the supported mechanism and it applies to nested dependencies too.

Repositories are the hand-written fakes from `user_fakes.py` (no mock library); the Microsoft
provider and the corporate directory are small fakes too, since they stand for external
services. The audit rows the login route writes go to the rolled-back test transaction.
"""

import base64
import hashlib
import urllib.parse
from typing import Any

import pytest
from httpx import AsyncClient
from user_fakes import (
    FakeDirectory,
    FakeRefreshTokenRepository,
    FakeUserDetailsRepository,
    FakeUserRepository,
)

from src.api.v1.dependencies import (
    get_azure_sso_client,
    get_employee_ad_client,
    get_refresh_token_repository,
    get_user_details_repository,
    get_user_repository,
)
from src.config.settings import settings
from src.domain.entities.user import User
from src.domain.entities.user_details import UserDetails
from src.infrastructure.external.azure_sso import (
    AzureAuthError,
    AzureTokenMissingError,
    AzureUnavailableError,
)
from src.infrastructure.security.jwt_provider import JWTProvider
from src.infrastructure.security.password_encoder import hash_password
from src.main import app

PASSWORD = "TestPass123!"
REDIRECT_URI = "http://localhost:6769/auth/microsoft/callback"
DEFAULT_PROFILE = {
    "mail": "New.User@corp.com",
    "userPrincipalName": "new.user@corp.com",
    "displayName": "New User",
}


class FakeSsoClient:
    """Stands in for Microsoft: records what the controller sent, answers as told."""

    def __init__(
        self,
        *,
        configured: bool = True,
        profile: dict[str, Any] | None = None,
        error: Exception | None = None,
    ) -> None:
        self._configured = configured
        self.profile = DEFAULT_PROFILE if profile is None else profile
        self.error = error
        self.authorizations: list[tuple[str, str]] = []
        self.exchanges: list[tuple[str, str]] = []

    @property
    def is_configured(self) -> bool:
        return self._configured

    def build_authorization_url(self, *, state: str, code_challenge: str) -> tuple[str, str]:
        self.authorizations.append((state, code_challenge))
        query = urllib.parse.urlencode({"state": state, "code_challenge": code_challenge})
        return (
            f"https://login.microsoftonline.com/tenant/oauth2/v2.0/authorize?{query}",
            REDIRECT_URI,
        )

    async def exchange_code_for_profile(self, code: str, code_verifier: str) -> dict[str, Any]:
        self.exchanges.append((code, code_verifier))
        if self.error is not None:
            raise self.error
        return self.profile


@pytest.fixture
def users() -> FakeUserRepository:
    return FakeUserRepository()


@pytest.fixture
def details() -> FakeUserDetailsRepository:
    return FakeUserDetailsRepository()


@pytest.fixture
def tokens() -> FakeRefreshTokenRepository:
    return FakeRefreshTokenRepository()


@pytest.fixture
def directory() -> FakeDirectory:
    return FakeDirectory()


@pytest.fixture
def sso() -> FakeSsoClient:
    return FakeSsoClient()


@pytest.fixture
def active_user(users: FakeUserRepository) -> User:
    # is_validate_ad=False keeps login on the local bcrypt path so the test does not depend on
    # the external Darwin AD service.
    return users.add(
        User(
            username="integrationuser",
            password_hash=hash_password(PASSWORD),
            is_active=True,
            is_blocked=False,
            is_validate_ad=False,
        )
    )


@pytest.fixture
def api(
    client: AsyncClient,
    users: FakeUserRepository,
    details: FakeUserDetailsRepository,
    tokens: FakeRefreshTokenRepository,
    directory: FakeDirectory,
    sso: FakeSsoClient,
) -> AsyncClient:
    """
    The shared `client`, with the user, token, directory and SSO dependencies replaced.

    Building on `client` matters: the login endpoint writes an audit row through
    `get_db_session`, so without that override these tests would write into the
    development database. `client` points it at the rolled-back test transaction.
    """
    app.dependency_overrides[get_user_repository] = lambda: users
    app.dependency_overrides[get_user_details_repository] = lambda: details
    app.dependency_overrides[get_refresh_token_repository] = lambda: tokens
    app.dependency_overrides[get_employee_ad_client] = lambda: directory
    app.dependency_overrides[get_azure_sso_client] = lambda: sso
    return client


def bearer(user: User) -> dict[str, str]:
    token = JWTProvider().create_access_token(user.username, user.id)
    return {"Authorization": f"Bearer {token}"}


def cookie_headers(response: Any, name: str) -> list[str]:
    return [h for h in response.headers.get_list("set-cookie") if h.startswith(f"{name}=")]


class TestLoginAPI:
    """Integration tests for POST /api/v1/auth/login."""

    async def test_login_success(self, api: AsyncClient, active_user: User) -> None:
        response = await api.post(
            "/api/v1/auth/login", json={"username": "integrationuser", "password": PASSWORD}
        )

        assert response.status_code == 200, response.text
        data = response.json()
        assert data["access_token"]
        assert data["token_type"] == "Bearer"
        assert "refresh_token" not in data

    async def test_the_refresh_token_is_an_httponly_scoped_cookie(
        self, api: AsyncClient, active_user: User
    ) -> None:
        response = await api.post(
            "/api/v1/auth/login", json={"username": "integrationuser", "password": PASSWORD}
        )

        cookie = cookie_headers(response, settings.REFRESH_COOKIE_NAME)[0]
        assert "HttpOnly" in cookie
        assert f"Path={settings.REFRESH_COOKIE_PATH}" in cookie

    async def test_the_session_is_recorded_server_side(
        self, api: AsyncClient, active_user: User, tokens: FakeRefreshTokenRepository
    ) -> None:
        await api.post(
            "/api/v1/auth/login", json={"username": "integrationuser", "password": PASSWORD}
        )

        assert len(tokens.rows) == 1

    async def test_login_invalid_password(self, api: AsyncClient, active_user: User) -> None:
        response = await api.post(
            "/api/v1/auth/login", json={"username": "integrationuser", "password": "WrongPass!"}
        )

        assert response.status_code == 401, response.text
        assert response.json() == {"detail": "Invalid username or password"}

    async def test_login_missing_fields(self, api: AsyncClient) -> None:
        response = await api.post("/api/v1/auth/login", json={})

        assert response.status_code == 422

    async def test_a_directory_outage_is_a_503_not_a_wrong_password(
        self,
        api: AsyncClient,
        users: FakeUserRepository,
        directory: FakeDirectory,
    ) -> None:
        from src.infrastructure.external.employee_ad.employee_ad_client import (
            EmployeeADUnavailableError,
        )

        users.add(User(username="aduser", password_hash="", is_validate_ad=True))
        directory.error = EmployeeADUnavailableError("down")

        response = await api.post(
            "/api/v1/auth/login", json={"username": "aduser", "password": "whatever"}
        )

        assert response.status_code == 503, response.text
        assert "temporarily unavailable" in response.json()["detail"]
        assert cookie_headers(response, settings.REFRESH_COOKIE_NAME) == []

    async def test_retrying_through_an_outage_never_locks_the_user_out(
        self,
        api: AsyncClient,
        users: FakeUserRepository,
        directory: FakeDirectory,
    ) -> None:
        """The attempts were never evaluated, so they must not use up the user's budget."""
        from src.infrastructure.external.employee_ad.employee_ad_client import (
            EmployeeADUnavailableError,
        )

        users.add(User(username="aduser", password_hash="", is_validate_ad=True))
        directory.error = EmployeeADUnavailableError("down")
        body = {"username": "aduser", "password": "whatever"}

        statuses = [
            (await api.post("/api/v1/auth/login", json=body)).status_code for _ in range(12)
        ]
        assert set(statuses) == {503}

        # The directory recovers: the very next attempt is evaluated, not refused.
        directory.error = None
        directory.valid = True
        assert (await api.post("/api/v1/auth/login", json=body)).status_code == 200


class TestErrorBodyShape:
    """Every error carries `detail`, the shape the API standard requires."""

    async def test_an_unauthenticated_request_has_detail(self, client: AsyncClient) -> None:
        response = await client.get("/api/v1/auth/me")

        assert response.status_code == 401
        assert isinstance(response.json()["detail"], str)

    async def test_a_bad_token_does_not_explain_why_it_failed(self, api: AsyncClient) -> None:
        response = await api.get("/api/v1/auth/me", headers={"Authorization": "Bearer not.a.jwt"})

        assert response.status_code == 401
        assert response.json() == {"detail": "Invalid or expired token"}


class TestCorrelationIdHeader:
    """Integration tests verifying correlation ID is returned in responses."""

    async def test_response_has_correlation_id(self, client: AsyncClient) -> None:
        """Every response should include X-Correlation-ID header."""
        response = await client.get("/")

        assert "x-correlation-id" in response.headers

    async def test_provided_correlation_id_is_echoed(self, client: AsyncClient) -> None:
        """If client sends X-Correlation-ID, it should be echoed back."""
        custom_id = "my-custom-correlation-id"

        response = await client.get("/", headers={"X-Correlation-ID": custom_id})

        assert response.headers.get("x-correlation-id") == custom_id


# ─────────────────────── Microsoft SSO ───────────────────────


async def start_sso(api: AsyncClient) -> str:
    """Begin a Microsoft sign-in the way the SPA does; returns the `state` it was given."""
    response = await api.get("/api/v1/auth/microsoft/login")
    assert response.status_code == 200, response.text
    query = urllib.parse.parse_qs(urllib.parse.urlparse(response.json()["auth_url"]).query)
    return query["state"][0]


class TestMicrosoftLoginUrl:
    """GET /api/v1/auth/microsoft/login — the browser-redirect URL endpoint."""

    async def test_configured_sso_returns_the_authorization_url(self, api: AsyncClient) -> None:
        response = await api.get("/api/v1/auth/microsoft/login")

        assert response.status_code == 200, response.text
        body = response.json()
        assert body["auth_url"].startswith("https://login.microsoftonline.com")
        assert body["redirect_uri"] == REDIRECT_URI

    async def test_the_url_carries_an_unguessable_state_and_a_pkce_challenge(
        self, api: AsyncClient, sso: FakeSsoClient
    ) -> None:
        first = await start_sso(api)
        second = await start_sso(api)

        assert first != second
        assert len(first) >= 32
        assert len(sso.authorizations) == 2
        assert sso.authorizations[0] == (first, sso.authorizations[0][1])
        assert sso.authorizations[0][1] != sso.authorizations[1][1]

    async def test_the_sign_in_is_bound_to_the_browser_by_an_httponly_cookie(
        self, api: AsyncClient
    ) -> None:
        response = await api.get("/api/v1/auth/microsoft/login")

        cookie = cookie_headers(response, settings.SSO_TXN_COOKIE_NAME)[0]
        assert "HttpOnly" in cookie
        assert f"Path={settings.REFRESH_COOKIE_PATH}" in cookie
        assert f"Max-Age={settings.SSO_TXN_TTL_SECONDS}" in cookie

    async def test_the_verifier_stays_in_the_cookie_and_out_of_the_url(
        self, api: AsyncClient, sso: FakeSsoClient
    ) -> None:
        response = await api.get("/api/v1/auth/microsoft/login")

        state, challenge = sso.authorizations[0]
        cookie_value = cookie_headers(response, settings.SSO_TXN_COOKIE_NAME)[0].split(";")[0]
        stored_state, _, verifier = cookie_value.split("=", 1)[1].partition(".")
        assert stored_state == state
        assert verifier not in response.json()["auth_url"]
        digest = hashlib.sha256(verifier.encode("ascii")).digest()
        assert base64.urlsafe_b64encode(digest).rstrip(b"=").decode() == challenge

    async def test_unconfigured_sso_returns_501_and_sets_no_cookie(self, api: AsyncClient) -> None:
        app.dependency_overrides[get_azure_sso_client] = lambda: FakeSsoClient(configured=False)

        response = await api.get("/api/v1/auth/microsoft/login")

        assert response.status_code == 501, response.text
        assert cookie_headers(response, settings.SSO_TXN_COOKIE_NAME) == []


class TestMicrosoftSsoCallback:
    """
    POST /api/v1/auth/microsoft/callback

    The Microsoft email is the verification key: it must resolve to a locally
    known user — primarily an employee imported from AD, whose email lives on
    ``user_details`` while their username is the employee id. An email matching
    no imported profile (and no local username) is rejected rather than silently
    provisioned. The `state` must be the one this browser was issued.
    """

    @pytest.fixture
    def imported_employee(
        self, users: FakeUserRepository, details: FakeUserDetailsRepository
    ) -> User:
        employee = users.add(User(username="E12345", password_hash=""))
        details.add(
            UserDetails(user_id=employee.id, employee_id="E12345", email="new.user@corp.com")
        )
        return employee

    async def callback(self, api: AsyncClient, state: str, code: str = "valid-code") -> Any:
        return await api.post(
            "/api/v1/auth/microsoft/callback", json={"code": code, "state": state}
        )

    async def test_login_resolves_imported_employee_by_email(
        self, api: AsyncClient, imported_employee: User
    ) -> None:
        response = await self.callback(api, await start_sso(api))

        assert response.status_code == 200, response.text
        assert response.json()["access_token"]
        assert response.json()["token_type"] == "Bearer"

    async def test_the_code_is_exchanged_with_the_verifier_from_the_cookie(
        self, api: AsyncClient, imported_employee: User, sso: FakeSsoClient
    ) -> None:
        state = await start_sso(api)
        _, challenge = sso.authorizations[0]

        await self.callback(api, state, code="the-code")

        ((code, verifier),) = sso.exchanges
        assert code == "the-code"
        digest = hashlib.sha256(verifier.encode("ascii")).digest()
        assert base64.urlsafe_b64encode(digest).rstrip(b"=").decode() == challenge

    async def test_unprovisioned_email_is_rejected_not_created(
        self, api: AsyncClient, users: FakeUserRepository
    ) -> None:
        response = await self.callback(api, await start_sso(api))

        assert response.status_code == 403, response.text
        assert users.rows == {}

    async def test_legacy_username_match_still_works(
        self, api: AsyncClient, users: FakeUserRepository
    ) -> None:
        users.add(User(username="new.user@corp.com", password_hash=""))

        response = await self.callback(api, await start_sso(api))

        assert response.status_code == 200, response.text

    async def test_refresh_cookie_is_httponly_and_scoped(
        self, api: AsyncClient, imported_employee: User
    ) -> None:
        response = await self.callback(api, await start_sso(api))

        cookie = cookie_headers(response, settings.REFRESH_COOKIE_NAME)[0]
        assert "HttpOnly" in cookie
        assert "/api/v1/auth" in cookie

    async def test_the_sign_in_cookie_is_spent_by_a_successful_callback(
        self, api: AsyncClient, imported_employee: User
    ) -> None:
        state = await start_sso(api)

        first = await self.callback(api, state)
        replay = await self.callback(api, state)

        assert first.status_code == 200
        assert replay.status_code == 400, replay.text

    async def test_blocked_user_is_rejected(
        self, api: AsyncClient, imported_employee: User, users: FakeUserRepository
    ) -> None:
        imported_employee.is_blocked = True
        await users.update(imported_employee)

        response = await self.callback(api, await start_sso(api))

        assert response.status_code == 403, response.text

    async def test_a_callback_this_browser_never_started_is_refused(
        self, api: AsyncClient, imported_employee: User, sso: FakeSsoClient
    ) -> None:
        """No cookie: the redirect was forged or replayed from elsewhere (login CSRF)."""
        response = await self.callback(api, "attacker-chosen-state")

        assert response.status_code == 400, response.text
        assert "invalid or has expired" in response.json()["detail"]
        assert sso.exchanges == [], "Microsoft must not be called for a forged callback"

    async def test_a_state_that_is_not_the_issued_one_is_refused(
        self, api: AsyncClient, imported_employee: User, sso: FakeSsoClient
    ) -> None:
        await start_sso(api)

        response = await self.callback(api, "someone-elses-state")

        assert response.status_code == 400, response.text
        assert sso.exchanges == []
        assert cookie_headers(response, settings.REFRESH_COOKIE_NAME) == []

    async def test_a_refused_callback_discards_the_sign_in_cookie(
        self, api: AsyncClient, imported_employee: User
    ) -> None:
        await start_sso(api)

        response = await self.callback(api, "wrong")

        cleared = cookie_headers(response, settings.SSO_TXN_COOKIE_NAME)[0]
        assert "Max-Age=0" in cleared or "expires" in cleared.lower()

    @pytest.mark.parametrize(
        "body", [{}, {"code": "c"}, {"state": "s"}, {"code": "", "state": "s"}]
    )
    async def test_code_and_state_are_both_required(
        self, api: AsyncClient, body: dict[str, str]
    ) -> None:
        response = await api.post("/api/v1/auth/microsoft/callback", json=body)

        assert response.status_code == 422, response.text

    async def test_a_body_that_is_not_an_object_is_rejected(self, api: AsyncClient) -> None:
        response = await api.post("/api/v1/auth/microsoft/callback", json=["code"])

        assert response.status_code == 422, response.text

    async def test_unconfigured_sso_returns_501(self, api: AsyncClient) -> None:
        app.dependency_overrides[get_azure_sso_client] = lambda: FakeSsoClient(configured=False)

        response = await self.callback(api, "s")

        assert response.status_code == 501, response.text

    async def test_profile_without_email_returns_400(self, api: AsyncClient) -> None:
        app.dependency_overrides[get_azure_sso_client] = lambda: FakeSsoClient(
            profile={"displayName": "No Email"}
        )

        response = await self.callback(api, await start_sso(api))

        assert response.status_code == 400, response.text

    @pytest.mark.parametrize(
        ("error", "status"),
        [
            (AzureTokenMissingError(), 400),
            (AzureAuthError("Microsoft authentication failed"), 400),
            (AzureUnavailableError(), 502),
        ],
    )
    async def test_provider_failures_map_to_http_statuses(
        self, api: AsyncClient, error: Exception, status: int
    ) -> None:
        app.dependency_overrides[get_azure_sso_client] = lambda: FakeSsoClient(error=error)

        response = await self.callback(api, await start_sso(api))

        assert response.status_code == status, response.text

    async def test_microsofts_own_error_text_is_not_passed_to_the_browser(
        self, api: AsyncClient
    ) -> None:
        app.dependency_overrides[get_azure_sso_client] = lambda: FakeSsoClient(
            error=AzureAuthError("Microsoft authentication failed")
        )

        response = await self.callback(api, await start_sso(api))

        assert response.json() == {"detail": "Microsoft authentication failed"}


# ─────────────────────── /auth/refresh ───────────────────────


async def sign_in(api: AsyncClient) -> str:
    """Log in and return the refresh token the server issued."""
    response = await api.post(
        "/api/v1/auth/login", json={"username": "integrationuser", "password": PASSWORD}
    )
    assert response.status_code == 200, response.text
    return response.cookies[settings.REFRESH_COOKIE_NAME]


class TestRefreshTokenAPI:
    """POST /api/v1/auth/refresh — spends the HttpOnly refresh cookie for a new pair."""

    async def test_missing_cookie_returns_401(self, api: AsyncClient) -> None:
        response = await api.post("/api/v1/auth/refresh")

        assert response.status_code == 401, response.text
        assert "Missing refresh token" in response.json()["detail"]

    async def test_valid_cookie_returns_a_new_access_token(
        self, api: AsyncClient, active_user: User
    ) -> None:
        await sign_in(api)

        response = await api.post("/api/v1/auth/refresh")

        assert response.status_code == 200, response.text
        assert response.json()["access_token"]
        assert response.json()["token_type"] == "Bearer"

    async def test_the_refresh_cookie_is_rotated(self, api: AsyncClient, active_user: User) -> None:
        original = await sign_in(api)

        response = await api.post("/api/v1/auth/refresh")

        rotated = cookie_headers(response, settings.REFRESH_COOKIE_NAME)
        assert len(rotated) == 1, "a refresh must hand out a successor cookie"
        assert original not in rotated[0]
        assert "HttpOnly" in rotated[0]

    async def test_the_successor_cookie_keeps_the_session_going(
        self, api: AsyncClient, active_user: User
    ) -> None:
        await sign_in(api)

        first = await api.post("/api/v1/auth/refresh")
        second = await api.post("/api/v1/auth/refresh")

        assert first.status_code == 200
        assert second.status_code == 200, second.text

    async def test_a_second_tab_refreshing_at_once_keeps_the_session(
        self, api: AsyncClient, active_user: User
    ) -> None:
        """Both tabs present the same cookie; the loser gets an access token, no new cookie."""
        original = await sign_in(api)
        await api.post("/api/v1/auth/refresh")

        api.cookies.set(settings.REFRESH_COOKIE_NAME, original, path=settings.REFRESH_COOKIE_PATH)
        raced = await api.post("/api/v1/auth/refresh")

        assert raced.status_code == 200, raced.text
        assert raced.json()["access_token"]
        assert cookie_headers(raced, settings.REFRESH_COOKIE_NAME) == []

    async def test_a_replayed_token_after_the_grace_window_ends_the_session(
        self,
        api: AsyncClient,
        active_user: User,
        tokens: FakeRefreshTokenRepository,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        original = await sign_in(api)
        rotated = await api.post("/api/v1/auth/refresh")
        successor = cookie_headers(rotated, settings.REFRESH_COOKIE_NAME)[0].split(";")[0]
        monkeypatch.setattr(settings, "REFRESH_REUSE_GRACE_SECONDS", 0)

        api.cookies.set(settings.REFRESH_COOKIE_NAME, original, path=settings.REFRESH_COOKIE_PATH)
        replay = await api.post("/api/v1/auth/refresh")

        assert replay.status_code == 401, replay.text
        assert all(row.revoked_at is not None for row in tokens.rows.values())
        # The stolen-token holder's successor is dead too.
        api.cookies.set(
            settings.REFRESH_COOKIE_NAME,
            successor.split("=", 1)[1],
            path=settings.REFRESH_COOKIE_PATH,
        )
        assert (await api.post("/api/v1/auth/refresh")).status_code == 401

    async def test_garbage_cookie_returns_401_and_clears_it(self, api: AsyncClient) -> None:
        api.cookies.set(settings.REFRESH_COOKIE_NAME, "not-a-real-token")

        response = await api.post("/api/v1/auth/refresh")

        assert response.status_code == 401, response.text
        assert response.json() == {"detail": "Invalid or expired token"}
        # The stale cookie is cleared so the client stops retrying with it.
        assert cookie_headers(response, settings.REFRESH_COOKIE_NAME)

    async def test_a_signed_token_the_server_never_issued_is_refused(
        self, api: AsyncClient, active_user: User
    ) -> None:
        forged = JWTProvider().create_refresh_token(active_user.username, active_user.id)
        api.cookies.set(settings.REFRESH_COOKIE_NAME, forged)

        response = await api.post("/api/v1/auth/refresh")

        assert response.status_code == 401, response.text

    async def test_blocked_user_refresh_returns_403(
        self, api: AsyncClient, active_user: User, users: FakeUserRepository
    ) -> None:
        await sign_in(api)
        active_user.is_blocked = True
        await users.update(active_user)

        response = await api.post("/api/v1/auth/refresh")

        assert response.status_code == 403, response.text

    async def test_blocking_a_user_revokes_their_session_for_good(
        self,
        api: AsyncClient,
        active_user: User,
        users: FakeUserRepository,
        tokens: FakeRefreshTokenRepository,
    ) -> None:
        await sign_in(api)
        active_user.is_blocked = True
        await users.update(active_user)
        await api.post("/api/v1/auth/refresh")

        assert all(row.revoked_at is not None for row in tokens.rows.values())


# ─────────────────────── /auth/me ───────────────────────


class TestGetMeAPI:
    """GET /api/v1/auth/me — the authenticated caller's own profile."""

    async def test_anonymous_request_is_rejected(self, client: AsyncClient) -> None:
        response = await client.get("/api/v1/auth/me")

        assert response.status_code in (401, 403), response.text

    async def test_authenticated_request_returns_the_profile_without_a_password_hash(
        self, api: AsyncClient, active_user: User
    ) -> None:
        response = await api.get("/api/v1/auth/me", headers=bearer(active_user))

        assert response.status_code == 200, response.text
        body = response.json()
        assert body["username"] == active_user.username
        assert body["is_active"] is True
        assert "password_hash" not in body


# ─────────────────────── /auth/logout ───────────────────────


class TestLogoutAPI:
    """POST /api/v1/auth/logout — revokes the session, records it, clears the cookie."""

    async def test_anonymous_request_is_rejected(self, client: AsyncClient) -> None:
        response = await client.post("/api/v1/auth/logout")

        assert response.status_code in (401, 403), response.text

    async def test_authenticated_logout_clears_the_refresh_cookie(
        self, api: AsyncClient, active_user: User
    ) -> None:
        response = await api.post("/api/v1/auth/logout", headers=bearer(active_user))

        assert response.status_code == 200, response.text
        assert response.json()["detail"] == "Logged out successfully"
        assert cookie_headers(response, settings.REFRESH_COOKIE_NAME)

    async def test_logout_ends_the_session_server_side(
        self, api: AsyncClient, active_user: User, tokens: FakeRefreshTokenRepository
    ) -> None:
        cookie = await sign_in(api)
        api.cookies.set(settings.REFRESH_COOKIE_NAME, cookie, path=settings.REFRESH_COOKIE_PATH)

        await api.post("/api/v1/auth/logout", headers=bearer(active_user))

        assert all(row.revoked_at is not None for row in tokens.rows.values())

    async def test_a_copied_refresh_cookie_is_useless_after_logout(
        self, api: AsyncClient, active_user: User
    ) -> None:
        cookie = await sign_in(api)
        api.cookies.set(settings.REFRESH_COOKIE_NAME, cookie, path=settings.REFRESH_COOKIE_PATH)
        await api.post("/api/v1/auth/logout", headers=bearer(active_user))

        api.cookies.set(settings.REFRESH_COOKIE_NAME, cookie, path=settings.REFRESH_COOKIE_PATH)
        response = await api.post("/api/v1/auth/refresh")

        assert response.status_code == 401, response.text

    async def test_logout_without_a_refresh_cookie_still_succeeds(
        self, api: AsyncClient, active_user: User
    ) -> None:
        response = await api.post("/api/v1/auth/logout", headers=bearer(active_user))

        assert response.status_code == 200, response.text

    async def test_another_session_survives_a_logout(
        self, api: AsyncClient, active_user: User
    ) -> None:
        laptop = await sign_in(api)
        phone = await sign_in(api)
        api.cookies.set(settings.REFRESH_COOKIE_NAME, laptop, path=settings.REFRESH_COOKIE_PATH)
        await api.post("/api/v1/auth/logout", headers=bearer(active_user))

        api.cookies.set(settings.REFRESH_COOKIE_NAME, phone, path=settings.REFRESH_COOKIE_PATH)
        response = await api.post("/api/v1/auth/refresh")

        assert response.status_code == 200, response.text
