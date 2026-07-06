# Feature: lacm-masters, Property 53: Unparseable bulk file stores nothing.
"""Property-based test for whole-file rejection of unparseable bulk uploads.

Property 53: Unparseable bulk file stores nothing.

**Validates: Requirements 19.2**

*For any* bulk-upload file that does not conform to the expected structure and
cannot be parsed, :class:`BulkUploadService.process` rejects the entire file by
raising :class:`MasterValidationError` and stores **nothing** — none of the five
underlying master services receive a create call.

Strategy
--------
Each Hypothesis example draws a target ``entity_type`` (one of the six masters
that support bulk import) together with a payload that is *guaranteed* to be
non-conforming, produced in one of three independent ways:

* ``non_utf8`` — arbitrary ASCII text with a lone ``0xFF`` byte spliced in.
  ``0xFF`` is never a valid UTF-8 byte, so decoding always fails.
* ``missing_columns`` — a header that keeps only a proper subset of the
  entity's required columns (plus guaranteed-non-matching ``col_*`` filler), so
  at least one required column is always absent.
* ``empty`` — an empty / whitespace-only / header-less payload that yields no
  usable header row.

Because every generated payload is rejectable by construction, the test pins the
*whole-file rejection* contract independently of the service's parsing internals
rather than mirroring them. The five master services are replaced with
lightweight in-memory recording fakes (duck-typed against the service ports, not
mocks); the resolution repositories are tiny code-lookup fakes; and a fake
session provides ``begin_nested`` as a no-op savepoint. The async service is
driven with ``asyncio.run`` because each Hypothesis example is independent.
"""

from __future__ import annotations

import asyncio
from uuid import UUID, uuid4

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from src.application.exceptions.application_exceptions import (
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
        return False


class FakeSession:
    """Provides ``begin_nested`` as a no-op savepoint context manager."""

    def begin_nested(self) -> _Nested:
        return _Nested()


class _RecordingService:
    """Base fake master service: records every create call it receives."""

    def __init__(self) -> None:
        self.created: list[object] = []


class FakeVendorService(_RecordingService):
    async def create_vendor(self, data: object, actor: User) -> None:
        self.created.append(data)


class FakeCustomerService(_RecordingService):
    async def create_customer(self, data: object, actor: User) -> None:
        self.created.append(data)


class FakeProductService(_RecordingService):
    async def create_master(self, data: object, actor: User) -> None:
        self.created.append(("master", data))

    async def create_detail(self, data: object, actor: User) -> None:
        self.created.append(("detail", data))


class FakeAgreementService(_RecordingService):
    async def create_agreement(self, data: object, actor: User) -> None:
        self.created.append(data)


class FakeMappingService(_RecordingService):
    async def create_mapping(self, data: object, actor: User) -> None:
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


def _build_service() -> tuple[BulkUploadService, list[_RecordingService]]:
    """Construct the service over fresh recording fakes; return both."""
    vendor_service = FakeVendorService()
    customer_service = FakeCustomerService()
    product_service = FakeProductService()
    agreement_service = FakeAgreementService()
    mapping_service = FakeMappingService()
    service = BulkUploadService(
        session=FakeSession(),  # type: ignore[arg-type]
        vendor_service=vendor_service,  # type: ignore[arg-type]
        customer_service=customer_service,  # type: ignore[arg-type]
        product_service=product_service,  # type: ignore[arg-type]
        agreement_service=agreement_service,  # type: ignore[arg-type]
        mapping_service=mapping_service,  # type: ignore[arg-type]
        vendor_repo=FakeVendorRepo(),  # type: ignore[arg-type]
        customer_repo=FakeCustomerRepo(),  # type: ignore[arg-type]
        product_repo=FakeProductRepo(),  # type: ignore[arg-type]
    )
    recorders: list[_RecordingService] = [
        vendor_service,
        customer_service,
        product_service,
        agreement_service,
        mapping_service,
    ]
    return service, recorders


# ─────────────────────────────── Strategy ─────────────────────────────

# Required columns per importable entity (mirrors the service's dispatch).
_REQUIRED: dict[str, list[str]] = {
    "vendor": ["vendor_code", "vendor_name", "vendor_email"],
    "customer": ["customer_code", "customer_name"],
    "product_master": ["basic_material_code", "product_name"],
    "product_detail": ["child_code", "product_master_code"],
    "agreement": ["vendor_code", "product_detail_code", "from_date", "to_date"],
    "mapping": ["vendor_code", "customer_code", "validity_from", "validity_to"],
}

# Printable ASCII that never collides with required column names or commas.
_ascii_text = st.text(
    alphabet=st.characters(min_codepoint=32, max_codepoint=126),
    max_size=20,
).filter(lambda s: "," not in s)


@st.composite
def _nonconforming(draw: st.DrawFn) -> tuple[str, bytes | str]:
    """Draw an ``(entity_type, payload)`` pair guaranteed to be rejectable."""
    entity = draw(st.sampled_from(sorted(_REQUIRED)))
    required = _REQUIRED[entity]
    mode = draw(st.sampled_from(["non_utf8", "missing_columns", "empty"]))

    if mode == "non_utf8":
        prefix = draw(_ascii_text)
        suffix = draw(_ascii_text)
        # 0xFF is never valid in UTF-8, so utf-8-sig decoding always fails.
        payload = prefix.encode("ascii") + b"\xff" + suffix.encode("ascii")
        return entity, payload

    if mode == "empty":
        blank = draw(st.sampled_from([b"", "", "   ", "\n", ",", "\n\n"]))
        return entity, blank

    # missing_columns: keep a *proper* subset of the required columns so at
    # least one required column is always absent, plus non-matching filler.
    kept = draw(
        st.lists(
            st.sampled_from(required),
            unique=True,
            max_size=len(required) - 1,
        )
    )
    extra_count = draw(st.integers(min_value=0, max_value=3))
    extras = [f"col_{i}" for i in range(extra_count)]
    header_cols = list(kept) + extras
    if not header_cols:
        # Guarantee a non-blank header that still omits every required column.
        header_cols = ["col_0"]
    header = ",".join(header_cols)

    data_row_count = draw(st.integers(min_value=0, max_value=3))
    width = len(header_cols)
    rows = [",".join(["x"] * width) for _ in range(data_row_count)]
    payload = "\n".join([header, *rows]) + "\n"
    return entity, payload


# ──────────────────────────────── Test ────────────────────────────────


@settings(max_examples=20)
@given(case=_nonconforming())
def test_unparseable_file_rejected_and_stores_nothing(
    case: tuple[str, bytes | str],
) -> None:
    """A non-conforming file is rejected whole and no master service is called."""
    entity_type, payload = case

    async def scenario() -> None:
        actor = User(id=uuid4(), username="admin", is_active=True)
        service, recorders = _build_service()

        with pytest.raises(MasterValidationError):
            await service.process(entity_type, FakeUpload(payload), actor)

        # Whole-file rejection: nothing was stored anywhere (Req 19.2).
        for recorder in recorders:
            assert recorder.created == []

    asyncio.run(scenario())
