"""
Unit tests for the Invoice Master controller.

The controller is intentionally thin, so these tests exercise its real
responsibilities in isolation (without standing up the FastAPI app, which is
wired in a later task):

* request/response schema adaptation to/from the Pydantic-agnostic service
  (including the nested header + lines aggregate),
* partial-update ``UNSET`` translation (omitted vs explicit-null), and
* master-exception-to-HTTP-status mapping (422 / 409 / 404).

The async route handlers are invoked directly with a fake service.
"""

from __future__ import annotations

from datetime import date, datetime, timezone
from decimal import Decimal
from uuid import uuid4

import pytest
from fastapi import HTTPException, status

from src.api.v1.endpoints.masters import invoice_controller as ctrl
from src.api.v1.schemas.masters.invoice_request import (
    CreateInvoiceRequest,
    InvoiceLineRequest,
    SapPaymentRequest,
    UpdateInvoiceRequest,
)
from src.application.exceptions.application_exceptions import (
    MasterConflictError,
    MasterNotFoundError,
    MasterValidationError,
)
from src.application.services.masters.invoice_service import UNSET
from src.domain.entities.masters.invoice import (
    InvoiceHeaderEntity,
    InvoiceLineEntity,
)
from src.domain.entities.user import User
from src.domain.enums.masters import InvoiceStatus

pytestmark = pytest.mark.asyncio


def _line(**overrides) -> InvoiceLineEntity:
    defaults = dict(
        id=uuid4(),
        invoice_header_id=uuid4(),
        product_detail_id=uuid4(),
        quantity=Decimal("2"),
        line_amount=Decimal("100.00"),
        vat_gst_amount=Decimal("18.00"),
        created_by="tester",
        created_date=datetime.now(timezone.utc),
        modified_by="tester",
        modified_date=datetime.now(timezone.utc),
    )
    defaults.update(overrides)
    return InvoiceLineEntity(**defaults)


def _invoice(**overrides) -> InvoiceHeaderEntity:
    defaults = dict(
        id=uuid4(),
        invoice_number="INV-001",
        invoice_date=date(2024, 1, 1),
        vendor_id=uuid4(),
        customer_id=uuid4(),
        bill_amount_excl_gst=Decimal("100.00"),
        bill_amount_incl_tax=Decimal("118.00"),
        amount_deducted=Decimal("0"),
        tds_value=Decimal("0"),
        due_date=date(2024, 1, 31),
        invoice_status=InvoiceStatus.Open,
        created_by="tester",
        created_date=datetime.now(timezone.utc),
        modified_by="tester",
        modified_date=datetime.now(timezone.utc),
    )
    defaults.update(overrides)
    header = InvoiceHeaderEntity(**defaults)
    if not header.lines:
        header.lines = [_line(invoice_header_id=header.id)]
    return header


@pytest.fixture
def actor() -> User:
    return User(
        id=uuid4(),
        username="tester",
        password_hash="x",
        is_active=True,
        is_blocked=False,
    )


class FakeInvoiceService:
    """Records calls and returns canned values."""

    def __init__(self) -> None:
        self.created_input = None
        self.update_patch = None
        self.list_args = None
        self.deleted_id = None
        self.sap_input = None
        self.settled_id = None
        self.raise_on_get: Exception | None = None
        self.raise_on_create: Exception | None = None
        self.raise_on_sap: Exception | None = None

    async def create_invoice(self, data, actor):  # noqa: ANN001
        self.created_input = data
        if self.raise_on_create is not None:
            raise self.raise_on_create
        return _invoice(invoice_number=data.invoice_number)

    async def get_invoice(self, invoice_id):  # noqa: ANN001
        if self.raise_on_get is not None:
            raise self.raise_on_get
        return _invoice(id=invoice_id)

    async def update_invoice(self, invoice_id, patch, actor):  # noqa: ANN001
        self.update_patch = patch
        return _invoice(id=invoice_id)

    async def list_invoices(self, skip, limit):  # noqa: ANN001
        self.list_args = (skip, limit)
        return [_invoice(), _invoice(invoice_number="INV-002")], 2

    async def delete_invoice(self, invoice_id, actor):  # noqa: ANN001
        self.deleted_id = invoice_id

    async def record_sap_payment(self, data, actor):  # noqa: ANN001
        self.sap_input = data
        if self.raise_on_sap is not None:
            raise self.raise_on_sap
        return _invoice(invoice_status=InvoiceStatus.PaymentCleared)

    async def mark_settled(self, invoice_id, actor):  # noqa: ANN001
        self.settled_id = invoice_id
        return _invoice(id=invoice_id, invoice_status=InvoiceStatus.Settled)


