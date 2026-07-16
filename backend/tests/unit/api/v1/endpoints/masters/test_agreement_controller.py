"""
Unit tests for the Agreement controller.

The controller is intentionally thin, so these tests exercise its real
responsibilities in isolation (without standing up the FastAPI app, which is
wired in a later task):

* request/response schema adaptation to/from the Pydantic-agnostic service,
* the optional ``vendor_id`` list filter (Req 11.10),
* partial-update mapping of omitted fields to the ``UNSET`` sentinel,
* multipart Agreement Document adaptation to ``AgreementDocumentInput``, and
* master-exception-to-HTTP-status mapping (422 / 409 / 404).

The async route handlers are invoked directly with a fake service.
"""

from __future__ import annotations

from datetime import date, datetime, timezone
from decimal import Decimal
from uuid import uuid4

import pytest
from fastapi import HTTPException, status

from src.api.v1.endpoints.masters import agreement_controller as ctrl
from src.api.v1.schemas.masters.agreement import (
    AgreementCreateRequest,
    AgreementRenewRequest,
    AgreementUpdateRequest,
)
from src.application.exceptions.application_exceptions import (
    MasterConflictError,
    MasterNotFoundError,
    MasterValidationError,
)
from src.application.services.masters.agreement_service import UNSET
from src.domain.entities.masters.agreement import AgreementEntity
from src.domain.entities.user import User
from src.domain.enums.masters import AgreementStatus, AgreementType


def _agreement(**overrides) -> AgreementEntity:
    defaults = dict(
        id=uuid4(),
        vendor_id=uuid4(),
        product_master_id=uuid4(),
        from_date=date(2025, 1, 1),
        to_date=date(2025, 12, 31),
        slab_in_days=30,
        reduction_percent=Decimal("5.00"),
        max_commission_percent=Decimal("20.00"),
        min_commission_percent=Decimal("5.00"),
        credit_days=15,
        agreement_type=AgreementType.Original,
        prior_agreement_id=None,
        agreement_document_ref=None,
        status=AgreementStatus.Active,
        created_by="tester",
        created_date=datetime.now(timezone.utc),
        modified_by="tester",
        modified_date=datetime.now(timezone.utc),
    )
    defaults.update(overrides)
    return AgreementEntity(**defaults)


@pytest.fixture
def actor() -> User:
    return User(id=uuid4(), username="tester", is_active=True)


class _FakeUpload:
    """Minimal stand-in for ``UploadFile`` for document-adaptation tests."""

    def __init__(self, content_type: str, filename: str, data: bytes) -> None:
        self.content_type = content_type
        self.filename = filename
        self._data = data

    async def read(self) -> bytes:
        return self._data


class FakeAgreementService:
    """Records calls and returns canned values."""

    def __init__(self) -> None:
        self.created_input = None
        self.update_patch = None
        self.renew_input = None
        self.list_args = None
        self.deleted_id = None
        self.raise_on_get: Exception | None = None
        self.raise_on_create: Exception | None = None
        self.raise_on_update: Exception | None = None
        self.raise_on_renew: Exception | None = None
        self.raise_on_delete: Exception | None = None

    async def create_agreement(self, data, actor):  # noqa: ANN001
        if self.raise_on_create is not None:
            raise self.raise_on_create
        self.created_input = data
        return _agreement(
            vendor_id=data.vendor_id,
            product_master_id=data.product_master_id,
            agreement_document_ref=(
                data.document.storage_ref if data.document else None
            ),
        )

    async def get_agreement(self, agreement_id):  # noqa: ANN001
        if self.raise_on_get is not None:
            raise self.raise_on_get
        return _agreement(id=agreement_id)

    async def update_agreement(self, agreement_id, patch, actor):  # noqa: ANN001
        if self.raise_on_update is not None:
            raise self.raise_on_update
        self.update_patch = patch
        return _agreement(id=agreement_id)

    async def renew_agreement(self, agreement_id, data, actor):  # noqa: ANN001
        if self.raise_on_renew is not None:
            raise self.raise_on_renew
        self.renew_input = data
        return _agreement(
            agreement_type=AgreementType.Renewal, prior_agreement_id=agreement_id
        )

    async def list_agreements(self, skip, limit, vendor_id=None):  # noqa: ANN001
        self.list_args = (skip, limit, vendor_id)
        # Return tuples matching controller unpacking: (entity, vendor_name, child_code, product_name)
        return [(_agreement(), "Vendor A", "CHILD-1", "Product A"),
                (_agreement(), "Vendor B", "CHILD-2", "Product B")], 2

    async def delete_agreement(self, agreement_id, actor):  # noqa: ANN001
        if self.raise_on_delete is not None:
            raise self.raise_on_delete
        self.deleted_id = agreement_id


