"""
Integration tests for the RBAC API.

Written before refactoring RbacService so they act as a behavioural baseline:
the same assertions must hold after the service stops committing internally.

Note these endpoints guard with `require_permission("rbac.read")` etc. — matched
on permission code — unlike the masters, which use (resource, action).
"""

from typing import Any

from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.domain.entities.user import User

PERMISSIONS = "/api/v1/rbac/permissions"
ROLES = "/api/v1/rbac/roles"
GRANT = "/api/v1/rbac/roles/grant-permission"
REVOKE_PERMISSION = "/api/v1/rbac/roles/revoke-permission"
ASSIGNMENTS = "/api/v1/rbac/assignments"
REVOKE_ROLE = "/api/v1/rbac/assignments/revoke"

UNKNOWN_ID = 999_999


async def _create_role(client: AsyncClient, code: str = "AUDITOR") -> dict[str, Any]:
    response = await client.post(
        ROLES, json={"code": code, "name": f"{code.title()} role"}
    )
    assert response.status_code == 201, response.text
    created: dict[str, Any] = response.json()
    return created


async def _create_permission(
    client: AsyncClient, code: str = "reports.export"
) -> dict[str, Any]:
    response = await client.post(
        PERMISSIONS,
        json={
            "code": code,
            "name": "Export reports",
            "scope": "API",
            "resource": "reports",
            "action": "EXPORT",
        },
    )
    assert response.status_code == 201, response.text
    created: dict[str, Any] = response.json()
    return created


class TestAuthorization:
    async def test_anonymous_cannot_list_permissions(self, client: AsyncClient) -> None:
        response = await client.get(PERMISSIONS)
        assert response.status_code in (401, 403), response.text

    async def test_anonymous_cannot_create_role(self, client: AsyncClient) -> None:
        response = await client.post(ROLES, json={"code": "X", "name": "X"})
        assert response.status_code in (401, 403), response.text


class TestPermissions:
    async def test_list_includes_seeded_permissions(self, admin_client: AsyncClient) -> None:
        response = await admin_client.get(PERMISSIONS)

        assert response.status_code == 200, response.text
        codes = {p["code"] for p in response.json()}
        assert "rbac.read" in codes
        assert "countries.create" in codes

    async def test_list_filtered_by_scope(self, admin_client: AsyncClient) -> None:
        response = await admin_client.get(PERMISSIONS, params={"scope": "API"})

        assert response.status_code == 200, response.text
        assert all(p["scope"] == "API" for p in response.json())

    async def test_invalid_scope_returns_422(self, admin_client: AsyncClient) -> None:
        response = await admin_client.get(PERMISSIONS, params={"scope": "NOPE"})
        assert response.status_code == 422

    async def test_create_permission(self, admin_client: AsyncClient) -> None:
        permission = await _create_permission(admin_client)

        assert permission["code"] == "reports.export"
        assert permission["scope"] == "API"
        assert permission["is_active"] is True

    async def test_duplicate_code_returns_409(self, admin_client: AsyncClient) -> None:
        await _create_permission(admin_client)

        response = await admin_client.post(
            PERMISSIONS,
            json={
                "code": "reports.export",
                "name": "Duplicate",
                "scope": "API",
                "resource": "reports",
                "action": "EXPORT",
            },
        )

        assert response.status_code == 409, response.text