# ─── list ───


async def test_list_maps_items_and_echoes_pagination() -> None:
    service = FakeInvoiceService()
    result = await ctrl.list_invoices(skip=5, limit=10, service=service)
    assert result.total == 2
    assert result.skip == 5
    assert result.limit == 10
    assert len(result.items) == 2
    assert service.list_args == (5, 10)


# ─── create ───


async def test_create_maps_request_with_lines_to_input_and_response(
    actor: User,
) -> None:
    service = FakeInvoiceService()
    detail_id = uuid4()
    request = CreateInvoiceRequest(
        invoice_number="INV-001",
        invoice_date=date(2024, 1, 1),
        vendor_id=uuid4(),
        customer_id=uuid4(),
        bill_amount_excl_gst=Decimal("100.00"),
        lines=[
            InvoiceLineRequest(
                product_detail_id=detail_id,
                quantity=Decimal("2"),
                line_amount=Decimal("100.00"),
            )
        ],
    )
    response = await ctrl.create_invoice(
        request=request, current_user=actor, service=service
    )
    assert service.created_input.invoice_number == "INV-001"
    assert len(service.created_input.lines) == 1
    assert service.created_input.lines[0].product_detail_id == detail_id
    # amount_deducted/tds default to None at the boundary; service applies 0.
    assert service.created_input.amount_deducted is None
    assert response.invoice_number == "INV-001"
    assert response.invoice_status == "Open"
    assert len(response.lines) == 1


async def test_create_duplicate_number_maps_to_409(actor: User) -> None:
    service = FakeInvoiceService()
    service.raise_on_create = MasterConflictError("duplicate")
    request = CreateInvoiceRequest(
        invoice_number="INV-001",
        invoice_date=date(2024, 1, 1),
        vendor_id=uuid4(),
        customer_id=uuid4(),
        bill_amount_excl_gst=Decimal("100.00"),
        lines=[InvoiceLineRequest(product_detail_id=uuid4())],
    )
    with pytest.raises(HTTPException) as exc:
        await ctrl.create_invoice(
            request=request, current_user=actor, service=service
        )
    assert exc.value.status_code == status.HTTP_409_CONFLICT


async def test_create_unknown_reference_maps_to_422(actor: User) -> None:
    service = FakeInvoiceService()
    service.raise_on_create = MasterValidationError(
        "vendor_id", "Vendor does not exist"
    )
    request = CreateInvoiceRequest(
        invoice_number="INV-001",
        invoice_date=date(2024, 1, 1),
        vendor_id=uuid4(),
        customer_id=uuid4(),
        bill_amount_excl_gst=Decimal("100.00"),
        lines=[InvoiceLineRequest(product_detail_id=uuid4())],
    )
    with pytest.raises(HTTPException) as exc:
        await ctrl.create_invoice(
            request=request, current_user=actor, service=service
        )
    assert exc.value.status_code == status.HTTP_422_UNPROCESSABLE_ENTITY


# ─── get + exception mapping ───


async def test_get_unknown_maps_to_404() -> None:
    service = FakeInvoiceService()
    service.raise_on_get = MasterNotFoundError("Invoice Header", uuid4())
    with pytest.raises(HTTPException) as exc:
        await ctrl.get_invoice(invoice_id=uuid4(), service=service)
    assert exc.value.status_code == status.HTTP_404_NOT_FOUND


# ─── partial update UNSET translation ───


