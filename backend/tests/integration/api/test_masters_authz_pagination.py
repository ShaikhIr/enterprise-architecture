"""
Integration tests for master-endpoint authorisation and pagination bounds
(Task 15.4, non-property criteria exercised through the FastAPI app).

Covered here (the remaining service-level edge cases live in
``tests/unit/application/masters/test_non_property_edge_cases.py``):

* Out-of-range pagination rejected at the ``Query`` boundary -> 422 ... Req 1.10, 6.12
* A request without a valid authenticated session -> 401 ............... Req 20.2
* An authenticated user lacking the permission -> 403 ................. Req 20.3

The full request/response cycle runs through ``src.main.app`` with FastAPI
dependency overrides standing in for the database session and the authenticated
user, mirroring the override/patch style of ``tests/integration/test_auth_api.py``
while keeping the tests free of a live database.
"""

from __future__ import annotations

from uuid import uuid4

import pytest
from httpx import ASGITransport, AsyncClient

from src.api.v1.dependencies import get_current_active_user
from src.api.v1.endpoints.masters.entity_controller import _get_entity_service
from src.domain.entities.role import PermissionScope
from src.domain.entities.user import User
from src.infrastructure.database.models.role_model import (
    RoleAssignmentModel,
    RoleModel,
)
from src.infrastructure.database.session import get_db_session
from src.main import app

pytestmark = pytest.mark.asyncio


# ─── Fakes standing in for the database session / permission store ───


class _FakeScalars:
    def __init__(self, rows: list) -> None:
        self._rows = rows

    def all(self) -> list:
        return self._rows


class _FakeResult:
    def __init__(self, rows: list) -> None:
        self._rows = rows

    def scalars(self) -> _FakeScalars:
        return _FakeScalars(self._rows)


class _FakePermission:
    """Duck-typed stand-in for a ``PermissionModel`` row."""

    def __init__(self, resource: str, action: str) -> None:
        self.id = uuid4()
        self.is_active = True
        self.scope = PermissionScope.API
        self.resource = resource
        self.action = action
        self.code = f"{resource}.{action}"


class _FakeRole:
    def __init__(self, permissions: list[_FakePermission]) -> None:
        self.permissions = permissions
        self.parent_role_id = None


class _FakeAssignment:
    def __init__(self, role_id) -> None:  # noqa: ANN001
        self.role_id = role_id
        self.is_active = True


class _PermissionSession:
    """Async-session stand-in answering the PermissionManager's two queries.

    When ``grant`` is true it returns one role assignment and a role carrying an
    API permission for ``resource``/``action``; otherwise it reports no role
    assignments, so the user has no effective permissions.
    """

    def __init__(self, *, grant: bool, resource: str = "entities", action: str = "READ") -> None:
        self._grant = grant
        self._resource = resource
        self._action = action

    async def execute(self, stmt):  # noqa: ANN001 - SQLAlchemy statement
        entity = stmt.column_descriptions[0]["entity"]
        if entity is RoleAssignmentModel:
            if not self._grant:
                return _FakeResult([])
            return _FakeResult([_FakeAssignment(role_id=uuid4())])
        if entity is RoleModel:
            perm = _FakePermission(self._resource, self._action)
            return _FakeResult([_FakeRole([perm])])
        return _FakeResult([])


def _active_user() -> User:
    return User(
        id=uuid4(),
        username="permitted",
        password_hash="x",
        is_active=True,
        is_blocked=False,
    )


class _StubEntityService:
    """Stub service so the endpoint body never touches a real database."""

    async def list_entities(
        self, skip: int = 0, limit: int = 20, search=None, is_active=None
    ):  # noqa: ANN001
        return [], 0


def _override_db(session: _PermissionSession):
    async def _dep():
        yield session

    return _dep


async def _get(path: str, *, headers: dict | None = None):
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        return await client.get(path, headers=headers)


# ─── Req 1.10 / 6.12 — pagination bounds rejected at the Query boundary ───


@pytest.mark.parametrize(
    "query",
    [
        "skip=-1",            # skip below 0
        "limit=0",            # limit below the lower bound
        "limit=101",          # limit above the upper bound
        "skip=-5&limit=200",  # both out of range
    ],
)
async def test_out_of_range_pagination_rejected(query: str) -> None:
    """Req 1.10/6.12: out-of-range skip/limit yields a 422 validation error."""
    user = _active_user()
    app.dependency_overrides[get_current_active_user] = lambda: user
    app.dependency_overrides[get_db_session] = _override_db(
        _PermissionSession(grant=True)
    )
    try:
        response = await _get(f"/api/v1/entities?{query}")
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 422


async def test_in_range_pagination_passes_validation() -> None:
    """Boundary contrast: limit=100 / skip=0 are accepted (not a 422)."""
    user = _active_user()
    app.dependency_overrides[get_current_active_user] = lambda: user
    app.dependency_overrides[get_db_session] = _override_db(
        _PermissionSession(grant=True)
    )
    app.dependency_overrides[_get_entity_service] = lambda: _StubEntityService()
    try:
        response = await _get("/api/v1/entities?skip=0&limit=100")
    finally:
        app.dependency_overrides.clear()

    # The in-range values are accepted at the Query boundary, so the request
    # reaches the (stubbed) handler and succeeds rather than being rejected 422.
    assert response.status_code == 200


# ─── Req 20.2 — no valid authenticated session -> 401 ───


async def test_missing_valid_session_returns_401() -> None:
    """Req 20.2: a request without a valid session is rejected with 401."""
    # Provide a dummy DB session so dependency wiring does not touch a real DB;
    # the invalid token is rejected before the session is ever used.
    app.dependency_overrides[get_db_session] = _override_db(
        _PermissionSession(grant=True)
    )
    try:
        response = await _get(
            "/api/v1/entities",
            headers={"Authorization": "Bearer not-a-valid-token"},
        )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 401


# ─── Req 20.3 — authenticated but lacking the permission -> 403 ───


async def test_insufficient_permission_returns_403() -> None:
    """Req 20.3: an authenticated user without the permission is rejected with 403."""
    user = _active_user()
    app.dependency_overrides[get_current_active_user] = lambda: user
    # The permission store grants nothing for this user.
    app.dependency_overrides[get_db_session] = _override_db(
        _PermissionSession(grant=False)
    )
    try:
        response = await _get("/api/v1/entities")
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 403