class TestRoles:
    async def test_create_role(self, admin_client: AsyncClient) -> None:
        role = await _create_role(admin_client)

        assert role["code"] == "AUDITOR"
        assert role["is_system"] is False
        assert role["is_active"] is True
        assert role["permissions"] == []

    async def test_duplicate_code_returns_409(self, admin_client: AsyncClient) -> None:
        await _create_role(admin_client)

        response = await admin_client.post(
            ROLES, json={"code": "AUDITOR", "name": "Another"}
        )

        assert response.status_code == 409, response.text

    async def test_list_roles(self, admin_client: AsyncClient) -> None:
        await _create_role(admin_client)

        response = await admin_client.get(ROLES)

        assert response.status_code == 200, response.text
        body = response.json()
        codes = {r["code"] for r in body["roles"]}
        assert {"ADMIN_TEST", "AUDITOR"} <= codes
        assert body["total"] == len(body["roles"])

    async def test_update_role(self, admin_client: AsyncClient) -> None:
        role = await _create_role(admin_client)

        response = await admin_client.patch(
            f"{ROLES}/{role['id']}",
            json={"name": "Senior Auditor", "description": "Read-only reviewer"},
        )

        assert response.status_code == 200, response.text
        assert response.json()["name"] == "Senior Auditor"

    async def test_system_role_cannot_be_modified(self, admin_client: AsyncClient) -> None:
        """The seeded ADMIN_TEST role is a system role, so it is protected."""
        listed = await admin_client.get(ROLES)
        system_role = next(
            r for r in listed.json()["roles"] if r["code"] == "ADMIN_TEST"
        )

        response = await admin_client.patch(
            f"{ROLES}/{system_role['id']}", json={"name": "Hijacked"}
        )

        assert response.status_code == 403, response.text

    async def test_update_unknown_role_returns_404(self, admin_client: AsyncClient) -> None:
        response = await admin_client.patch(
            f"{ROLES}/{UNKNOWN_ID}", json={"name": "Ghost"}
        )
        assert response.status_code == 404, response.text


class TestGrantAndRevokePermission:
    async def test_grant_then_duplicate_then_revoke(self, admin_client: AsyncClient) -> None:
        role = await _create_role(admin_client)
        permission = await _create_permission(admin_client)
        payload = {"role_id": role["id"], "permission_id": permission["id"]}

        granted = await admin_client.post(GRANT, json=payload)
        assert granted.status_code == 201, granted.text

        # The grant is visible on the role
        listed = await admin_client.get(ROLES)
        target = next(r for r in listed.json()["roles"] if r["id"] == role["id"])
        assert permission["id"] in {p["id"] for p in target["permissions"]}

        duplicate = await admin_client.post(GRANT, json=payload)
        assert duplicate.status_code == 409, duplicate.text

        revoked = await admin_client.post(REVOKE_PERMISSION, json=payload)
        assert revoked.status_code == 200, revoked.text

        # Revoking twice is a 404 because the link has gone
        again = await admin_client.post(REVOKE_PERMISSION, json=payload)
        assert again.status_code == 404, again.text

    async def test_grant_unknown_role_returns_404(self, admin_client: AsyncClient) -> None:
        permission = await _create_permission(admin_client)

        response = await admin_client.post(
            GRANT, json={"role_id": UNKNOWN_ID, "permission_id": permission["id"]}
        )

        assert response.status_code == 404, response.text

    async def test_grant_unknown_permission_returns_404(self, admin_client: AsyncClient) -> None:
        role = await _create_role(admin_client)

        response = await admin_client.post(
            GRANT, json={"role_id": role["id"], "permission_id": UNKNOWN_ID}
        )

        assert response.status_code == 404, response.text


class TestRoleAssignment:
    async def test_assign_then_duplicate_then_revoke(
        self, admin_client: AsyncClient, admin_user: User
    ) -> None:
        role = await _create_role(admin_client)
        payload = {"user_id": admin_user.id, "role_id": role["id"]}

        assigned = await admin_client.post(ASSIGNMENTS, json=payload)
        assert assigned.status_code == 201, assigned.text
        body = assigned.json()
        assert body["user_id"] == admin_user.id
        assert body["is_active"] is True

        duplicate = await admin_client.post(ASSIGNMENTS, json=payload)
        assert duplicate.status_code == 409, duplicate.text

        revoked = await admin_client.post(REVOKE_ROLE, json=payload)
        assert revoked.status_code == 200, revoked.text

        again = await admin_client.post(REVOKE_ROLE, json=payload)
        assert again.status_code == 404, again.text

    async def test_assign_unknown_role_returns_404(self, admin_client: AsyncClient) -> None:
        response = await admin_client.post(
            ASSIGNMENTS, json={"user_id": 999_999, "role_id": UNKNOWN_ID}
        )
        assert response.status_code == 404, response.text


