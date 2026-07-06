# Feature: lacm-masters, Property 26: Product Master validation and default.
"""Property-based test for Product Master create/update validation and default.

Property 26: Product Master validation and default.

**Validates: Requirements 9.2, 9.3, 9.4**

*For any* create/update Product Master request, the request is rejected with no
persist/modify when:

* the Basic Material Code or Product Name is missing/empty/whitespace-only
  (Req 9.2), or
* the Basic Material Code duplicates an existing Product Master (Req 9.3, create
  path; the duplicate guard also applies on update against another record).

*For any* valid create request (Basic Material Code and Product Name present and
within bounds, Status omitted), the stored Product Master defaults its Status to
``Active`` and preserves the supplied fields exactly (Req 9.4).

The service is exercised against a real in-memory implementation of
``IProductRepository`` (a fake, not a mock), so the property validates actual
``ProductService`` logic end-to-end through the port. Each Hypothesis example
drives the async service via ``asyncio.run`` so examples remain isolated.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from uuid import UUID, uuid4

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from src.application.exceptions.application_exceptions import (
    MasterConflictError,
    MasterValidationError,
)
from src.application.services.masters.product_service import (
    ProductMasterCreateInput,
    ProductMasterUpdateInput,
    ProductService,
)
from src.domain.entities.masters.product import (
    ProductDetailEntity,
    ProductMasterEntity,
)
from src.domain.entities.user import User
from src.domain.enums.masters import ProductStatus
from src.domain.repositories.masters.product_repository import IProductRepository

# Field length caps aligned with the service's validation limits.
_MAX_BASIC_MATERIAL_CODE_LEN = 50
_MAX_PRODUCT_NAME_LEN = 255
_MAX_THERAPEUTIC_CATEGORY_LEN = 255


class FakeProductRepository(IProductRepository):
    """In-memory ``IProductRepository`` for testing the service in isolation."""

    def __init__(self) -> None:
        self._masters: dict[UUID, ProductMasterEntity] = {}
        self._details: dict[UUID, ProductDetailEntity] = {}

    # --- Product Master ---

    async def create_master(
        self, master: ProductMasterEntity
    ) -> ProductMasterEntity:
        self._masters[master.id] = master
        return master

    async def update_master(
        self, master: ProductMasterEntity
    ) -> ProductMasterEntity:
        self._masters[master.id] = master
        return master

    async def get_master_by_id(
        self, master_id: UUID
    ) -> ProductMasterEntity | None:
        return self._masters.get(master_id)

    async def delete_master(self, master_id: UUID) -> None:
        self._masters.pop(master_id, None)

    async def list_masters(
        self, skip: int = 0, limit: int = 20
    ) -> list[ProductMasterEntity]:
        ordered = sorted(
            self._masters.values(), key=lambda m: m.basic_material_code
        )
        return ordered[skip : skip + limit]

    async def count_masters(self) -> int:
        return len(self._masters)

    async def exists_master_by_basic_material_code(
        self, basic_material_code: str, exclude_id: UUID | None = None
    ) -> bool:
        return any(
            m.basic_material_code == basic_material_code and m.id != exclude_id
            for m in self._masters.values()
        )

    async def get_master_by_basic_material_code(
        self, basic_material_code: str
    ) -> ProductMasterEntity | None:
        for m in self._masters.values():
            if m.basic_material_code == basic_material_code:
                return m
        return None

    async def has_details(self, master_id: UUID) -> bool:
        return any(
            d.product_master_id == master_id for d in self._details.values()
        )

    # --- Product Detail (unused by this property, minimal implementations) ---

    async def create_detail(
        self, detail: ProductDetailEntity
    ) -> ProductDetailEntity:
        self._details[detail.id] = detail
        return detail

    async def update_detail(
        self, detail: ProductDetailEntity
    ) -> ProductDetailEntity:
        self._details[detail.id] = detail
        return detail

    async def get_detail_by_id(
        self, detail_id: UUID
    ) -> ProductDetailEntity | None:
        return self._details.get(detail_id)

    async def delete_detail(self, detail_id: UUID) -> None:
        self._details.pop(detail_id, None)

    async def list_details(
        self,
        skip: int = 0,
        limit: int = 20,
        product_master_id: UUID | None = None,
    ) -> list[ProductDetailEntity]:
        values = [
            d
            for d in self._details.values()
            if product_master_id is None
            or d.product_master_id == product_master_id
        ]
        ordered = sorted(values, key=lambda d: d.child_code)
        return ordered[skip : skip + limit]

    async def count_details(self, product_master_id: UUID | None = None) -> int:
        return len(
            [
                d
                for d in self._details.values()
                if product_master_id is None
                or d.product_master_id == product_master_id
            ]
        )

    async def exists_detail_by_child_code(
        self, child_code: str, exclude_id: UUID | None = None
    ) -> bool:
        return any(
            d.child_code == child_code and d.id != exclude_id
            for d in self._details.values()
        )

    async def get_detail_by_child_code(
        self, child_code: str
    ) -> ProductDetailEntity | None:
        for d in self._details.values():
            if d.child_code == child_code:
                return d
        return None

    async def get_product_name_for_detail(self, detail_id: UUID) -> str | None:
        detail = self._details.get(detail_id)
        if detail is None or detail.product_master_id is None:
            return None
        master = self._masters.get(detail.product_master_id)
        return master.product_name if master is not None else None


def _actor() -> User:
    return User(id=uuid4(), username="tester", is_active=True)


def _service(repo: FakeProductRepository) -> ProductService:
    # The session is unused by the in-memory repository path.
    return ProductService(session=None, product_repo=repo)  # type: ignore[arg-type]


# ─── Valid baseline values (within every rule) for non-target fields ───
_VALID_CODE = "BMC-001"
_VALID_NAME = "Paracetamol 500mg"


def _valid_create(**overrides: object) -> ProductMasterCreateInput:
    base: dict[str, object] = {
        "basic_material_code": _VALID_CODE,
        "product_name": _VALID_NAME,
    }
    base.update(overrides)
    return ProductMasterCreateInput(**base)  # type: ignore[arg-type]


# ─── Strategies ───

_blank = st.one_of(
    st.none(),
    st.just(""),
    st.text(alphabet=" \t\n\r\f\v", min_size=1, max_size=8),
)


@dataclass(frozen=True)
class Case:
    """A single invalid-request scenario."""

    rule: str  # which trigger
    field: str  # offending field name reported by the service
    value: object  # the invalid value (unused for duplicate-code)
    conflict: bool  # True => MasterConflictError; False => MasterValidationError


@st.composite
def _cases(draw: st.DrawFn) -> Case:
    rule = draw(
        st.sampled_from(
            [
                "missing_code",
                "missing_name",
                "duplicate_code",
            ]
        )
    )
    if rule == "missing_code":
        return Case(rule, "basic_material_code", draw(_blank), False)
    if rule == "missing_name":
        return Case(rule, "product_name", draw(_blank), False)
    # duplicate_code
    return Case(rule, "basic_material_code", None, True)


async def _assert_create_rejected(case: Case) -> None:
    repo = FakeProductRepository()
    service = _service(repo)

    if case.rule == "duplicate_code":
        existing = await service.create_master(
            _valid_create(basic_material_code="DUP-001", product_name="Existing"),
            _actor(),
        )
        before = dict(repo._masters)
        with pytest.raises(MasterConflictError):
            await service.create_master(
                _valid_create(basic_material_code="DUP-001", product_name="New"),
                _actor(),
            )
        # Only the seeded record remains; nothing new persisted.
        assert set(repo._masters) == {existing.id}
        assert repo._masters == before
        return

    payload = _valid_create(**{case.field: case.value})
    with pytest.raises(MasterValidationError) as exc:
        await service.create_master(payload, _actor())
    assert exc.value.field == case.field
    # Nothing persisted.
    assert repo._masters == {}


async def _assert_update_rejected(case: Case) -> None:
    repo = FakeProductRepository()
    service = _service(repo)

    if case.rule == "duplicate_code":
        first = await service.create_master(
            _valid_create(basic_material_code="PM-A", product_name="First"),
            _actor(),
        )
        second = await service.create_master(
            _valid_create(basic_material_code="PM-B", product_name="Second"),
            _actor(),
        )
        with pytest.raises(MasterConflictError):
            await service.update_master(
                second.id,
                ProductMasterUpdateInput(basic_material_code="PM-A"),
                _actor(),
            )
        # Both records untouched.
        assert repo._masters[first.id].basic_material_code == "PM-A"
        assert repo._masters[second.id].basic_material_code == "PM-B"
        return

    seeded = await service.create_master(
        _valid_create(basic_material_code="SEED-001", product_name="Seed"),
        _actor(),
    )
    patch = ProductMasterUpdateInput(**{case.field: case.value})  # type: ignore[arg-type]
    with pytest.raises(MasterValidationError) as exc:
        await service.update_master(seeded.id, patch, _actor())
    assert exc.value.field == case.field
    # The stored record is unchanged.
    assert len(repo._masters) == 1
    stored = repo._masters[seeded.id]
    assert stored.basic_material_code == "SEED-001"
    assert stored.product_name == "Seed"


@settings(max_examples=20)
@given(case=_cases())
def test_product_master_validation_rejects_invalid(case: Case) -> None:
    """Invalid create/update requests are rejected and persist/modify nothing.

    Each example violates exactly one Property-26 rule (Req 9.2, 9.3). On both
    the create and the partial-update paths the service must raise the
    appropriate error (conflict for a duplicate Basic Material Code, validation
    error identifying the offending field otherwise) and must leave the
    repository unchanged.
    """
    asyncio.run(_assert_create_rejected(case))
    asyncio.run(_assert_update_rejected(case))


# Required string field: non-empty/whitespace after trimming, within cap.
def _required_text(max_size: int) -> st.SearchStrategy[str]:
    return st.text(min_size=1, max_size=max_size).filter(lambda s: s.strip() != "")


_optional_category = st.none() | st.text(max_size=_MAX_THERAPEUTIC_CATEGORY_LEN)


@settings(max_examples=20)
@given(
    basic_material_code=_required_text(_MAX_BASIC_MATERIAL_CODE_LEN),
    product_name=_required_text(_MAX_PRODUCT_NAME_LEN),
    therapeutic_category=_optional_category,
)
def test_valid_product_master_creation_defaults_status_active(
    basic_material_code: str,
    product_name: str,
    therapeutic_category: str | None,
) -> None:
    """Creating a valid Product Master with no Status supplied defaults to Active.

    The input omits ``status`` so the service must apply the ``Active`` default
    (Req 9.4). All supplied fields must be preserved exactly on the stored
    record (verified by reading it back by id).
    """

    async def scenario() -> ProductMasterEntity:
        repo = FakeProductRepository()
        service = _service(repo)
        created = await service.create_master(
            ProductMasterCreateInput(
                basic_material_code=basic_material_code,
                product_name=product_name,
                therapeutic_category=therapeutic_category,
                # status intentionally omitted to exercise the Active default.
            ),
            _actor(),
        )
        # Read it back by its generated id to confirm what was persisted.
        return await service.get_master(created.id)

    stored = asyncio.run(scenario())

    # Status defaults to Active when omitted (Req 9.4).
    assert stored.status == ProductStatus.Active
    # Supplied fields are preserved exactly.
    assert stored.basic_material_code == basic_material_code
    assert stored.product_name == product_name
    assert stored.therapeutic_category == therapeutic_category
