"""
Integration tests for authentication API endpoints.
Tests the full request/response cycle through the ASGI app.

Dependencies are swapped via `app.dependency_overrides`, not `unittest.mock.patch`.
FastAPI resolves `Depends(...)` targets when routes are declared, so patching the
module attribute has no effect on an already-registered route — the override
registry is the supported mechanism and it applies to nested dependencies too.
"""

from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest
from httpx import AsyncClient

from src.api.v1.dependencies import get_user_repository
from src.domain.entities.user import User
from src.infrastructure.security.password_encoder import hash_password
from src.main import app


@pytest.fixture
def active_user() -> User:
    # is_validate_ad=False keeps login on the local bcrypt path so the test
    # does not depend on the external Darwin AD service.
    return User(
        id=uuid4(),
        username="integrationuser",
        password_hash=hash_password("TestPass123!"),
        is_active=True,
        is_blocked=False,
        is_validate_ad=False,
    )


@pytest.fixture
def mock_user_repo(active_user: User) -> AsyncMock:
    repo = AsyncMock()
    repo.get_by_username.return_value = active_user
    return repo


@pytest.fixture
def auth_client(client: AsyncClient, mock_user_repo: AsyncMock) -> AsyncClient:
    """
    Client with a mocked user repository, layered on the shared `client` fixture.

    Building on `client` matters: the login endpoint writes an audit row through
    `get_db_session`, so without that override these tests would write into the
    development database. `client` points it at the rolled-back test transaction.
    """
    app.dependency_overrides[get_user_repository] = lambda: mock_user_repo
    return client


class TestLoginAPI:
    """Integration tests for POST /api/v1/auth/login."""

    async def test_login_success(self, auth_client: AsyncClient) -> None:
        """Valid login should return 200 with a token pair."""
        response = await auth_client.post(
            "/api/v1/auth/login",
            json={"username": "integrationuser", "password": "TestPass123!"},
        )

        assert response.status_code == 200, response.text
        data = response.json()
        assert data["access_token"]
        assert data["token_type"] == "Bearer"

    async def test_login_invalid_password(self, auth_client: AsyncClient) -> None:
        """Wrong password should return 401."""
        response = await auth_client.post(
            "/api/v1/auth/login",
            json={"username": "integrationuser", "password": "WrongPass!"},
        )

        assert response.status_code == 401, response.text

    async def test_login_missing_fields(self, auth_client: AsyncClient) -> None:
        """Missing fields should return 422."""
        response = await auth_client.post("/api/v1/auth/login", json={})

        assert response.status_code == 422


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


# ─────────────────────── Microsoft SSO callback ───────────────────────


@pytest.fixture
def sso_repo() -> AsyncMock:
    """Repository where the incoming Microsoft user does not exist locally yet."""
    repo = AsyncMock()
    repo.get_by_username.return_value = None

    async def _create(user: User) -> User:
        return user

    repo.create.side_effect = _create
    return repo


def _sso_client(
    *, configured: bool = True, profile: dict[str, Any] | None = None
) -> MagicMock:
    client = MagicMock()
    client.is_configured = configured
    client.exchange_code_for_profile = AsyncMock(
        return_value=profile
        if profile is not None
        else {
            "mail": "New.User@corp.com",
            "userPrincipalName": "new.user@corp.com",
            "displayName": "New User",
        }
    )
    return client


