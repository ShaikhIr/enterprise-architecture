"""
Unit tests for the Vendor-Customer Mapping controller.

The controller is intentionally thin, so these tests exercise its real
responsibilities in isolation (without standing up the FastAPI app, which is
wired in a later task):

* request/response schema adaptation to/from the Pydantic-agnostic service,
* combined vendor/customer list filtering and pagination echo (Req 14.7, 20.4),
* dates-only partial-update UNSET translation (Req 14.6), and
* master-exception-to-HTTP-status mapping (422 / 409 / 404).

The async route handlers are invoked directly with a fake service.
"""

from __future__ import annotations

from datetime import date, datetime, timezone
from uuid import uuid4

import pytest
from fastapi import HTTPException, status

from src.api.v1.endpoints.masters import mapping_controller as ctrl
from src.api.v1.schemas.masters.mapping_request import (
    CreateMappingRequest,
    UpdateMappingRequest,
)
from src.application.exceptions.application_exceptions import (
    MasterConflictError,
    MasterNotFoundError,
    MasterValidationError,
)
from src.application.services.masters.mapping_service import UNSET
from src.domain.entities.masters.mapping import MappingEntity
from src.domain.entities.user import User
from src.domain.enums.masters import MappingStatus

pytestmark = pytest.mark.asyncio


def _mapping(**overrides) -> MappingEntity:
    defaults = dict(
        id=uuid4(),
        vendor_id=uuid4(),
        customer_id=uuid4(),
        validity_from=date(2024, 1, 1),
        validity_to=date(2024, 12, 31),
        status=MappingStatus.Active,
        created_by="tester",
        created_date=datetime.now(timezone.utc),
        modified_by="tester",
        modified_date=datetime.now(timezone.utc),
    )
    defaults.update(overrides)
    return MappingEntity(**defaults)


@pytest.fixture
def actor() -> User:
    return User(
        id=uuid4(),
        username="tester",
        password_hash="x",
        is_active=True,
        is_blocked=False,
    )


class FakeMappingService:
    """Records calls and returns canned values."""

    def __init__(self) -> None:
        self.created_input = None
        self.update_patch = None
        self.list_args = None
        self.deleted_id = None
        self.raise_on_get: Exception | None = None
        self.raise_on_create: Exception | None = None
        self.raise_on_update: Exception | None = None
        self.raise_on_delete: Exception | None = None

    async def create_mapping(self, data, actor):  # noqa: ANN001
        self.created_input = data
        if self.raise_on_create is not None:
            raise self.raise_on_create
        return _mapping(
            vendor_id=data.vendor_id,
            customer_id=data.customer_id,
            validity_from=data.validity_from,
            validity_to=data.validity_to,
            status=data.status if data.status is not None else MappingStatus.Active,
        )

    async def get_mapping(self, mapping_id):  # noqa: ANN001
        if self.raise_on_get is not None:
            raise self.raise_on_get
        return _mapping(id=mapping_id)

    async def update_mapping(self, mapping_id, patch, actor):  # noqa: ANN001
        self.update_patch = patch
        if self.raise_on_update is not None:
            raise self.raise_on_update
        return _mapping(id=mapping_id)

    async def list_mappings(self, skip, limit, vendor_id, customer_id):  # noqa: ANN001
        self.list_args = (skip, limit, vendor_id, customer_id)
        return [_mapping(), _mapping()], 2

    async def delete_mapping(self, mapping_id, actor):  # noqa: ANN001
        self.deleted_id = mapping_id
        if self.raise_on_delete is not None:
            raise self.raise_on_delete


# ─── list ───


async def test_list_maps_items_and_echoes_pagination_and_filters() -> None:
    service = FakeMappingService()
    vid, cid = uuid4(), uuid4()
    result = await ctrl.list_mappings(
        vendor_id=vid, customer_id=cid, skip=5, limit=10, service=service
    )
    assert result.total == 2
    assert result.skip == 5
    assert result.limit == 10
    assert len(result.items) == 2
    assert service.list_args == (5, 10, vid, cid)


async def test_list_defaults_pass_none_filters() -> None:
    service = FakeMappingService()
    await ctrl.list_mappings(
        vendor_id=None, customer_id=None, skip=0, limit=20, service=service
    )
    assert service.list_args == (0, 20, None, None)


# ─── create ───


async def test_create_maps_request_to_input_and_response(actor: User) -> None:
    service = FakeMappingService()
    vid, cid = uuid4(), uuid4()
    request = CreateMappingRequest(
        vendor_id=vid,
        customer_id=cid,
        validity_from=date(2024, 1, 1),
        validity_to=date(2024, 12, 31),
    )
    response = await ctrl.create_mapping(
        request=request, current_user=actor, service=service
    )
    assert service.created_input.vendor_id == vid
    assert service.created_input.customer_id == cid
    assert service.created_input.status is None
    assert response.vendor_id == vid
    assert response.status == "Active"


