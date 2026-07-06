"""
Unit tests for the Bulk Upload controller.

The controller is intentionally thin, so these tests exercise its real
responsibilities in isolation (without standing up the FastAPI app, which is
wired in a later task):

* routing the uploaded file + ``entity_type`` to ``BulkUploadService.process``,
* adapting the returned ``BulkUploadReport`` (and its ``BulkRowError`` rows) to
  the ``BulkUploadReportResponse`` schema (Req 19.6), and
* master-exception-to-HTTP-status mapping — an unparseable file or unknown
  ``entity_type`` (``MasterValidationError``) maps to 422 (Req 19.2), with
  conflict → 409 and not-found → 404 for completeness.

The async route handler is invoked directly with a fake service.
"""

from __future__ import annotations

from uuid import uuid4

import pytest
from fastapi import HTTPException, status

from src.api.v1.endpoints.masters import bulk_upload_controller as ctrl
from src.application.exceptions.application_exceptions import (
    MasterConflictError,
    MasterNotFoundError,
    MasterValidationError,
)
from src.application.services.masters.bulk_upload_service import (
    BulkRowError,
    BulkUploadReport,
)
from src.domain.entities.user import User


@pytest.fixture
def actor() -> User:
    return User(id=uuid4(), username="tester", is_active=True)


class _FakeUpload:
    """Minimal stand-in for ``UploadFile``."""

    def __init__(self, filename: str, data: bytes) -> None:
        self.filename = filename
        self._data = data

    async def read(self, size: int = -1) -> bytes:
        return self._data


class FakeBulkUploadService:
    """Records the call and returns a canned report (or raises)."""

    def __init__(self) -> None:
        self.process_args: tuple | None = None
        self.report = BulkUploadReport(received=0, stored=0, skipped=0, errors=[])
        self.raise_on_process: Exception | None = None

    async def process(self, entity_type, file, actor):  # noqa: ANN001
        if self.raise_on_process is not None:
            raise self.raise_on_process
        self.process_args = (entity_type, file, actor)
        return self.report


async def test_routes_entity_type_and_file_to_service(actor: User) -> None:
    service = FakeBulkUploadService()
    upload = _FakeUpload("vendors.csv", b"vendor_code,vendor_name,vendor_email\n")
    await ctrl.bulk_upload(
        entity_type="vendor", file=upload, current_user=actor, service=service
    )
    assert service.process_args is not None
    entity_type, file, passed_actor = service.process_args
    assert entity_type == "vendor"
    assert file is upload
    assert passed_actor is actor


async def test_maps_report_to_response(actor: User) -> None:
    service = FakeBulkUploadService()
    service.report = BulkUploadReport(
        received=3,
        stored=2,
        skipped=1,
        errors=[BulkRowError(row_number=2, reason="Vendor Code is required")],
    )
    response = await ctrl.bulk_upload(
        entity_type="vendor",
        file=_FakeUpload("vendors.csv", b"data"),
        current_user=actor,
        service=service,
    )
    assert response.received == 3
    assert response.stored == 2
    assert response.skipped == 1
    # Accounting invariant surfaced verbatim (Req 19.6).
    assert response.received == response.stored + response.skipped
    assert len(response.errors) == 1
    assert response.errors[0].row_number == 2
    assert response.errors[0].reason == "Vendor Code is required"


async def test_unknown_entity_type_maps_to_422(actor: User) -> None:
    service = FakeBulkUploadService()
    service.raise_on_process = MasterValidationError(
        "entity_type", "Unsupported bulk-upload entity type 'widgets'"
    )
    with pytest.raises(HTTPException) as exc:
        await ctrl.bulk_upload(
            entity_type="widgets",
            file=_FakeUpload("x.csv", b"data"),
            current_user=actor,
            service=service,
        )
    assert exc.value.status_code == status.HTTP_422_UNPROCESSABLE_ENTITY
    assert exc.value.detail == {
        "field": "entity_type",
        "reason": "Unsupported bulk-upload entity type 'widgets'",
    }


async def test_unparseable_file_maps_to_422(actor: User) -> None:
    service = FakeBulkUploadService()
    service.raise_on_process = MasterValidationError(
        "file", "The uploaded file is missing required columns: vendor_code"
    )
    with pytest.raises(HTTPException) as exc:
        await ctrl.bulk_upload(
            entity_type="vendor",
            file=_FakeUpload("bad.csv", b"nope"),
            current_user=actor,
            service=service,
        )
    assert exc.value.status_code == status.HTTP_422_UNPROCESSABLE_ENTITY
    assert exc.value.detail["field"] == "file"


async def test_conflict_maps_to_409(actor: User) -> None:
    service = FakeBulkUploadService()
    service.raise_on_process = MasterConflictError("conflict")
    with pytest.raises(HTTPException) as exc:
        await ctrl.bulk_upload(
            entity_type="vendor",
            file=_FakeUpload("x.csv", b"data"),
            current_user=actor,
            service=service,
        )
    assert exc.value.status_code == status.HTTP_409_CONFLICT


async def test_not_found_maps_to_404(actor: User) -> None:
    service = FakeBulkUploadService()
    service.raise_on_process = MasterNotFoundError("Vendor", uuid4())
    with pytest.raises(HTTPException) as exc:
        await ctrl.bulk_upload(
            entity_type="vendor",
            file=_FakeUpload("x.csv", b"data"),
            current_user=actor,
            service=service,
        )
    assert exc.value.status_code == status.HTTP_404_NOT_FOUND
