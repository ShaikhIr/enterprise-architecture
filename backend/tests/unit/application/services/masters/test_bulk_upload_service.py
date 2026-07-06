"""
Unit tests for :class:`BulkUploadService` (task 14.1).

These exercise the service's own logic — CSV parsing / whole-file rejection,
per-row savepoint isolation and accounting, Business-Code resolution, and the
``received == stored + skipped`` invariant — in isolation. The five master
services are replaced with lightweight in-memory fakes that record their create
calls (and can be told to reject specific rows), and the resolution repositories
are tiny fakes exposing only the code-lookup methods the service uses. A fake
session provides ``begin_nested`` as a no-op async context manager.

Covers Requirements 19.1–19.6.
"""

from __future__ import annotations

from uuid import UUID, uuid4

import pytest

from src.application.exceptions.application_exceptions import (
    MasterConflictError,
    MasterValidationError,
)
from src.application.services.masters.bulk_upload_service import (
    BulkUploadService,
)
from src.domain.entities.user import User


# ─────────────────────────────── Fakes ────────────────────────────────


class _Nested:
    async def __aenter__(self) -> "_Nested":
        return self

    async def __aexit__(self, *_exc: object) -> bool:
        # Never suppress; the service's try/except classifies the row.
        return False


class FakeSession:
    """Provides ``begin_nested`` as a no-op savepoint context manager."""

    def begin_nested(self) -> _Nested:
        return _Nested()


class _RecordingService:
    """Base fake master service: records inputs, optionally rejects some."""

    def __init__(self) -> None:
        self.created: list[object] = []
        self.reject_when = None  # Callable[[input], str | None]

    def _maybe_reject(self, data: object) -> None:
        if self.reject_when is not None:
            reason = self.reject_when(data)
            if reason is not None:
                raise MasterValidationError("row", reason)


class FakeVendorService(_RecordingService):
    async def create_vendor(self, data: object, actor: User) -> None:
        self._maybe_reject(data)
        self.created.append(data)


class FakeCustomerService(_RecordingService):
    async def create_customer(self, data: object, actor: User) -> None:
        self._maybe_reject(data)
        self.created.append(data)


class FakeProductService(_RecordingService):
    async def create_master(self, data: object, actor: User) -> None:
        self._maybe_reject(data)
        self.created.append(("master", data))

    async def create_detail(self, data: object, actor: User) -> None:
        self._maybe_reject(data)
        self.created.append(("detail", data))


class FakeAgreementService(_RecordingService):
    async def create_agreement(self, data: object, actor: User) -> None:
        self._maybe_reject(data)
        self.created.append(data)


class FakeMappingService(_RecordingService):
    async def create_mapping(self, data: object, actor: User) -> None:
        self._maybe_reject(data)
        self.created.append(data)


class _Resolvable:
    def __init__(self, id: UUID) -> None:
        self.id = id


class FakeVendorRepo:
    def __init__(self) -> None:
        self.by_code: dict[str, _Resolvable] = {}

    async def get_by_code(self, vendor_code: str):
        return self.by_code.get(vendor_code)


class FakeCustomerRepo:
    def __init__(self) -> None:
        self.by_code: dict[str, _Resolvable] = {}

    async def get_by_customer_code(self, customer_code: str):
        return self.by_code.get(customer_code)


class FakeProductRepo:
    def __init__(self) -> None:
        self.masters_by_code: dict[str, _Resolvable] = {}
        self.details_by_code: dict[str, _Resolvable] = {}

    async def get_master_by_basic_material_code(self, basic_material_code: str):
        return self.masters_by_code.get(basic_material_code)

    async def get_detail_by_child_code(self, child_code: str):
        return self.details_by_code.get(child_code)


class FakeUpload:
    """Minimal stand-in for an uploaded file with an async ``read``."""

    def __init__(self, data: bytes | str) -> None:
        self._data = data

    async def read(self, size: int = -1) -> bytes | str:
        return self._data


# ─────────────────────────────── Fixtures ─────────────────────────────


@pytest.fixture
def vendor_service() -> FakeVendorService:
    return FakeVendorService()


@pytest.fixture
def customer_service() -> FakeCustomerService:
    return FakeCustomerService()


@pytest.fixture
def product_service() -> FakeProductService:
    return FakeProductService()


@pytest.fixture
def agreement_service() -> FakeAgreementService:
    return FakeAgreementService()


@pytest.fixture
def mapping_service() -> FakeMappingService:
    return FakeMappingService()