async def test_create_unknown_vendor_maps_to_422(actor: User) -> None:
    service = FakeMappingService()
    service.raise_on_create = MasterValidationError(
        "vendor_id", "Vendor does not exist"
    )
    request = CreateMappingRequest(
        vendor_id=uuid4(),
        customer_id=uuid4(),
        validity_from=date(2024, 1, 1),
        validity_to=date(2024, 12, 31),
    )
    with pytest.raises(HTTPException) as exc:
        await ctrl.create_mapping(
            request=request, current_user=actor, service=service
        )
    assert exc.value.status_code == status.HTTP_422_UNPROCESSABLE_ENTITY


async def test_create_overlap_maps_to_409(actor: User) -> None:
    service = FakeMappingService()
    service.raise_on_create = MasterConflictError("overlap")
    request = CreateMappingRequest(
        vendor_id=uuid4(),
        customer_id=uuid4(),
        validity_from=date(2024, 1, 1),
        validity_to=date(2024, 12, 31),
    )
    with pytest.raises(HTTPException) as exc:
        await ctrl.create_mapping(
            request=request, current_user=actor, service=service
        )
    assert exc.value.status_code == status.HTTP_409_CONFLICT


# ─── get + exception mapping ───


async def test_get_unknown_maps_to_404() -> None:
    service = FakeMappingService()
    service.raise_on_get = MasterNotFoundError("Mapping", uuid4())
    with pytest.raises(HTTPException) as exc:
        await ctrl.get_mapping(mapping_id=uuid4(), service=service)
    assert exc.value.status_code == status.HTTP_404_NOT_FOUND


# ─── dates-only partial update UNSET translation (Req 14.6) ───


async def test_update_translates_unset_for_omitted_dates(actor: User) -> None:
    service = FakeMappingService()
    request = UpdateMappingRequest(validity_to=date(2025, 6, 30))
    await ctrl.update_mapping(
        mapping_id=uuid4(), request=request, current_user=actor, service=service
    )
    patch = service.update_patch
    assert patch.validity_to == date(2025, 6, 30)
    assert patch.validity_from is UNSET


async def test_update_both_omitted_is_all_unset(actor: User) -> None:
    service = FakeMappingService()
    request = UpdateMappingRequest()
    await ctrl.update_mapping(
        mapping_id=uuid4(), request=request, current_user=actor, service=service
    )
    patch = service.update_patch
    assert patch.validity_from is UNSET
    assert patch.validity_to is UNSET


async def test_update_invalid_period_maps_to_422(actor: User) -> None:
    service = FakeMappingService()
    service.raise_on_update = MasterValidationError(
        "validity_from", "Validity From must be on or before Validity To"
    )
    request = UpdateMappingRequest(validity_from=date(2025, 1, 1))
    with pytest.raises(HTTPException) as exc:
        await ctrl.update_mapping(
            mapping_id=uuid4(),
            request=request,
            current_user=actor,
            service=service,
        )
    assert exc.value.status_code == status.HTTP_422_UNPROCESSABLE_ENTITY


# ─── delete ───


async def test_delete_returns_204(actor: User) -> None:
    service = FakeMappingService()
    mid = uuid4()
    response = await ctrl.delete_mapping(
        mapping_id=mid, current_user=actor, service=service
    )
    assert service.deleted_id == mid
    assert response.status_code == status.HTTP_204_NO_CONTENT


async def test_delete_unknown_maps_to_404(actor: User) -> None:
    service = FakeMappingService()
    service.raise_on_delete = MasterNotFoundError("Mapping", uuid4())
    with pytest.raises(HTTPException) as exc:
        await ctrl.delete_mapping(
            mapping_id=uuid4(), current_user=actor, service=service
        )
    assert exc.value.status_code == status.HTTP_404_NOT_FOUND


# ─── exception-to-HTTP mapping helper ───


@pytest.mark.parametrize(
    ("exc", "expected"),
    [
        (
            MasterValidationError("vendor_id", "required"),
            status.HTTP_422_UNPROCESSABLE_ENTITY,
        ),
        (MasterConflictError("overlap"), status.HTTP_409_CONFLICT),
        (MasterNotFoundError("Mapping", uuid4()), status.HTTP_404_NOT_FOUND),
    ],
)
def test_to_http_exception_mapping(exc, expected) -> None:  # noqa: ANN001
    http_exc = ctrl._to_http_exception(exc)
    assert http_exc.status_code == expected