class TestMicrosoftSsoCallback:
    """
    POST /api/v1/auth/microsoft/callback

    The auto-provisioning branch raised TypeError before this test existed: it
    constructed `User(role="USER")`, but `role` was dropped from the entity in
    migration c9d4e2f5a1b7. Any first-time SSO login returned 500.
    """

    async def test_first_login_auto_provisions_the_user(
        self, client: AsyncClient, sso_repo: AsyncMock
    ) -> None:
        app.dependency_overrides[get_user_repository] = lambda: sso_repo

        with patch(
            "src.infrastructure.external.azure_sso.AzureSsoClient",
            return_value=_sso_client(),
        ):
            response = await client.post(
                "/api/v1/auth/microsoft/callback", json={"code": "valid-code"}
            )

        assert response.status_code == 200, response.text
        assert response.json()["access_token"]
        assert response.json()["token_type"] == "Bearer"

        sso_repo.create.assert_awaited_once()
        created: User = sso_repo.create.await_args.args[0]
        assert created.username == "new.user@corp.com"  # normalised to lowercase
        assert created.is_active is True
        assert created.created_by == "microsoft_sso"

    async def test_existing_user_is_not_reprovisioned(
        self, client: AsyncClient, sso_repo: AsyncMock, active_user: User
    ) -> None:
        sso_repo.get_by_username.return_value = active_user
        app.dependency_overrides[get_user_repository] = lambda: sso_repo

        with patch(
            "src.infrastructure.external.azure_sso.AzureSsoClient",
            return_value=_sso_client(),
        ):
            response = await client.post(
                "/api/v1/auth/microsoft/callback", json={"code": "valid-code"}
            )

        assert response.status_code == 200, response.text
        sso_repo.create.assert_not_awaited()

    async def test_refresh_cookie_is_httponly_and_scoped(
        self, client: AsyncClient, sso_repo: AsyncMock
    ) -> None:
        app.dependency_overrides[get_user_repository] = lambda: sso_repo

        with patch(
            "src.infrastructure.external.azure_sso.AzureSsoClient",
            return_value=_sso_client(),
        ):
            response = await client.post(
                "/api/v1/auth/microsoft/callback", json={"code": "valid-code"}
            )

        cookie = response.headers.get("set-cookie", "")
        assert "HttpOnly" in cookie
        assert "/api/v1/auth" in cookie

    async def test_blocked_user_is_rejected(
        self, client: AsyncClient, sso_repo: AsyncMock, blocked_user: User
    ) -> None:
        sso_repo.get_by_username.return_value = blocked_user
        app.dependency_overrides[get_user_repository] = lambda: sso_repo

        with patch(
            "src.infrastructure.external.azure_sso.AzureSsoClient",
            return_value=_sso_client(),
        ):
            response = await client.post(
                "/api/v1/auth/microsoft/callback", json={"code": "valid-code"}
            )

        assert response.status_code == 403, response.text

    async def test_missing_code_returns_400(
        self, client: AsyncClient, sso_repo: AsyncMock
    ) -> None:
        app.dependency_overrides[get_user_repository] = lambda: sso_repo

        with patch(
            "src.infrastructure.external.azure_sso.AzureSsoClient",
            return_value=_sso_client(),
        ):
            response = await client.post("/api/v1/auth/microsoft/callback", json={})

        assert response.status_code == 400, response.text

    async def test_unconfigured_sso_returns_501(
        self, client: AsyncClient, sso_repo: AsyncMock
    ) -> None:
        app.dependency_overrides[get_user_repository] = lambda: sso_repo

        with patch(
            "src.infrastructure.external.azure_sso.AzureSsoClient",
            return_value=_sso_client(configured=False),
        ):
            response = await client.post(
                "/api/v1/auth/microsoft/callback", json={"code": "valid-code"}
            )

        assert response.status_code == 501, response.text

    async def test_profile_without_email_returns_400(
        self, client: AsyncClient, sso_repo: AsyncMock
    ) -> None:
        """A Graph profile with no mail or UPN cannot be mapped to a user."""
        app.dependency_overrides[get_user_repository] = lambda: sso_repo

        with patch(
            "src.infrastructure.external.azure_sso.AzureSsoClient",
            return_value=_sso_client(profile={"displayName": "No Email"}),
        ):
            response = await client.post(
                "/api/v1/auth/microsoft/callback", json={"code": "valid-code"}
            )

        assert response.status_code == 400, response.text


# ─────────────────────── Microsoft SSO login URL ───────────────────────


class TestMicrosoftLoginUrl:
    """GET /api/v1/auth/microsoft/login — the browser-redirect URL endpoint."""

    async def test_configured_sso_returns_the_authorization_url(
        self, client: AsyncClient
    ) -> None:
        with patch(
            "src.infrastructure.external.azure_sso.AzureSsoClient",
            return_value=_sso_client(),
        ) as mock_client_cls:
            mock_client_cls.return_value.build_authorization_url.return_value = (
                "https://login.microsoftonline.com/tenant/oauth2/v2.0/authorize?client_id=x",
                "http://localhost:6769/auth/microsoft/callback",
            )
            response = await client.get("/api/v1/auth/microsoft/login")

        assert response.status_code == 200, response.text
        body = response.json()
        assert body["auth_url"].startswith("https://login.microsoftonline.com")
        assert body["redirect_uri"] == "http://localhost:6769/auth/microsoft/callback"

    async def test_unconfigured_sso_returns_501(self, client: AsyncClient) -> None:
        with patch(
            "src.infrastructure.external.azure_sso.AzureSsoClient",
            return_value=_sso_client(configured=False),
        ):
            response = await client.get("/api/v1/auth/microsoft/login")

        assert response.status_code == 501, response.text