@pytest.fixture
def vendor_repo() -> FakeVendorRepo:
    return FakeVendorRepo()


@pytest.fixture
def customer_repo() -> FakeCustomerRepo:
    return FakeCustomerRepo()


@pytest.fixture
def product_repo() -> FakeProductRepo:
    return FakeProductRepo()


@pytest.fixture
def service(
    vendor_service: FakeVendorService,
    customer_service: FakeCustomerService,
    product_service: FakeProductService,
    agreement_service: FakeAgreementService,
    mapping_service: FakeMappingService,
    vendor_repo: FakeVendorRepo,
    customer_repo: FakeCustomerRepo,
    product_repo: FakeProductRepo,
) -> BulkUploadService:
    return BulkUploadService(
        session=FakeSession(),  # type: ignore[arg-type]
        vendor_service=vendor_service,  # type: ignore[arg-type]
        customer_service=customer_service,  # type: ignore[arg-type]
        product_service=product_service,  # type: ignore[arg-type]
        agreement_service=agreement_service,  # type: ignore[arg-type]
        mapping_service=mapping_service,  # type: ignore[arg-type]
        vendor_repo=vendor_repo,  # type: ignore[arg-type]
        customer_repo=customer_repo,  # type: ignore[arg-type]
        product_repo=product_repo,  # type: ignore[arg-type]
    )


@pytest.fixture
def actor() -> User:
    return User(id=uuid4(), username="admin", is_active=True)


# ─────────────────────────── Unknown entity type ──────────────────────


async def test_unknown_entity_type_is_rejected(
    service: BulkUploadService, actor: User
) -> None:
    upload = FakeUpload(b"vendor_code,vendor_name,vendor_email\n")
    with pytest.raises(MasterValidationError):
        await service.process("widget", upload, actor)


# ───────────────────── Unparseable file (Req 19.2) ─────────────────────


async def test_missing_required_columns_rejects_whole_file(
    service: BulkUploadService, vendor_service: FakeVendorService, actor: User
) -> None:
    # Header lacks vendor_email → whole-file rejection, nothing stored.
    upload = FakeUpload(b"vendor_code,vendor_name\nV1,Acme\n")
    with pytest.raises(MasterValidationError):
        await service.process("vendor", upload, actor)
    assert vendor_service.created == []


async def test_non_utf8_file_rejects_whole_file(
    service: BulkUploadService, vendor_service: FakeVendorService, actor: User
) -> None:
    upload = FakeUpload(b"\xff\xfe\x00bad bytes")
    with pytest.raises(MasterValidationError):
        await service.process("vendor", upload, actor)
    assert vendor_service.created == []


# ───────────────────── Row accounting & independence ──────────────────


async def test_vendor_rows_all_valid_are_stored(
    service: BulkUploadService, vendor_service: FakeVendorService, actor: User
) -> None:
    csv_data = (
        "vendor_code,vendor_name,vendor_email\n"
        "V1,Acme,a@x.com\n"
        "V2,Beta,b@x.com\n"
    )
    report = await service.process("vendor", FakeUpload(csv_data), actor)

    assert report.received == 2
    assert report.stored == 2
    assert report.skipped == 0
    assert report.errors == []
    assert report.received == report.stored + report.skipped
    assert len(vendor_service.created) == 2


async def test_invalid_row_skipped_with_positional_error_batch_continues(
    service: BulkUploadService, vendor_service: FakeVendorService, actor: User
) -> None:
    # The fake service rejects any row whose vendor_name is "BAD".
    vendor_service.reject_when = lambda d: (
        "bad name" if getattr(d, "vendor_name", "") == "BAD" else None
    )
    csv_data = (
        "vendor_code,vendor_name,vendor_email\n"
        "V1,Acme,a@x.com\n"
        "V2,BAD,b@x.com\n"
        "V3,Gamma,c@x.com\n"
    )
    report = await service.process("vendor", FakeUpload(csv_data), actor)

    assert report.received == 3
    assert report.stored == 2
    assert report.skipped == 1
    assert report.received == report.stored + report.skipped
    assert len(report.errors) == 1
    # Positional error points at the second data row.
    assert report.errors[0].row_number == 2
    # The batch continued: rows 1 and 3 were stored.
    assert len(vendor_service.created) == 2


async def test_blank_lines_do_not_inflate_received(
    service: BulkUploadService, actor: User
) -> None:
    csv_data = (
        "vendor_code,vendor_name,vendor_email\n"
        "V1,Acme,a@x.com\n"
        "\n"
        "   \n"
        "V2,Beta,b@x.com\n"
    )
    report = await service.process("vendor", FakeUpload(csv_data), actor)
    assert report.received == 2
    assert report.stored == 2


