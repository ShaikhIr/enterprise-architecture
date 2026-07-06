# Feature: lacm-masters, Property 52: Bulk upload row accounting and independence.
"""Property-based test for per-row accounting and independence of bulk uploads.

Property 52: Bulk upload row accounting and independence.

**Validates: Requirements 19.1, 19.3, 19.4, 19.5, 19.6**

*For any* bulk-upload file that parses, each row is processed independently
(Req 19.1): valid rows are stored, rows failing validation (Req 19.3) or
referencing an unresolvable Business Code (Req 19.5) are skipped with a
positional row-level error (naming the unresolved code where applicable),
resolvable Business Codes are converted to the referenced records' UUIDs before
storing (Req 19.4), and the final report (Req 19.6) satisfies
``received == stored + skipped`` with exactly one error entry per skipped row.

Strategy
--------
Each Hypothesis example fixes a pool of *known* Vendor and Customer Business
Codes (seeded into the resolution repositories with freshly minted UUIDs) and
then draws a list of Vendor-Customer Mapping rows, each belonging to one of five
independent categories:

* ``good`` — both codes resolvable and the (delegated) mapping service accepts
  the row, so it is stored. The expected ``vendor_id``/``customer_id`` UUIDs are
  remembered to confirm Business-Code → UUID resolution (Req 19.4).
* ``unresolvable_vendor`` / ``unresolvable_customer`` — one code uses a prefix
  that can never collide with a known code, so resolution fails and the row is
  skipped with the offending code named in the error (Req 19.5).
* ``bad_date`` — resolvable codes but a non-ISO ``validity_from`` cell, so cell
  coercion rejects the row (validation failure, Req 19.3).
* ``service_reject`` — resolvable codes and valid dates, but the row trips a
  deterministic rule enforced by the delegated mapping service (its ``from`` and
  ``to`` dates are equal), exercising the *delegated* validation path (Req 19.3).

Rows are shuffled freely by the list strategy, so the test pins independence and
positional accounting regardless of how good and bad rows interleave. The five
master services are lightweight in-memory recording fakes (the mapping fake also
applies the equal-dates rejection rule); the resolution repositories are tiny
code-lookup fakes; and a fake session provides ``begin_nested`` as a no-op
savepoint. The async service is driven with ``asyncio.run`` because each
Hypothesis example is independent.
"""

from __future__ import annotations

import asyncio
from uuid import UUID, uuid4

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
        # Never suppress; the service's try/except classifies the row.
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
    """Records created mappings; rejects rows whose validity dates are equal.

    The equal-dates rule stands in for the real service's delegated validation
    so the property can exercise the "row fails validation in the delegated
    service" path (Req 19.3) deterministically.
    """

    async def create_mapping(self, data, actor: User) -> None:
        if data.validity_from == data.validity_to:
            raise MasterValidationError(
                "validity", "validity_from must be before validity_to"
            )
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


def _build_service() -> tuple[
    BulkUploadService, FakeMappingService, FakeVendorRepo, FakeCustomerRepo
]:
    """Construct the service over fresh fakes; return the parts under test."""
    mapping_service = FakeMappingService()
    vendor_repo = FakeVendorRepo()
    customer_repo = FakeCustomerRepo()
    service = BulkUploadService(
        session=FakeSession(),  # type: ignore[arg-type]
        vendor_service=FakeVendorService(),  # type: ignore[arg-type]
        customer_service=FakeCustomerService(),  # type: ignore[arg-type]
        product_service=FakeProductService(),  # type: ignore[arg-type]
        agreement_service=FakeAgreementService(),  # type: ignore[arg-type]
        mapping_service=mapping_service,  # type: ignore[arg-type]
        vendor_repo=vendor_repo,  # type: ignore[arg-type]
        customer_repo=customer_repo,  # type: ignore[arg-type]
        product_repo=FakeProductRepo(),  # type: ignore[arg-type]
    )
    return service, mapping_service, vendor_repo, customer_repo


# ─────────────────────────────── Strategy ─────────────────────────────

# Fixed, always-parseable dates. ``good`` rows use two distinct dates so the
# delegated mapping service accepts them; ``service_reject`` rows use equal
# dates to trip its delegated-validation rule.
_GOOD_FROM = "2024-01-01"
_GOOD_TO = "2024-12-31"
_EQUAL_DATE = "2024-06-15"

_CATEGORIES = [
    "good",
    "unresolvable_vendor",
    "unresolvable_customer",
    "bad_date",
    "service_reject",
]


