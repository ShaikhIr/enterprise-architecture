"""
Unit tests for the Product Master and Product Detail controllers.

The controllers are intentionally thin, so these tests exercise their two real
responsibilities in isolation (without standing up the FastAPI app, which is
wired in a later task):

* request/response schema adaptation to/from the Pydantic-agnostic service, and
* master-exception-to-HTTP-status mapping (422 / 409 / 404).

The async route handlers are invoked directly with a fake service.
"""

from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal
from uuid import uuid4

import pytest
from fastapi import HTTPException, status

from src.api.v1.endpoints.masters import (
    product_detail_controller as detail_ctrl,
    product_master_controller as master_ctrl,
)
from src.api.v1.schemas.masters.product import (
    ProductDetailCreateRequest,
    ProductDetailUpdateRequest,
    ProductMasterCreateRequest,
    ProductMasterUpdateRequest,
)
from src.application.exceptions.application_exceptions import (
    MasterConflictError,
    MasterNotFoundError,
    MasterValidationError,
)
from src.application.services.masters.product_service import UNSET
from src.domain.entities.masters.product import (
    ProductDetailEntity,
    ProductMasterEntity,
)
from src.domain.entities.user import User
from src.domain.enums.masters import ProductStatus


def _master(**overrides) -> ProductMasterEntity:
    defaults = dict(
        id=uuid4(),
        basic_material_code="BM-1",
        product_name="Paracetamol",
        therapeutic_category="Analgesic",
        status=ProductStatus.Active,
        created_by="tester",
        created_date=datetime.now(timezone.utc),
        modified_by="tester",
        modified_date=datetime.now(timezone.utc),
    )
    defaults.update(overrides)
    return ProductMasterEntity(**defaults)


def _detail(**overrides) -> ProductDetailEntity:
    defaults = dict(
        id=uuid4(),
        child_code="CH-1",
        product_master_id=uuid4(),
        variant_description="10mg",
        hsn_code="3004",
        pack_size="10s",
        unit_of_measure="strip",
        mrp=Decimal("100.00"),
        rate=Decimal("80.00"),
        gst_percent=Decimal("12.00"),
        status=ProductStatus.Active,
        created_by="tester",
        created_date=datetime.now(timezone.utc),
        modified_by="tester",
        modified_date=datetime.now(timezone.utc),
    )
    defaults.update(overrides)
    return ProductDetailEntity(**defaults)


@pytest.fixture
def actor() -> User:
    return User(id=uuid4(), username="tester", is_active=True)


class FakeProductService:
    """Records calls and returns canned values."""

    def __init__(self) -> None:
        self.created_input = None
        self.update_patch = None
        self.list_args = None
        self.deleted_id = None
        self.raise_on_get: Exception | None = None
        self.raise_on_create: Exception | None = None
        self.raise_on_delete: Exception | None = None

    # ── master ──
    async def create_master(self, data, actor):  # noqa: ANN001
        if self.raise_on_create is not None:
            raise self.raise_on_create
        self.created_input = data
        return _master(
            basic_material_code=data.basic_material_code,
            product_name=data.product_name,
            therapeutic_category=data.therapeutic_category,
            status=ProductStatus.Active if data.status is None else data.status,
        )

    async def get_master(self, master_id):  # noqa: ANN001
        if self.raise_on_get is not None:
            raise self.raise_on_get
        return _master(id=master_id)

    async def update_master(self, master_id, patch, actor):  # noqa: ANN001
        self.update_patch = patch
        return _master(id=master_id)

    async def list_masters(self, skip, limit):  # noqa: ANN001
        self.list_args = (skip, limit)
        return [_master(), _master(basic_material_code="BM-2")], 2

    async def delete_master(self, master_id, actor):  # noqa: ANN001
        if self.raise_on_delete is not None:
            raise self.raise_on_delete
        self.deleted_id = master_id

    # ── detail ──
    async def create_detail(self, data, actor):  # noqa: ANN001
        if self.raise_on_create is not None:
            raise self.raise_on_create
        self.created_input = data
        return _detail(
            child_code=data.child_code,
            product_master_id=data.product_master_id,
            status=ProductStatus.Active if data.status is None else data.status,
        )

    async def get_detail(self, detail_id):  # noqa: ANN001
        if self.raise_on_get is not None:
            raise self.raise_on_get
        return _detail(id=detail_id)

    async def update_detail(self, detail_id, patch, actor):  # noqa: ANN001
        self.update_patch = patch
        return _detail(id=detail_id)

    async def list_details(self, skip, limit, product_master_id=None):  # noqa: ANN001
        self.list_args = (skip, limit, product_master_id)
        return [_detail()], 1

    async def delete_detail(self, detail_id, actor):  # noqa: ANN001
        if self.raise_on_delete is not None:
            raise self.raise_on_delete
        self.deleted_id = detail_id

    async def get_product_name(self, detail_id):  # noqa: ANN001
        if self.raise_on_get is not None:
            raise self.raise_on_get
        return "Paracetamol"


# ───────────────────────── Product Master controller ─────────────────────────


async def test_master_list_maps_items_and_echoes_pagination() -> None:
    service = FakeProductService()
    result = await master_ctrl.list_product_masters(skip=5, limit=10, service=service)
    assert result.total == 2
    assert result.skip == 5
    assert result.limit == 10
    assert len(result.items) == 2
    assert service.list_args == (5, 10)