# ─────────────────────── /auth/refresh ───────────────────────


class TestRefreshTokenAPI:
    """POST /api/v1/auth/refresh — exchanges the HttpOnly refresh cookie for a new access token."""

    async def test_missing_cookie_returns_401(self, client: AsyncClient) -> None:
        response = await client.post("/api/v1/auth/refresh")

        assert response.status_code == 401, response.text
        assert "Missing refresh token" in response.json()["detail"]

    async def test_valid_cookie_returns_a_new_access_token(
        self, client: AsyncClient, mock_user_repo: AsyncMock, active_user: User
    ) -> None:
        from src.infrastructure.security.jwt_provider import JWTProvider

        app.dependency_overrides[get_user_repository] = lambda: mock_user_repo
        refresh_token = JWTProvider().create_refresh_token(active_user.username, active_user.id)
        client.cookies.set("refresh_token", refresh_token)

        response = await client.post("/api/v1/auth/refresh")

        assert response.status_code == 200, response.text
        assert response.json()["access_token"]
        assert response.json()["token_type"] == "Bearer"

    async def test_garbage_cookie_returns_401_and_clears_it(
        self, client: AsyncClient
    ) -> None:
        client.cookies.set("refresh_token", "not-a-real-token")

        response = await client.post("/api/v1/auth/refresh")

        assert response.status_code == 401, response.text
        # The stale cookie is cleared so the client stops retrying with it.
        set_cookie = response.headers.get("set-cookie", "")
        assert "refresh_token=" in set_cookie

    async def test_blocked_user_refresh_returns_403(
        self, client: AsyncClient, mock_user_repo: AsyncMock, blocked_user: User
    ) -> None:
        from src.infrastructure.security.jwt_provider import JWTProvider

        mock_user_repo.get_by_username.return_value = blocked_user
        app.dependency_overrides[get_user_repository] = lambda: mock_user_repo
        refresh_token = JWTProvider().create_refresh_token(blocked_user.username, blocked_user.id)
        client.cookies.set("refresh_token", refresh_token)

        response = await client.post("/api/v1/auth/refresh")

        assert response.status_code == 403, response.text


# ─────────────────────── /auth/me ───────────────────────


class TestGetMeAPI:
    """GET /api/v1/auth/me — the authenticated caller's own profile."""

    async def test_anonymous_request_is_rejected(self, client: AsyncClient) -> None:
        response = await client.get("/api/v1/auth/me")

        assert response.status_code in (401, 403), response.text

    async def test_authenticated_request_returns_the_profile_without_a_password_hash(
        self, client: AsyncClient, mock_user_repo: AsyncMock, active_user: User
    ) -> None:
        from src.infrastructure.security.jwt_provider import JWTProvider

        app.dependency_overrides[get_user_repository] = lambda: mock_user_repo
        token = JWTProvider().create_access_token(active_user.username, active_user.id)
        client.headers["Authorization"] = f"Bearer {token}"

        response = await client.get("/api/v1/auth/me")

        assert response.status_code == 200, response.text
        body = response.json()
        assert body["username"] == active_user.username
        assert body["is_active"] is True
        assert "password_hash" not in body


# ─────────────────────── /auth/logout ───────────────────────


class TestLogoutAPI:
    """POST /api/v1/auth/logout — records the event and clears the refresh cookie."""

    async def test_anonymous_request_is_rejected(self, client: AsyncClient) -> None:
        response = await client.post("/api/v1/auth/logout")

        assert response.status_code in (401, 403), response.text

    async def test_authenticated_logout_clears_the_refresh_cookie(
        self, client: AsyncClient, mock_user_repo: AsyncMock, active_user: User
    ) -> None:
        from src.infrastructure.security.jwt_provider import JWTProvider

        app.dependency_overrides[get_user_repository] = lambda: mock_user_repo
        token = JWTProvider().create_access_token(active_user.username, active_user.id)
        client.headers["Authorization"] = f"Bearer {token}"

        response = await client.post("/api/v1/auth/logout")

        assert response.status_code == 200, response.text
        assert response.json()["detail"] == "Logged out successfully"
        set_cookie = response.headers.get("set-cookie", "")
        assert "refresh_token=" in set_cookie
