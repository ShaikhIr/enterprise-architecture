"""
Unit tests for the Customer Master controller.

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

from src.api.v1.endpoints.masters import customer_controller as ctrl
from src.api.v1.schemas.masters.customer_request import (
    CreateCustomerRequest,
    UpdateCustomerRequest,
)
from src.application.exceptions.application_exceptions import (
    MasterConflictError,
    MasterNotFoundError,
    MasterValidationError,
)
from src.application.services.masters.customer_service import UNSET
from src.domain.entities.masters.customer import CustomerEntity
from src.domain.entities.user import User
from src.domain.enums.masters import CustomerStatus

pytestmark = pytest.mark.asyncio


def _customer(**overrides) -> CustomerEntity:
    defaults = dict(
        id=uuid4(),
        customer_code="CUST001",
        customer_name="City Hospital",
        address="1 Main St",
        gstn_number="22AAAAA0000A1Z5",
        contact_person="Jane Doe",
        contact_number="555-1234",
        contact_email="jane@example.com",
        status=CustomerStatus.Active,
        created_by="tester",
        created_date=datetime.now(timezone.utc),
        modified_by="tester",
        modified_date=datetime.now(timezone.utc),
    )
    defaults.update(overrides)
    return CustomerEntity(**defaults)


@pytest.fixture
def actor() -> User:
    return User(
        id=uuid4(),
        username="tester",
        password_hash="x",
        is_active=True,
        is_blocked=False,
    )


class FakeCustomerService:
    """Records calls and returns canned values."""

    def __init__(self) -> None:
        self.created_input = None
        self.update_patch = None
        self.list_args = None
        self.deleted_id = None
        self.raise_on_get: Exception | None = None
        self.raise_on_create: Exception | None = None
        self.raise_on_delete: Exception | None = None

    async def create_customer(self, data, actor):  # noqa: ANN001
        self.created_input = data
        if self.raise_on_create is not None:
            raise self.raise_on_create
        return _customer(
            customer_code=data.customer_code,
            customer_name=data.customer_name,
            status=data.status if data.status is not None else CustomerStatus.Active,
        )

    async def get_customer(self, customer_id):  # noqa: ANN001
        if self.raise_on_get is not None:
            raise self.raise_on_get
        return _customer(id=customer_id)

    async def update_customer(self, customer_id, patch, actor):  # noqa: ANN001
        self.update_patch = patch
        return _customer(id=customer_id)

    async def list_customers(
        self,
        skip: int,
        limit: int,
        customer_code: str | None = None,
        customer_name: str | None = None,
    ) -> tuple:  # noqa: ANN001
        self.list_args = (skip, limit)
        return [_customer(), _customer(customer_code="CUST002")], 2

    async def delete_customer(self, customer_id, actor):  # noqa: ANN001
        self.deleted_id = customer_id
        if self.raise_on_delete is not None:
            raise self.raise_on_delete


# ─── list ───


async def test_list_maps_items_and_echoes_pagination() -> None:
    service = FakeCustomerService()
    result = await ctrl.list_customers(skip=5, limit=10, service=service)
    assert result.total == 2
    assert result.skip == 5
    assert result.limit == 10
    assert len(result.items) == 2
    assert service.list_args == (5, 10)


# ─── create ───


async def test_create_maps_request_to_input_and_response(actor: User) -> None:
    service = FakeCustomerService()
    request = CreateCustomerRequest(
        customer_code="CUST001",
        customer_name="City Hospital",
    )
    response = await ctrl.create_customer(
        request=request, current_user=actor, service=service
    )
    assert service.created_input.customer_code == "CUST001"
    assert service.created_input.customer_name == "City Hospital"
    assert service.created_input.status is None
    assert response.customer_code == "CUST001"
    assert response.status == "Active"


async def test_create_invalid_type_maps_to_422(actor: User) -> None:
    service = FakeCustomerService()
    service.raise_on_create = MasterValidationError(
        "customer_code", "Customer Code is required"
    )
    request = CreateCustomerRequest(
        customer_code="",
        customer_name="City Hospital",
    )
    with pytest.raises(HTTPException) as exc:
        await ctrl.create_customer(
            request=request, current_user=actor, service=service
        )
    assert exc.value.status_code == status.HTTP_422_UNPROCESSABLE_ENTITY


async def test_create_duplicate_code_maps_to_409(actor: User) -> None:
    service = FakeCustomerService()
    service.raise_on_create = MasterConflictError("duplicate")
    request = CreateCustomerRequest(
        customer_code="CUST001", customer_name="City Hospital"
    )
    with pytest.raises(HTTPException) as exc:
        await ctrl.create_customer(
            request=request, current_user=actor, service=service
        )
    assert exc.value.status_code == status.HTTP_409_CONFLICT


# ─── get + exception mapping ───


async def test_get_unknown_maps_to_404() -> None:
    service = FakeCustomerService()
    service.raise_on_get = MasterNotFoundError("Customer", uuid4())
    with pytest.raises(HTTPException) as exc:
        await ctrl.get_customer(customer_id=uuid4(), service=service)
    assert exc.value.status_code == status.HTTP_404_NOT_FOUND


# ─── partial update UNSET translation ───


async def test_update_translates_unset_for_omitted_fields(actor: User) -> None:
    service = FakeCustomerService()
    # Only customer_name supplied; the rest must become UNSET.
    request = UpdateCustomerRequest(customer_name="Renamed Hospital")
    await ctrl.update_customer(
        customer_id=uuid4(), request=request, current_user=actor, service=service
    )
    patch = service.update_patch
    assert patch.customer_name == "Renamed Hospital"
    assert patch.customer_code is UNSET
    assert patch.gstn_number is UNSET
    assert patch.contact_email is UNSET
    assert patch.status is UNSET


async def test_update_preserves_explicit_null_for_nullable_field(actor: User) -> None:
    service = FakeCustomerService()
    request = UpdateCustomerRequest(gstn_number=None)
    await ctrl.update_customer(
        customer_id=uuid4(), request=request, current_user=actor, service=service
    )
    patch = service.update_patch
    # Explicit null is preserved (not UNSET) so the service can clear the field.
    assert patch.gstn_number is None
    assert patch.customer_name is UNSET


async def test_update_explicit_null_status_treated_as_unset(actor: User) -> None:
    service = FakeCustomerService()
    # status is non-nullable; an explicit null must not be forwarded as None.
    request = UpdateCustomerRequest(status=None)
    await ctrl.update_customer(
        customer_id=uuid4(), request=request, current_user=actor, service=service
    )
    assert service.update_patch.status is UNSET


# ─── delete ───


async def test_delete_returns_204(actor: User) -> None:
    service = FakeCustomerService()
    cid = uuid4()
    response = await ctrl.delete_customer(
        customer_id=cid, current_user=actor, service=service
    )
    assert service.deleted_id == cid
    assert response.status_code == status.HTTP_204_NO_CONTENT


async def test_delete_in_use_maps_to_409(actor: User) -> None:
    service = FakeCustomerService()
    service.raise_on_delete = MasterConflictError("in use")
    with pytest.raises(HTTPException) as exc:
        await ctrl.delete_customer(
            customer_id=uuid4(), current_user=actor, service=service
        )
    assert exc.value.status_code == status.HTTP_409_CONFLICT


# ─── exception-to-HTTP mapping helper ───


@pytest.mark.parametrize(
    ("exc", "expected"),
    [
        (
            MasterValidationError("customer_code", "required"),
            status.HTTP_422_UNPROCESSABLE_ENTITY,
        ),
        (MasterConflictError("duplicate"), status.HTTP_409_CONFLICT),
        (MasterNotFoundError("Customer", uuid4()), status.HTTP_404_NOT_FOUND),
    ],
)
def test_to_http_exception_mapping(exc, expected) -> None:  # noqa: ANN001
    http_exc = ctrl._to_http_exception(exc)
    assert http_exc.status_code == expected