def _create_request(**overrides) -> AgreementCreateRequest:
    defaults = dict(
        vendor_id=uuid4(),
        product_master_id=uuid4(),
        from_date=date(2025, 1, 1),
        to_date=date(2025, 12, 31),
        slab_in_days=30,
        reduction_percent=Decimal("5"),
        max_commission_percent=Decimal("20"),
        min_commission_percent=Decimal("5"),
        credit_days=15,
    )
    defaults.update(overrides)
    return AgreementCreateRequest(**defaults)


# ───────────────────────────────── list ─────────────────────────────────


async def test_list_maps_items_and_echoes_pagination() -> None:
    service = FakeAgreementService()
    result = await ctrl.list_agreements(
        skip=5, limit=10, vendor_id=None, service=service
    )
    assert result.total == 2
    assert result.skip == 5
    assert result.limit == 10
    assert len(result.items) == 2
    assert service.list_args == (5, 10, None)


async def test_list_passes_vendor_filter() -> None:
    service = FakeAgreementService()
    vendor_id = uuid4()
    await ctrl.list_agreements(skip=0, limit=20, vendor_id=vendor_id, service=service)
    assert service.list_args == (0, 20, vendor_id)


# ──────────────────────────────── create ────────────────────────────────


async def test_create_maps_request_to_input_and_response(actor: User) -> None:
    service = FakeAgreementService()
    request = _create_request()
    response = await ctrl.create_agreement(
        request=request, document=None, current_user=actor, service=service
    )
    assert service.created_input.vendor_id == request.vendor_id
    assert service.created_input.product_master_id == request.product_master_id
    assert service.created_input.document is None
    assert response.vendor_id == request.vendor_id
    assert response.status == AgreementStatus.Active


async def test_create_adapts_uploaded_document(actor: User) -> None:
    service = FakeAgreementService()
    upload = _FakeUpload("application/pdf", "agreement.pdf", b"%PDF-1.7 data")
    response = await ctrl.create_agreement(
        request=_create_request(), document=upload, current_user=actor, service=service
    )
    doc = service.created_input.document
    assert doc is not None
    assert doc.content_type == "application/pdf"
    assert doc.size_bytes == len(b"%PDF-1.7 data")
    assert doc.storage_ref == "agreement.pdf"
    assert response.agreement_document_ref == "agreement.pdf"


async def test_create_validation_maps_to_422(actor: User) -> None:
    service = FakeAgreementService()
    service.raise_on_create = MasterValidationError("from_date", "must be <= to_date")
    with pytest.raises(HTTPException) as exc:
        await ctrl.create_agreement(
            request=_create_request(),
            document=None,
            current_user=actor,
            service=service,
        )
    assert exc.value.status_code == status.HTTP_422_UNPROCESSABLE_ENTITY
    assert exc.value.detail == {"field": "from_date", "reason": "must be <= to_date"}


async def test_create_overlap_conflict_maps_to_409(actor: User) -> None:
    service = FakeAgreementService()
    service.raise_on_create = MasterConflictError("overlapping active agreement")
    with pytest.raises(HTTPException) as exc:
        await ctrl.create_agreement(
            request=_create_request(),
            document=None,
            current_user=actor,
            service=service,
        )
    assert exc.value.status_code == status.HTTP_409_CONFLICT