class TestAuditTrail:
    """RBAC changes must leave an audit record."""

    async def test_role_creation_is_audited(
        self, admin_client: AsyncClient, db_session: AsyncSession
    ) -> None:
        from src.infrastructure.database.models.audit_log_model import AuditLogModel

        role = await _create_role(admin_client)

        rows = (
            (
                await db_session.execute(
                    select(AuditLogModel).where(
                        AuditLogModel.resource_id == str(role["id"])
                    )
                )
            )
            .scalars()
            .all()
        )

        assert rows, "expected an audit row for the created role"
        # Two rows exist: the automatic before-flush listener records the raw
        # INSERT, and RbacService records ROLE_CREATED attributed to the actor.
        # Assert on content rather than position — the query has no ORDER BY.
        assert any(
            r.action == "ROLE_CREATED" and r.actor_username == "admin-test" for r in rows
        ), [(r.action, r.actor_username) for r in rows]

    async def test_permission_grant_is_audited(
        self, admin_client: AsyncClient, db_session: AsyncSession
    ) -> None:
        from src.infrastructure.database.models.audit_log_model import AuditLogModel

        role = await _create_role(admin_client)
        permission = await _create_permission(admin_client)

        await admin_client.post(
            GRANT, json={"role_id": role["id"], "permission_id": permission["id"]}
        )

        actions = (
            (
                await db_session.execute(
                    select(AuditLogModel.action).where(
                        AuditLogModel.actor_username == "admin-test"
                    )
                )
            )
            .scalars()
            .all()
        )

        assert any("PERMISSION" in a for a in actions), actions


class TestMyPermissions:
    """
    The self-service permission endpoints the frontend reads.

    `/my-permissions/all` returned a 500 before this suite existed: it read
    `current_user.role`, a field dropped in migration c9d4e2f5a1b7 when RBAC
    replaced the single-role column. Nothing caught it because the module was
    exempt from strict type checking and had no tests.
    """

    async def test_menu_permissions(self, admin_client: AsyncClient) -> None:
        response = await admin_client.get("/api/v1/rbac/my-permissions/menu")

        assert response.status_code == 200, response.text
        body = response.json()
        assert "masters" in body["menu_keys"]
        assert all(p["scope"] == "MENU" for p in body["permissions"])

    async def test_all_permissions(
        self, admin_client: AsyncClient, admin_user: User
    ) -> None:
        response = await admin_client.get("/api/v1/rbac/my-permissions/all")

        assert response.status_code == 200, response.text
        body = response.json()
        assert body["username"] == "admin-test"
        assert body["user_id"] == admin_user.id
        assert "legacy_role" not in body, "removed with the single-role column"
        assert body["total_effective_permissions"] > 0
        assert {r["code"] for r in body["assigned_roles"]} == {"ADMIN_TEST"}

    async def test_field_permissions(self, admin_client: AsyncClient) -> None:
        response = await admin_client.get("/api/v1/rbac/my-permissions/fields/users")

        assert response.status_code == 200, response.text
        body = response.json()
        assert body["resource"] == "users"
        assert body["fields"].get("salary") == ["READ"]

    async def test_anonymous_cannot_read_own_permissions(self, client: AsyncClient) -> None:
        response = await client.get("/api/v1/rbac/my-permissions/menu")
        assert response.status_code in (401, 403), response.text


class TestAuditLogsEndpoint:
    async def test_audit_logs_listing(self, admin_client: AsyncClient) -> None:
        """Creating a role should show up in the audit log listing."""
        await _create_role(admin_client, code="LISTED")

        response = await admin_client.get("/api/v1/rbac/audit-logs")

        assert response.status_code == 200, response.text
        body = response.json()
        assert body["total"] >= 1
        assert any(log["actor_username"] == "admin-test" for log in body["logs"])
