"""
Unit tests for the Vendor Master controller.

These exercise the thin controller's real responsibilities — request → service
input translation, entity → response shaping, pagination envelope, the
deactivate route, and the master-exception → HTTP status mapping (422/409/404).

A minimal FastAPI app mounts only the vendor router so the suite is independent
of sibling master controllers and of a live database. The ``VendorService`` is
replaced with an in-memory fake (no mocking of the behaviour under test), the
actor/session dependencies are overridden, and the RBAC check is forced to
allow so we test the controller layer in isolation.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, patch
from uuid import UUID, uuid4

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from src.api.v1.dependencies import get_current_active_user
from src.api.v1.endpoints.masters.vendor_controller import (
    _get_vendor_service,
    router as vendor_router,
)
from src.application.exceptions.application_exceptions import (
    MasterConflictError,
    MasterNotFoundError,
    MasterValidationError,
)
from src.domain.entities.masters.vendor import VendorEntity
from src.domain.entities.user import User
from src.domain.enums.masters import VendorStatus
from src.infrastructure.database.session import get_db_session


def _make_vendor(**overrides) -> VendorEntity:
    """Build a VendorEntity with sensible defaults for response shaping."""
    base = dict(
        id=uuid4(),
        vendor_code="V001",
        vendor_name="Acme Liaisons",
        vendor_email="acme@example.com",
        status=VendorStatus.Active,
    )
    base.update(overrides)
    return VendorEntity(**base)


class FakeVendorService:
    """Configurable stand-in for VendorService driving controller behaviour."""

    def __init__(self) -> None:
        self.created: VendorEntity | None = None
        self.list_result: tuple[list[VendorEntity], int] = ([], 0)
        self.raise_on: dict[str, Exception] = {}
        self.last_list_args: tuple[int, int] | None = None

    async def list_vendors(self, skip: int = 0, limit: int = 20):
        self.last_list_args = (skip, limit)
        if "list" in self.raise_on:
            raise self.raise_on["list"]
        return self.list_result

    async def create_vendor(self, data, actor):
        if "create" in self.raise_on:
            raise self.raise_on["create"]
        self.created = _make_vendor(
            vendor_code=data.vendor_code,
            vendor_name=data.vendor_name,
            vendor_email=data.vendor_email,
        )
        return self.created

    async def get_vendor(self, vendor_id: UUID):
        if "get" in self.raise_on:
            raise self.raise_on["get"]
        return _make_vendor(id=vendor_id)

    async def update_vendor(self, vendor_id: UUID, patch, actor):
        if "update" in self.raise_on:
            raise self.raise_on["update"]
        name = patch.vendor_name if isinstance(patch.vendor_name, str) else "Acme Liaisons"
        return _make_vendor(id=vendor_id, vendor_name=name)

    async def deactivate_vendor(self, vendor_id: UUID, actor):
        if "deactivate" in self.raise_on:
            raise self.raise_on["deactivate"]
        return _make_vendor(id=vendor_id, status=VendorStatus.Inactive)


@pytest.fixture
def fake_service() -> FakeVendorService:
    return FakeVendorService()


@pytest.fixture
def client(fake_service):
    """Async client over an app that mounts only the vendor router."""
    app = FastAPI()
    app.include_router(vendor_router, prefix="/api/v1")

    actor = User(
        id=uuid4(),
        username="admin",
        is_active=True,
        is_blocked=False,
    )

    app.dependency_overrides[_get_vendor_service] = lambda: fake_service
    app.dependency_overrides[get_current_active_user] = lambda: actor
    app.dependency_overrides[get_db_session] = lambda: object()

    transport = ASGITransport(app=app)
    return AsyncClient(transport=transport, base_url="http://test")


# RBAC is enforced via PermissionManager.has_api_access; force-allow it.
def _allow_rbac():
    return patch(
        "src.infrastructure.security.permission_manager.PermissionManager.has_api_access",
        new=AsyncMock(return_value=True),
    )


@pytest.mark.asyncio
class TestVendorController:
    async def test_list_returns_paginated_envelope(self, client, fake_service):
        vendors = [_make_vendor(vendor_code=f"V{i}") for i in range(3)]
        fake_service.list_result = (vendors, 7)
        with _allow_rbac():
            async with client as c:
                resp = await c.get("/api/v1/vendors", params={"skip": 0, "limit": 20})
        assert resp.status_code == 200
        body = resp.json()
        assert body["total"] == 7
        assert body["skip"] == 0
        assert body["limit"] == 20
        assert len(body["items"]) == 3
        assert fake_service.last_list_args == (0, 20)

    async def test_list_rejects_out_of_range_limit(self, client, fake_service):
        with _allow_rbac():
            async with client as c:
                resp = await c.get("/api/v1/vendors", params={"limit": 500})
        # Pagination bounds enforced at the Query boundary (Req 6.12).
        assert resp.status_code == 422

    async def test_list_rejects_negative_skip(self, client, fake_service):
        with _allow_rbac():
            async with client as c:
                resp = await c.get("/api/v1/vendors", params={"skip": -1})
        assert resp.status_code == 422

    async def test_create_returns_201(self, client, fake_service):
        with _allow_rbac():
            async with client as c:
                resp = await c.post(
                    "/api/v1/vendors",
                    json={
                        "vendor_code": "V123",
                        "vendor_name": "New Vendor",
                        "vendor_email": "new@example.com",
                    },
                )
        assert resp.status_code == 201
        assert resp.json()["vendor_code"] == "V123"

    async def test_create_validation_error_maps_to_422(self, client, fake_service):
        fake_service.raise_on["create"] = MasterValidationError(
            "vendor_email", "Vendor Email is not a valid email address"
        )
        with _allow_rbac():
            async with client as c:
                resp = await c.post(
                    "/api/v1/vendors",
                    json={
                        "vendor_code": "V1",
                        "vendor_name": "X",
                        "vendor_email": "bad",
                    },
                )
        assert resp.status_code == 422
        assert resp.json()["detail"]["field"] == "vendor_email"

    async def test_create_conflict_maps_to_409(self, client, fake_service):
        fake_service.raise_on["create"] = MasterConflictError(
            "A Vendor with code 'V1' already exists"
        )
        with _allow_rbac():
            async with client as c:
                resp = await c.post(
                    "/api/v1/vendors",
                    json={
                        "vendor_code": "V1",
                        "vendor_name": "X",
                        "vendor_email": "x@example.com",
                    },
                )
        assert resp.status_code == 409

    async def test_get_not_found_maps_to_404(self, client, fake_service):
        fake_service.raise_on["get"] = MasterNotFoundError("Vendor", uuid4())
        with _allow_rbac():
            async with client as c:
                resp = await c.get(f"/api/v1/vendors/{uuid4()}")
        assert resp.status_code == 404

    async def test_get_returns_vendor(self, client, fake_service):
        vid = uuid4()
        with _allow_rbac():
            async with client as c:
                resp = await c.get(f"/api/v1/vendors/{vid}")
        assert resp.status_code == 200
        assert resp.json()["id"] == str(vid)

    async def test_update_partial_applies_supplied_fields(self, client, fake_service):
        vid = uuid4()
        with _allow_rbac():
            async with client as c:
                resp = await c.patch(
                    f"/api/v1/vendors/{vid}",
                    json={"vendor_name": "Renamed"},
                )
        assert resp.status_code == 200
        assert resp.json()["vendor_name"] == "Renamed"

    async def test_update_not_found_maps_to_404(self, client, fake_service):
        fake_service.raise_on["update"] = MasterNotFoundError("Vendor", uuid4())
        with _allow_rbac():
            async with client as c:
                resp = await c.patch(
                    f"/api/v1/vendors/{uuid4()}",
                    json={"vendor_name": "Renamed"},
                )
        assert resp.status_code == 404

    async def test_deactivate_sets_inactive(self, client, fake_service):
        vid = uuid4()
        with _allow_rbac():
            async with client as c:
                resp = await c.post(f"/api/v1/vendors/{vid}/deactivate")
        assert resp.status_code == 200
        assert resp.json()["status"] == VendorStatus.Inactive.value

    async def test_deactivate_not_found_maps_to_404(self, client, fake_service):
        fake_service.raise_on["deactivate"] = MasterNotFoundError("Vendor", uuid4())
        with _allow_rbac():
            async with client as c:
                resp = await c.post(f"/api/v1/vendors/{uuid4()}/deactivate")
        assert resp.status_code == 404
