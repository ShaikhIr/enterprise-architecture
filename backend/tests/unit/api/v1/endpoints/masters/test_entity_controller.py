"""
Unit tests for the Entity Master controller.

The controller is intentionally thin, so these tests exercise its two real
responsibilities in isolation (without standing up the FastAPI app, which is
wired in a later task):

* request/response schema adaptation to/from the Pydantic-agnostic service, and
* master-exception-to-HTTP-status mapping (422 / 409 / 404).

The async route handlers are invoked directly with a fake service.
"""

from __future__ import annotations

from datetime import datetime, timezone
from uuid import uuid4

import pytest
from fastapi import HTTPException, status

from src.api.v1.endpoints.masters import entity_controller as ctrl
from src.api.v1.schemas.masters.entity import (
    CreateEntityRequest,
    UpdateEntityRequest,
)
from src.application.exceptions.application_exceptions import (
    MasterConflictError,
    MasterNotFoundError,
    MasterValidationError,
)
from src.application.services.masters.entity_service import (
    UNSET,
    EntityDropdownItem,
)
from src.domain.entities.masters.entity import EntityEntity
from src.domain.entities.user import User


def _entity(**overrides) -> EntityEntity:
    defaults = dict(
        id=uuid4(),
        entity_name="Acme Corp",
        short_code="ACME",
        company_code="C001",
        is_active=True,
        created_by="tester",
        created_date=datetime.now(timezone.utc),
        modified_by="tester",
        modified_date=datetime.now(timezone.utc),
    )
    defaults.update(overrides)
    return EntityEntity(**defaults)


@pytest.fixture
def actor() -> User:
    return User(id=uuid4(), username="tester", is_active=True)


class FakeEntityService:
    """Records calls and returns canned values."""

    def __init__(self) -> None:
        self.created_input = None
        self.update_patch = None
        self.list_args = None
        self.raise_on_get: Exception | None = None

    async def create_entity(self, data, actor):  # noqa: ANN001
        self.created_input = data
        return _entity(
            entity_name=data.entity_name,
            short_code=data.short_code,
            company_code=data.company_code,
            is_active=True if data.is_active is None else data.is_active,
        )

    async def get_entity(self, entity_id):  # noqa: ANN001
        if self.raise_on_get is not None:
            raise self.raise_on_get
        return _entity(id=entity_id)

    async def update_entity(self, entity_id, patch, actor):  # noqa: ANN001
        self.update_patch = patch
        return _entity(id=entity_id)

    async def list_entities(self, skip, limit, search, is_active):  # noqa: ANN001
        self.list_args = (skip, limit, search, is_active)
        return [_entity(), _entity(entity_name="Beta")], 2

    async def get_dropdown(self):
        return [EntityDropdownItem(id=uuid4(), label="ACME - Acme Corp")]


# ─── list ───


async def test_list_maps_items_and_echoes_pagination() -> None:
    service = FakeEntityService()
    result = await ctrl.list_entities(
        skip=5, limit=10, search="ac", is_active=True, service=service
    )
    assert result.total == 2
    assert result.skip == 5
    assert result.limit == 10
    assert len(result.items) == 2
    assert service.list_args == (5, 10, "ac", True)


# ─── dropdown ───


async def test_dropdown_maps_items() -> None:
    service = FakeEntityService()
    items = await ctrl.get_entity_dropdown(service=service)
    assert len(items) == 1
    assert items[0].label == "ACME - Acme Corp"


# ─── create ───


async def test_create_maps_request_to_input_and_response(actor: User) -> None:
    service = FakeEntityService()
    request = CreateEntityRequest(
        entity_name="Acme Corp", short_code="ACME", company_code="C001"
    )
    response = await ctrl.create_entity(
        request=request, current_user=actor, service=service
    )
    assert service.created_input.entity_name == "Acme Corp"
    assert service.created_input.short_code == "ACME"
    assert service.created_input.is_active is None
    assert response.entity_name == "Acme Corp"
    assert response.is_active is True


# ─── get + exception mapping ───


async def test_get_unknown_maps_to_404() -> None:
    service = FakeEntityService()
    service.raise_on_get = MasterNotFoundError("Entity", uuid4())
    with pytest.raises(HTTPException) as exc:
        await ctrl.get_entity(entity_id=uuid4(), service=service)
    assert exc.value.status_code == status.HTTP_404_NOT_FOUND


# ─── partial update UNSET translation ───


async def test_update_translates_unset_for_omitted_fields(actor: User) -> None:
    service = FakeEntityService()
    # Only entity_name supplied; the rest must become UNSET.
    request = UpdateEntityRequest(entity_name="Renamed")
    await ctrl.update_entity(
        entity_id=uuid4(), request=request, current_user=actor, service=service
    )
    patch = service.update_patch
    assert patch.entity_name == "Renamed"
    assert patch.short_code is UNSET
    assert patch.company_code is UNSET
    assert patch.is_active is UNSET


async def test_update_preserves_explicit_null_for_company_code(actor: User) -> None:
    service = FakeEntityService()
    request = UpdateEntityRequest(company_code=None)
    await ctrl.update_entity(
        entity_id=uuid4(), request=request, current_user=actor, service=service
    )
    patch = service.update_patch
    # Explicit null is preserved (not UNSET) so the service can clear the field.
    assert patch.company_code is None
    assert patch.entity_name is UNSET


# ─── exception-to-HTTP mapping helper ───


@pytest.mark.parametrize(
    ("exc", "expected"),
    [
        (MasterValidationError("entity_name", "required"), status.HTTP_422_UNPROCESSABLE_ENTITY),
        (MasterConflictError("duplicate"), status.HTTP_409_CONFLICT),
        (MasterNotFoundError("Entity", uuid4()), status.HTTP_404_NOT_FOUND),
    ],
)
def test_to_http_exception_mapping(exc, expected) -> None:  # noqa: ANN001
    http_exc = ctrl._to_http_exception(exc)
    assert http_exc.status_code == expected