# ───────────── Business-Code resolution (Req 19.4 / 19.5) ──────────────


async def test_mapping_resolves_business_codes_to_uuids(
    service: BulkUploadService,
    mapping_service: FakeMappingService,
    vendor_repo: FakeVendorRepo,
    customer_repo: FakeCustomerRepo,
    actor: User,
) -> None:
    vendor_id, customer_id = uuid4(), uuid4()
    vendor_repo.by_code["V1"] = _Resolvable(vendor_id)
    customer_repo.by_code["C1"] = _Resolvable(customer_id)

    csv_data = (
        "vendor_code,customer_code,validity_from,validity_to\n"
        "V1,C1,2024-01-01,2024-12-31\n"
    )
    report = await service.process("mapping", FakeUpload(csv_data), actor)

    assert report.stored == 1
    assert report.skipped == 0
    created = mapping_service.created[0]
    # Codes were resolved to the referenced records' UUIDs before storing.
    assert created.vendor_id == vendor_id
    assert created.customer_id == customer_id


async def test_unresolvable_code_skips_row_naming_the_code(
    service: BulkUploadService,
    mapping_service: FakeMappingService,
    vendor_repo: FakeVendorRepo,
    customer_repo: FakeCustomerRepo,
    actor: User,
) -> None:
    # Only V1 resolves; the row references the unknown vendor code "V9".
    vendor_repo.by_code["V1"] = _Resolvable(uuid4())
    customer_repo.by_code["C1"] = _Resolvable(uuid4())

    csv_data = (
        "vendor_code,customer_code,validity_from,validity_to\n"
        "V9,C1,2024-01-01,2024-12-31\n"
    )
    report = await service.process("mapping", FakeUpload(csv_data), actor)

    assert report.received == 1
    assert report.stored == 0
    assert report.skipped == 1
    assert mapping_service.created == []
    assert report.errors[0].row_number == 1
    assert "V9" in report.errors[0].reason


async def test_agreement_resolves_vendor_and_detail_codes(
    service: BulkUploadService,
    agreement_service: FakeAgreementService,
    vendor_repo: FakeVendorRepo,
    product_repo: FakeProductRepo,
    actor: User,
) -> None:
    vendor_id, detail_id = uuid4(), uuid4()
    vendor_repo.by_code["V1"] = _Resolvable(vendor_id)
    product_repo.details_by_code["CH1"] = _Resolvable(detail_id)

    csv_data = (
        "vendor_code,product_detail_code,from_date,to_date,"
        "slab_in_days,credit_days\n"
        "V1,CH1,2024-01-01,2024-12-31,30,45\n"
    )
    report = await service.process("agreement", FakeUpload(csv_data), actor)

    assert report.stored == 1
    created = agreement_service.created[0]
    assert created.vendor_id == vendor_id
    assert created.product_detail_id == detail_id
    assert created.slab_in_days == 30
    assert created.credit_days == 45


async def test_product_detail_resolves_master_code(
    service: BulkUploadService,
    product_service: FakeProductService,
    product_repo: FakeProductRepo,
    actor: User,
) -> None:
    master_id = uuid4()
    product_repo.masters_by_code["BM1"] = _Resolvable(master_id)

    csv_data = (
        "child_code,product_master_code,mrp,rate,gst_percent\n"
        "CH1,BM1,100.50,90.00,18\n"
    )
    report = await service.process("product_detail", FakeUpload(csv_data), actor)

    assert report.stored == 1
    kind, data = product_service.created[0]
    assert kind == "detail"
    assert data.product_master_id == master_id


# ────────────────────── Bad typed cells skip the row ───────────────────


async def test_bad_date_cell_skips_row(
    service: BulkUploadService,
    mapping_service: FakeMappingService,
    vendor_repo: FakeVendorRepo,
    customer_repo: FakeCustomerRepo,
    actor: User,
) -> None:
    vendor_repo.by_code["V1"] = _Resolvable(uuid4())
    customer_repo.by_code["C1"] = _Resolvable(uuid4())

    csv_data = (
        "vendor_code,customer_code,validity_from,validity_to\n"
        "V1,C1,not-a-date,2024-12-31\n"
    )
    report = await service.process("mapping", FakeUpload(csv_data), actor)

    assert report.received == 1
    assert report.stored == 0
    assert report.skipped == 1
    assert mapping_service.created == []
    assert report.received == report.stored + report.skipped