@st.composite
def _scenario(draw: st.DrawFn) -> dict:
    """Draw known code pools plus a list of categorised mapping rows."""
    n_vendors = draw(st.integers(min_value=1, max_value=4))
    n_customers = draw(st.integers(min_value=1, max_value=4))
    known_vendor_codes = [f"V{i}" for i in range(n_vendors)]
    known_customer_codes = [f"C{i}" for i in range(n_customers)]

    known_vendor = st.sampled_from(known_vendor_codes)
    known_customer = st.sampled_from(known_customer_codes)
    # Unknown codes use the ``U`` prefix, which can never equal a ``V``/``C``
    # known code, so they are guaranteed unresolvable.
    unknown_code = st.integers(min_value=0, max_value=99).map(lambda n: f"U{n}")

    @st.composite
    def _row(row_draw: st.DrawFn) -> dict:
        category = row_draw(st.sampled_from(_CATEGORIES))
        if category == "good":
            return {
                "category": "good",
                "vendor_code": row_draw(known_vendor),
                "customer_code": row_draw(known_customer),
                "validity_from": _GOOD_FROM,
                "validity_to": _GOOD_TO,
            }
        if category == "unresolvable_vendor":
            code = row_draw(unknown_code)
            return {
                "category": "unresolvable_vendor",
                "vendor_code": code,
                "customer_code": row_draw(known_customer),
                "validity_from": _GOOD_FROM,
                "validity_to": _GOOD_TO,
                "named_code": code,
            }
        if category == "unresolvable_customer":
            code = row_draw(unknown_code)
            return {
                "category": "unresolvable_customer",
                "vendor_code": row_draw(known_vendor),
                "customer_code": code,
                "validity_from": _GOOD_FROM,
                "validity_to": _GOOD_TO,
                "named_code": code,
            }
        if category == "bad_date":
            return {
                "category": "bad_date",
                "vendor_code": row_draw(known_vendor),
                "customer_code": row_draw(known_customer),
                "validity_from": "not-a-date",
                "validity_to": _GOOD_TO,
            }
        # service_reject: resolvable + valid dates, but from == to.
        return {
            "category": "service_reject",
            "vendor_code": row_draw(known_vendor),
            "customer_code": row_draw(known_customer),
            "validity_from": _EQUAL_DATE,
            "validity_to": _EQUAL_DATE,
        }

    rows = draw(st.lists(_row(), min_size=0, max_size=10))
    return {
        "known_vendor_codes": known_vendor_codes,
        "known_customer_codes": known_customer_codes,
        "rows": rows,
    }


def _to_csv(rows: list[dict]) -> str:
    header = "vendor_code,customer_code,validity_from,validity_to"
    lines = [
        f"{r['vendor_code']},{r['customer_code']},"
        f"{r['validity_from']},{r['validity_to']}"
        for r in rows
    ]
    return "\n".join([header, *lines]) + "\n"


# ──────────────────────────────── Test ────────────────────────────────


@settings(max_examples=20)
@given(scenario=_scenario())
def test_bulk_row_accounting_and_independence(scenario: dict) -> None:
    """Rows are processed independently and the report accounts for every row."""
    rows = scenario["rows"]
    known_vendor_codes = scenario["known_vendor_codes"]
    known_customer_codes = scenario["known_customer_codes"]

    async def run() -> None:
        actor = User(id=uuid4(), username="admin", is_active=True)
        service, mapping_service, vendor_repo, customer_repo = _build_service()

        # Seed the resolution repositories with the known codes → UUIDs.
        vendor_uuids = {code: uuid4() for code in known_vendor_codes}
        customer_uuids = {code: uuid4() for code in known_customer_codes}
        for code, vid in vendor_uuids.items():
            vendor_repo.by_code[code] = _Resolvable(vid)
        for code, cid in customer_uuids.items():
            customer_repo.by_code[code] = _Resolvable(cid)

        report = await service.process("mapping", FakeUpload(_to_csv(rows)), actor)

        good_indices = [
            i for i, r in enumerate(rows, start=1) if r["category"] == "good"
        ]
        skipped_indices = [
            i for i, r in enumerate(rows, start=1) if r["category"] != "good"
        ]

        # Req 19.6: report counts every received row.
        assert report.received == len(rows)
        assert report.stored == len(good_indices)
        assert report.skipped == len(skipped_indices)
        # Accounting invariant always holds.
        assert report.received == report.stored + report.skipped

        # Exactly one positional error per skipped row, at the right positions.
        assert len(report.errors) == report.skipped
        assert [e.row_number for e in report.errors] == skipped_indices

        # Req 19.5: unresolvable-code errors name the offending Business Code.
        errors_by_row = {e.row_number: e for e in report.errors}
        for index, row in enumerate(rows, start=1):
            if row["category"] in (
                "unresolvable_vendor",
                "unresolvable_customer",
            ):
                assert row["named_code"] in errors_by_row[index].reason

        # Req 19.1 + 19.4: every good row was stored independently of the bad
        # rows, in order, with its Business Codes resolved to the right UUIDs.
        assert len(mapping_service.created) == len(good_indices)
        good_rows = [r for r in rows if r["category"] == "good"]
        for created, row in zip(mapping_service.created, good_rows):
            assert created.vendor_id == vendor_uuids[row["vendor_code"]]
            assert created.customer_id == customer_uuids[row["customer_code"]]

    asyncio.run(run())
