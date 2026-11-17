"""
Integration tests for the user management API.

Written to cover UserService after it was refactored onto repository ports —
these endpoints previously had no tests at all, so nothing would have caught a
regression in the extraction.
"""

from typing import Any

from httpx import AsyncClient

from src.domain.entities.user import User

USERS = "/api/v1/users"
ROLES = "/api/v1/rbac/roles"
UNKNOWN_ID = 999999


async def _create_user(
    client: AsyncClient, username: str = "new.user", role_id: str | None = None
) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "username": username,
        "password": "StrongPass123!",
        "is_validate_ad": False,
    }
    if role_id:
        payload["role_id"] = role_id
    response = await client.post(USERS, json=payload)
    assert response.status_code == 201, response.text
    created: dict[str, Any] = response.json()
    return created


class TestAuthorization:
    async def test_anonymous_cannot_list_users(self, client: AsyncClient) -> None:
        response = await client.get(USERS)
        assert response.status_code in (401, 403), response.text


class TestListAndGet:
    async def test_list_includes_the_seeded_admin(self, admin_client: AsyncClient) -> None:
        response = await admin_client.get(USERS)

        assert response.status_code == 200, response.text
        body = response.json()
        assert body["skip"] == 0
        assert any(u["username"] == "admin-test" for u in body["users"])

    async def test_list_respects_pagination_params(self, admin_client: AsyncClient) -> None:
        await _create_user(admin_client, username="page.one")

        response = await admin_client.get(USERS, params={"skip": 0, "limit": 1})

        assert response.status_code == 200, response.text
        body = response.json()
        assert len(body["users"]) == 1
        assert body["limit"] == 1

    async def test_get_by_id(
        self, admin_client: AsyncClient, admin_user: User
    ) -> None:
        response = await admin_client.get(f"{USERS}/{admin_user.id}")

        assert response.status_code == 200, response.text
        assert response.json()["username"] == "admin-test"

    async def test_unknown_id_returns_404(self, admin_client: AsyncClient) -> None:
        response = await admin_client.get(f"{USERS}/{UNKNOWN_ID}")
        assert response.status_code == 404, response.text


class TestCreateAndUpdate:
    async def test_create_user(self, admin_client: AsyncClient) -> None:
        created = await _create_user(admin_client)

        assert created["username"] == "new.user"
        assert created["is_active"] is True
        assert created["is_blocked"] is False
        assert created["created_by"] == "admin-test"

    async def test_duplicate_username_returns_409(self, admin_client: AsyncClient) -> None:
        await _create_user(admin_client, username="dupe.user")

        response = await admin_client.post(
            USERS,
            json={
                "username": "dupe.user",
                "password": "StrongPass123!",
                "is_validate_ad": False,
            },
        )

        assert response.status_code == 409, response.text

    async def test_create_with_role_assigns_it(self, admin_client: AsyncClient) -> None:
        role = (
            await admin_client.post(ROLES, json={"code": "REVIEWER", "name": "Reviewer"})
        ).json()

        created = await _create_user(
            admin_client, username="with.role", role_id=role["id"]
        )

        roles = await admin_client.get(f"{USERS}/{created['id']}/roles")
        assert roles.status_code == 200, roles.text
        assert [r["code"] for r in roles.json()["roles"]] == ["REVIEWER"]

    async def test_patch_blocks_user(self, admin_client: AsyncClient) -> None:
        created = await _create_user(admin_client, username="to.block")

        response = await admin_client.patch(
            f"{USERS}/{created['id']}", json={"is_blocked": True}
        )

        assert response.status_code == 200, response.text
        assert response.json()["is_blocked"] is True
        assert response.json()["modified_by"] == "admin-test"

    async def test_patch_unknown_user_returns_404(self, admin_client: AsyncClient) -> None:
        response = await admin_client.patch(
            f"{USERS}/{UNKNOWN_ID}", json={"is_blocked": True}
        )
        assert response.status_code == 404, response.text

    async def test_patch_role_replaces_the_previous_one(self, admin_client: AsyncClient) -> None:
        """Supplying role_id should leave exactly one active assignment."""
        first = (
            await admin_client.post(ROLES, json={"code": "ROLE_A", "name": "Role A"})
        ).json()
        second = (
            await admin_client.post(ROLES, json={"code": "ROLE_B", "name": "Role B"})
        ).json()

        created = await _create_user(
            admin_client, username="swap.role", role_id=first["id"]
        )

        patched = await admin_client.patch(
            f"{USERS}/{created['id']}", json={"role_id": second["id"]}
        )
        assert patched.status_code == 200, patched.text

        roles = await admin_client.get(f"{USERS}/{created['id']}/roles")
        assert [r["code"] for r in roles.json()["roles"]] == ["ROLE_B"]


class TestDetailsRolesAndHistory:
    async def test_details_returns_nulls_without_a_profile(
        self, admin_client: AsyncClient
    ) -> None:
        """A user with no user_details row still resolves, with empty AD fields."""
        created = await _create_user(admin_client, username="no.profile")

        response = await admin_client.get(f"{USERS}/{created['id']}/details")

        assert response.status_code == 200, response.text
        body = response.json()
        assert body["username"] == "no.profile"
        assert body["employee_id"] is None
        assert body["department"] is None

    async def test_details_unknown_user_returns_404(self, admin_client: AsyncClient) -> None:
        response = await admin_client.get(f"{USERS}/{UNKNOWN_ID}/details")
        assert response.status_code == 404, response.text

    async def test_roles_empty_when_none_assigned(self, admin_client: AsyncClient) -> None:
        created = await _create_user(admin_client, username="no.roles")

        response = await admin_client.get(f"{USERS}/{created['id']}/roles")

        assert response.status_code == 200, response.text
        assert response.json() == {"user_id": created["id"], "roles": []}

    async def test_roles_include_permissions(
        self, admin_client: AsyncClient, admin_user: User
    ) -> None:
        """The seeded admin's role carries its granted permissions."""
        response = await admin_client.get(f"{USERS}/{admin_user.id}/roles")

        assert response.status_code == 200, response.text
        roles = response.json()["roles"]
        assert [r["code"] for r in roles] == ["ADMIN_TEST"]
        codes = {p["code"] for p in roles[0]["permissions"]}
        assert "users.read" in codes

    async def test_login_history_is_empty_for_a_fresh_user(
        self, admin_client: AsyncClient
    ) -> None:
        created = await _create_user(admin_client, username="never.logged.in")

        response = await admin_client.get(f"{USERS}/{created['id']}/login-history")

        assert response.status_code == 200, response.text
        assert response.json() == []

    async def test_login_history_records_a_successful_login(
        self, admin_client: AsyncClient, admin_user: User
    ) -> None:
        """Logging in writes an audit row that surfaces as login history."""
        login = await admin_client.post(
            "/api/v1/auth/login",
            json={"username": "admin-test", "password": "AdminPass123!"},
        )
        assert login.status_code == 200, login.text

        response = await admin_client.get(f"{USERS}/{admin_user.id}/login-history")

        assert response.status_code == 200, response.text
        entries = response.json()
        assert entries, "expected the login to appear in history"
        assert entries[0]["action"] == "LOGIN_SUCCESS"
        assert entries[0]["created_at"]