async def test_master_create_maps_request_to_input_and_response(actor: User) -> None:
    service = FakeProductService()
    request = ProductMasterCreateRequest(
        basic_material_code="BM-9", product_name="Ibuprofen"
    )
    response = await master_ctrl.create_product_master(
        request=request, current_user=actor, service=service
    )
    assert service.created_input.basic_material_code == "BM-9"
    assert service.created_input.product_name == "Ibuprofen"
    assert service.created_input.status is None
    assert response.basic_material_code == "BM-9"
    assert response.status == ProductStatus.Active


async def test_master_create_conflict_maps_to_409(actor: User) -> None:
    service = FakeProductService()
    service.raise_on_create = MasterConflictError("duplicate")
    request = ProductMasterCreateRequest(
        basic_material_code="BM-9", product_name="Ibuprofen"
    )
    with pytest.raises(HTTPException) as exc:
        await master_ctrl.create_product_master(
            request=request, current_user=actor, service=service
        )
    assert exc.value.status_code == status.HTTP_409_CONFLICT


async def test_master_get_unknown_maps_to_404() -> None:
    service = FakeProductService()
    service.raise_on_get = MasterNotFoundError("Product Master", uuid4())
    with pytest.raises(HTTPException) as exc:
        await master_ctrl.get_product_master(master_id=uuid4(), service=service)
    assert exc.value.status_code == status.HTTP_404_NOT_FOUND


async def test_master_update_translates_unset_for_omitted_fields(actor: User) -> None:
    service = FakeProductService()
    request = ProductMasterUpdateRequest(product_name="Renamed")
    await master_ctrl.update_product_master(
        master_id=uuid4(), request=request, current_user=actor, service=service
    )
    patch = service.update_patch
    assert patch.product_name == "Renamed"
    assert patch.basic_material_code is UNSET
    assert patch.therapeutic_category is UNSET
    assert patch.status is UNSET


async def test_master_update_preserves_explicit_null(actor: User) -> None:
    service = FakeProductService()
    request = ProductMasterUpdateRequest(therapeutic_category=None)
    await master_ctrl.update_product_master(
        master_id=uuid4(), request=request, current_user=actor, service=service
    )
    patch = service.update_patch
    assert patch.therapeutic_category is None
    assert patch.product_name is UNSET


async def test_master_delete_blocked_maps_to_409(actor: User) -> None:
    service = FakeProductService()
    service.raise_on_delete = MasterConflictError("has children")
    with pytest.raises(HTTPException) as exc:
        await master_ctrl.delete_product_master(
            master_id=uuid4(), current_user=actor, service=service
        )
    assert exc.value.status_code == status.HTTP_409_CONFLICT


async def test_master_delete_returns_204(actor: User) -> None:
    service = FakeProductService()
    response = await master_ctrl.delete_product_master(
        master_id=uuid4(), current_user=actor, service=service
    )
    assert response.status_code == status.HTTP_204_NO_CONTENT


# ───────────────────────── Product Detail controller ─────────────────────────


async def test_detail_list_passes_master_filter() -> None:
    service = FakeProductService()
    master_id = uuid4()
    result = await detail_ctrl.list_product_details(
        skip=0, limit=20, product_master_id=master_id, service=service
    )
    assert result.total == 1
    assert service.list_args == (0, 20, master_id)


async def test_detail_create_maps_request_to_input_and_response(actor: User) -> None:
    service = FakeProductService()
    master_id = uuid4()
    request = ProductDetailCreateRequest(
        child_code="CH-9",
        product_master_id=master_id,
        mrp=Decimal("50.00"),
        gst_percent=Decimal("5"),
    )
    response = await detail_ctrl.create_product_detail(
        request=request, current_user=actor, service=service
    )
    assert service.created_input.child_code == "CH-9"
    assert service.created_input.product_master_id == master_id
    assert service.created_input.status is None
    assert response.child_code == "CH-9"
    assert response.status == ProductStatus.Active


async def test_detail_create_validation_maps_to_422(actor: User) -> None:
    service = FakeProductService()
    service.raise_on_create = MasterValidationError("mrp", "must be >= 0")
    request = ProductDetailCreateRequest(child_code="CH-9", product_master_id=uuid4())
    with pytest.raises(HTTPException) as exc:
        await detail_ctrl.create_product_detail(
            request=request, current_user=actor, service=service
        )
    assert exc.value.status_code == status.HTTP_422_UNPROCESSABLE_ENTITY
    assert exc.value.detail == {"field": "mrp", "reason": "must be >= 0"}


async def test_detail_update_translates_unset_for_omitted_fields(actor: User) -> None:
    service = FakeProductService()
    request = ProductDetailUpdateRequest(rate=Decimal("12.50"))
    await detail_ctrl.update_product_detail(
        detail_id=uuid4(), request=request, current_user=actor, service=service
    )
    patch = service.update_patch
    assert patch.rate == Decimal("12.50")
    assert patch.child_code is UNSET
    assert patch.product_master_id is UNSET
    assert patch.gst_percent is UNSET


async def test_detail_product_name_resolution() -> None:
    service = FakeProductService()
    result = await detail_ctrl.get_product_detail_name(
        detail_id=uuid4(), service=service
    )
    assert result.product_name == "Paracetamol"


async def test_detail_product_name_unknown_maps_to_404() -> None:
    service = FakeProductService()
    service.raise_on_get = MasterNotFoundError("Product Detail", uuid4())
    with pytest.raises(HTTPException) as exc:
        await detail_ctrl.get_product_detail_name(detail_id=uuid4(), service=service)
    assert exc.value.status_code == status.HTTP_404_NOT_FOUND


async def test_detail_delete_returns_204(actor: User) -> None:
    service = FakeProductService()
    response = await detail_ctrl.delete_product_detail(
        detail_id=uuid4(), current_user=actor, service=service
    )
    assert response.status_code == status.HTTP_204_NO_CONTENT