# ───────────────────────────────── get ──────────────────────────────────


async def test_get_unknown_maps_to_404() -> None:
    service = FakeAgreementService()
    service.raise_on_get = MasterNotFoundError("Agreement", uuid4())
    with pytest.raises(HTTPException) as exc:
        await ctrl.get_agreement(agreement_id=uuid4(), service=service)
    assert exc.value.status_code == status.HTTP_404_NOT_FOUND


# ──────────────────────────────── update ────────────────────────────────


async def test_update_translates_unset_for_omitted_fields(actor: User) -> None:
    service = FakeAgreementService()
    request = AgreementUpdateRequest(credit_days=20)
    await ctrl.update_agreement(
        agreement_id=uuid4(),
        request=request,
        document=None,
        current_user=actor,
        service=service,
    )
    patch = service.update_patch
    assert patch.credit_days == 20
    assert patch.vendor_id is UNSET
    assert patch.product_master_id is UNSET
    assert patch.from_date is UNSET
    assert patch.to_date is UNSET
    assert patch.document is UNSET


async def test_update_applies_uploaded_document(actor: User) -> None:
    service = FakeAgreementService()
    upload = _FakeUpload("image/png", "scan.png", b"\x89PNG bytes")
    await ctrl.update_agreement(
        agreement_id=uuid4(),
        request=AgreementUpdateRequest(),
        document=upload,
        current_user=actor,
        service=service,
    )
    patch = service.update_patch
    assert patch.document is not UNSET
    assert patch.document.content_type == "image/png"
    assert patch.document.storage_ref == "scan.png"


async def test_update_unknown_maps_to_404(actor: User) -> None:
    service = FakeAgreementService()
    service.raise_on_update = MasterNotFoundError("Agreement", uuid4())
    with pytest.raises(HTTPException) as exc:
        await ctrl.update_agreement(
            agreement_id=uuid4(),
            request=AgreementUpdateRequest(),
            document=None,
            current_user=actor,
            service=service,
        )
    assert exc.value.status_code == status.HTTP_404_NOT_FOUND


# ───────────────────────────────── renew ────────────────────────────────


async def test_renew_maps_request_and_marks_renewal(actor: User) -> None:
    service = FakeAgreementService()
    prior_id = uuid4()
    request = AgreementRenewRequest(
        from_date=date(2026, 1, 1), to_date=date(2026, 12, 31)
    )
    response = await ctrl.renew_agreement(
        agreement_id=prior_id,
        request=request,
        document=None,
        current_user=actor,
        service=service,
    )
    assert service.renew_input.from_date == date(2026, 1, 1)
    assert response.agreement_type == AgreementType.Renewal
    assert response.prior_agreement_id == prior_id


async def test_renew_unknown_maps_to_404(actor: User) -> None:
    service = FakeAgreementService()
    service.raise_on_renew = MasterNotFoundError("Agreement", uuid4())
    request = AgreementRenewRequest(
        from_date=date(2026, 1, 1), to_date=date(2026, 12, 31)
    )
    with pytest.raises(HTTPException) as exc:
        await ctrl.renew_agreement(
            agreement_id=uuid4(),
            request=request,
            document=None,
            current_user=actor,
            service=service,
        )
    assert exc.value.status_code == status.HTTP_404_NOT_FOUND


# ──────────────────────────────── delete ────────────────────────────────


async def test_delete_returns_204(actor: User) -> None:
    service = FakeAgreementService()
    response = await ctrl.delete_agreement(
        agreement_id=uuid4(), current_user=actor, service=service
    )
    assert response.status_code == status.HTTP_204_NO_CONTENT


async def test_delete_unknown_maps_to_404(actor: User) -> None:
    service = FakeAgreementService()
    service.raise_on_delete = MasterNotFoundError("Agreement", uuid4())
    with pytest.raises(HTTPException) as exc:
        await ctrl.delete_agreement(
            agreement_id=uuid4(), current_user=actor, service=service
        )
    assert exc.value.status_code == status.HTTP_404_NOT_FOUND