async def test_update_translates_unset_for_omitted_fields(actor: User) -> None:
    service = FakeInvoiceService()
    # Only amount_deducted supplied; the rest must become UNSET.
    request = UpdateInvoiceRequest(amount_deducted=Decimal("5.00"))
    await ctrl.update_invoice(
        invoice_id=uuid4(), request=request, current_user=actor, service=service
    )
    patch = service.update_patch
    assert patch.amount_deducted == Decimal("5.00")
    assert patch.bill_amount_excl_gst is UNSET
    assert patch.bill_amount_incl_tax is UNSET
    assert patch.tds_value is UNSET
    assert patch.due_date is UNSET


async def test_update_preserves_explicit_null_for_nullable_due_date(
    actor: User,
) -> None:
    service = FakeInvoiceService()
    request = UpdateInvoiceRequest(due_date=None)
    await ctrl.update_invoice(
        invoice_id=uuid4(), request=request, current_user=actor, service=service
    )
    patch = service.update_patch
    # Explicit null is preserved (not UNSET) so the service can clear the field.
    assert patch.due_date is None
    assert patch.amount_deducted is UNSET


async def test_update_explicit_null_required_field_treated_as_unset(
    actor: User,
) -> None:
    service = FakeInvoiceService()
    # bill_amount_excl_gst is non-nullable; explicit null must not be forwarded.
    request = UpdateInvoiceRequest(bill_amount_excl_gst=None)
    await ctrl.update_invoice(
        invoice_id=uuid4(), request=request, current_user=actor, service=service
    )
    assert service.update_patch.bill_amount_excl_gst is UNSET


# ─── delete ───


async def test_delete_returns_204(actor: User) -> None:
    service = FakeInvoiceService()
    iid = uuid4()
    response = await ctrl.delete_invoice(
        invoice_id=iid, current_user=actor, service=service
    )
    assert service.deleted_id == iid
    assert response.status_code == status.HTTP_204_NO_CONTENT


# ─── SAP payment ───


async def test_sap_payment_forwards_path_id_and_returns_cleared(
    actor: User,
) -> None:
    service = FakeInvoiceService()
    iid = uuid4()
    request = SapPaymentRequest(
        payment_clearing_date=date(2024, 2, 1),
        sap_clearing_document_no="SAP-123",
    )
    response = await ctrl.record_sap_payment(
        invoice_id=iid, request=request, current_user=actor, service=service
    )
    assert service.sap_input.invoice_id == iid
    assert service.sap_input.sap_clearing_document_no == "SAP-123"
    assert response.invoice_status == "Payment Cleared"


async def test_sap_payment_unknown_maps_to_404(actor: User) -> None:
    service = FakeInvoiceService()
    service.raise_on_sap = MasterNotFoundError("Invoice Header", uuid4())
    request = SapPaymentRequest(
        payment_clearing_date=date(2024, 2, 1),
        sap_clearing_document_no="SAP-123",
    )
    with pytest.raises(HTTPException) as exc:
        await ctrl.record_sap_payment(
            invoice_id=uuid4(), request=request, current_user=actor, service=service
        )
    assert exc.value.status_code == status.HTTP_404_NOT_FOUND


# ─── settle ───


async def test_settle_returns_settled(actor: User) -> None:
    service = FakeInvoiceService()
    iid = uuid4()
    response = await ctrl.mark_settled(
        invoice_id=iid, current_user=actor, service=service
    )
    assert service.settled_id == iid
    assert response.invoice_status == "Settled"


# ─── exception-to-HTTP mapping helper ───


@pytest.mark.parametrize(
    ("exc", "expected"),
    [
        (
            MasterValidationError("invoice_number", "required"),
            status.HTTP_422_UNPROCESSABLE_ENTITY,
        ),
        (MasterConflictError("duplicate"), status.HTTP_409_CONFLICT),
        (MasterNotFoundError("Invoice Header", uuid4()), status.HTTP_404_NOT_FOUND),
    ],
)
def test_to_http_exception_mapping(exc, expected) -> None:  # noqa: ANN001
    http_exc = ctrl._to_http_exception(exc)
    assert http_exc.status_code == expected
