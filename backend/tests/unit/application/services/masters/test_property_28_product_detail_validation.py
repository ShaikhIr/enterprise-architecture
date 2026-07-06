# Feature: lacm-masters, Property 28: Product Detail validation and default.
"""Property-based test for Product Detail create/update validation and default.

Property 28: Product Detail validation and default.

**Validates: Requirements 10.2, 10.3, 10.4, 10.5, 10.6, 10.7**

*For any* create- or update-Product-Detail request, the request is rejected
with no persist/modify when:

* the Child Code is missing/empty/whitespace-only (Req 10.2),
* the Product Master reference is missing/empty (Req 10.2),
* the Child Code duplicates an existing detail (Req 10.3),
* the referenced Product Master does not exist (Req 10.4),
* MRP or Rate is below 0 (Req 10.5),
* GST % is outside the 0-100 inclusive range (Req 10.6);

and *for any* valid create request the stored Product Detail defaults Status to
``Active`` while preserving its supplied fields (Req 10.7).

The service is exercised against a real in-memory implementation of
``IProductRepository`` (a fake, not a mock), so the property validates actual
service logic end-to-end through the port. Each Hypothesis example drives the
async service via ``asyncio.run`` so examples remain isolated.
"""

from __future__ import annotations

import asyncio
import string
from dataclasses import dataclass, replace
from decimal import Decimal
from uuid import UUID, uuid4

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from src.application.exceptions.application_exceptions import (
    MasterConflictError,
    MasterValidationError,
)
from src.application.services.masters.product_service import (
    ProductDetailCreateInput,
    ProductDetailUpdateInput,
    ProductMasterCreateInput,
    ProductService,
)
from src.domain.entities.masters.product import (
    ProductDetailEntity,
    ProductMasterEntity,
)
from src.domain.entities.user import User
from src.domain.enums.masters import ProductStatus
from src.domain.repositories.masters.product_repository import IProductRepository


class FakeProductRepository(IProductRepository):
    """In-memory ``IProductRepository`` for testing the service in isolation."""

    def __init__(self) -> None:
        self.masters: dict[UUID, ProductMasterEntity] = {}
        self.details: dict[UUID, ProductDetailEntity] = {}

    # --- Product Master ---

    async def create_master(
        self, master: ProductMasterEntity
    ) -> ProductMasterEntity:
        self.masters[master.id] = master
        return master

    async def update_master(
        self, master: ProductMasterEntity
    ) -> ProductMasterEntity:
        self.masters[master.id] = master
        return master

    async def get_master_by_id(self, master_id: UUID) -> ProductMasterEntity | None:
        return self.masters.get(master_id)

    async def delete_master(self, master_id: UUID) -> None:
        self.masters.pop(master_id, None)

    async def list_masters(
        self, skip: int = 0, limit: int = 20
    ) -> list[ProductMasterEntity]:
        ordered = list(self.masters.values())
        return ordered[skip : skip + limit]

    async def count_masters(self) -> int:
        return len(self.masters)

    async def exists_master_by_basic_material_code(
        self, basic_material_code: str, exclude_id: UUID | None = None
    ) -> bool:
        return any(
            m.basic_material_code == basic_material_code and m.id != exclude_id
            for m in self.masters.values()
        )

    async def has_details(self, master_id: UUID) -> bool:
        return any(d.product_master_id == master_id for d in self.details.values())

    async def get_master_by_basic_material_code(
        self, basic_material_code: str
    ) -> ProductMasterEntity | None:
        for m in self.masters.values():
            if m.basic_material_code == basic_material_code:
                return m
        return None

    # --- Product Detail ---

    async def create_detail(
        self, detail: ProductDetailEntity
    ) -> ProductDetailEntity:
        self.details[detail.id] = detail
        return detail

    async def update_detail(
        self, detail: ProductDetailEntity
    ) -> ProductDetailEntity:
        self.details[detail.id] = detail
        return detail

    async def get_detail_by_id(self, detail_id: UUID) -> ProductDetailEntity | None:
        return self.details.get(detail_id)

    async def delete_detail(self, detail_id: UUID) -> None:
        self.details.pop(detail_id, None)

    async def list_details(
        self,
        skip: int = 0,
        limit: int = 20,
        product_master_id: UUID | None = None,
    ) -> list[ProductDetailEntity]:
        ordered = [
            d
            for d in self.details.values()
            if product_master_id is None or d.product_master_id == product_master_id
        ]
        return ordered[skip : skip + limit]

    async def count_details(self, product_master_id: UUID | None = None) -> int:
        return len(
            [
                d
                for d in self.details.values()
                if product_master_id is None
                or d.product_master_id == product_master_id
            ]
        )

    async def exists_detail_by_child_code(
        self, child_code: str, exclude_id: UUID | None = None
    ) -> bool:
        return any(
            d.child_code == child_code and d.id != exclude_id
            for d in self.details.values()
        )

    async def get_product_name_for_detail(self, detail_id: UUID) -> str | None:
        detail = self.details.get(detail_id)
        if detail is None or detail.product_master_id is None:
            return None
        master = self.masters.get(detail.product_master_id)
        return master.product_name if master else None

    async def get_detail_by_child_code(
        self, child_code: str
    ) -> ProductDetailEntity | None:
        for d in self.details.values():
            if d.child_code == child_code:
                return d
        return None


def _actor() -> User:
    return User(id=uuid4(), username="tester", is_active=True)


def _service(repo: FakeProductRepository) -> ProductService:
    # The session is unused by the in-memory repository path.
    return ProductService(session=None, product_repo=repo)  # type: ignore[arg-type]


async def _seed_master(
    service: ProductService, code: str = "BM-1"
) -> ProductMasterEntity:
    return await service.create_master(
        ProductMasterCreateInput(basic_material_code=code, product_name="Paracetamol"),
        _actor(),
    )


# ─── Strategies ───

# Missing/empty/whitespace-only values (Req 10.2).
_blank = st.one_of(
    st.none(),
    st.just(""),
    st.text(alphabet=" \t\n\r\f\v", min_size=1, max_size=8),
)

# Negative monetary values (Req 10.5).
_negative_amount = st.decimals(
    min_value=Decimal("-100000"),
    max_value=Decimal("-0.01"),
    allow_nan=False,
    allow_infinity=False,
    places=2,
)

# GST percentages outside 0-100 inclusive (Req 10.6).
_out_of_range_gst = st.one_of(
    st.decimals(
        min_value=Decimal("-100000"),
        max_value=Decimal("-0.01"),
        allow_nan=False,
        allow_infinity=False,
        places=2,
    ),
    st.decimals(
        min_value=Decimal("100.01"),
        max_value=Decimal("100000"),
        allow_nan=False,
        allow_infinity=False,
        places=2,
    ),
)

_token = st.text(
    alphabet=string.ascii_letters + string.digits + "-", min_size=1, max_size=20
)


@dataclass(frozen=True)
class InvalidCase:
    """A single invalid-request scenario."""

    rule: str  # which trigger
    field: str  # offending field name reported by the service
    value: object  # the invalid value (unused for duplicate/nonexistent)
    conflict: bool  # True => MasterConflictError; otherwise MasterValidationError


@st.composite
def _invalid_cases(draw: st.DrawFn) -> InvalidCase:
    rule = draw(
        st.sampled_from(
            [
                "missing_child_code",
                "missing_master_ref",
                "nonexistent_master",
                "duplicate_child_code",
                "negative_mrp",
                "negative_rate",
                "out_of_range_gst",
            ]
        )
    )
    if rule == "missing_child_code":
        return InvalidCase(rule, "child_code", draw(_blank), False)
    if rule == "missing_master_ref":
        return InvalidCase(rule, "product_master_id", None, False)
    if rule == "nonexistent_master":
        return InvalidCase(rule, "product_master_id", uuid4(), False)
    if rule == "negative_mrp":
        return InvalidCase(rule, "mrp", draw(_negative_amount), False)
    if rule == "negative_rate":
        return InvalidCase(rule, "rate", draw(_negative_amount), False)
    if rule == "out_of_range_gst":
        return InvalidCase(rule, "gst_percent", draw(_out_of_range_gst), False)
    # duplicate_child_code
    return InvalidCase(rule, "child_code", None, True)


# ─── Invalid create-path assertions ───


async def _assert_create_rejected(case: InvalidCase) -> None:
    repo = FakeProductRepository()
    service = _service(repo)
    master = await _seed_master(service)

    if case.rule == "duplicate_child_code":
        existing = await service.create_detail(
            ProductDetailCreateInput(
                child_code="DUP-1", product_master_id=master.id
            ),
            _actor(),
        )
        before = dict(repo.details)
        with pytest.raises(MasterConflictError):
            await service.create_detail(
                ProductDetailCreateInput(
                    child_code="DUP-1", product_master_id=master.id
                ),
                _actor(),
            )
        # Only the seeded detail remains; nothing new persisted.
        assert set(repo.details) == {existing.id}
        assert repo.details == before
        return

    # Build an otherwise-valid payload with exactly one offending field.
    overrides: dict[str, object] = {
        "child_code": "C-OK",
        "product_master_id": master.id,
    }
    overrides[case.field] = case.value
    payload = ProductDetailCreateInput(**overrides)  # type: ignore[arg-type]

    with pytest.raises(MasterValidationError) as exc:
        await service.create_detail(payload, _actor())
    assert exc.value.field == case.field
    # Nothing persisted.
    assert repo.details == {}


# ─── Invalid update-path assertions ───


async def _assert_update_rejected(case: InvalidCase) -> None:
    repo = FakeProductRepository()
    service = _service(repo)
    master = await _seed_master(service)

    if case.rule == "missing_master_ref":
        # UNSET vs explicit-None: the update path validates an explicitly
        # supplied null reference, so target that.
        seeded = await service.create_detail(
            ProductDetailCreateInput(
                child_code="UPD-1", product_master_id=master.id
            ),
            _actor(),
        )
        snapshot = replace(seeded)
        with pytest.raises(MasterValidationError) as exc:
            await service.update_detail(
                seeded.id,
                ProductDetailUpdateInput(product_master_id=None),  # type: ignore[arg-type]
                _actor(),
            )
        assert exc.value.field == "product_master_id"
        assert repo.details[seeded.id] == snapshot
        return

    if case.rule == "duplicate_child_code":
        first = await service.create_detail(
            ProductDetailCreateInput(child_code="UPD-A", product_master_id=master.id),
            _actor(),
        )
        second = await service.create_detail(
            ProductDetailCreateInput(child_code="UPD-B", product_master_id=master.id),
            _actor(),
        )
        first_snap = replace(first)
        second_snap = replace(second)
        with pytest.raises(MasterConflictError):
            await service.update_detail(
                second.id,
                ProductDetailUpdateInput(child_code="UPD-A"),
                _actor(),
            )
        # Both records untouched.
        assert repo.details[first.id].child_code == first_snap.child_code
        assert repo.details[second.id].child_code == second_snap.child_code
        return

    seeded = await service.create_detail(
        ProductDetailCreateInput(child_code="UPD-SEED", product_master_id=master.id),
        _actor(),
    )
    snapshot = replace(seeded)

    patch = ProductDetailUpdateInput(**{case.field: case.value})  # type: ignore[arg-type]
    with pytest.raises(MasterValidationError) as exc:
        await service.update_detail(seeded.id, patch, _actor())
    assert exc.value.field == case.field
    # The stored record is unchanged.
    assert len(repo.details) == 1
    assert repo.details[seeded.id] == snapshot


@settings(max_examples=20)
@given(case=_invalid_cases())
def test_product_detail_invalid_requests_rejected(case: InvalidCase) -> None:
    """Invalid create/update requests are rejected and persist/modify nothing.

    Each example violates exactly one Property-28 rule (Req 10.2, 10.3, 10.4,
    10.5, 10.6). On both the create and the partial-update paths the service
    must raise the appropriate error (conflict for a duplicate Child Code,
    validation error identifying the offending field otherwise) and leave the
    repository unchanged.
    """
    asyncio.run(_assert_create_rejected(case))
    asyncio.run(_assert_update_rejected(case))


# ─── Valid-create default + preservation assertions (Req 10.7) ───


@dataclass(frozen=True)
class ValidCase:
    """A valid create payload with all optional fields supplied."""

    child_code: str
    variant_description: str | None
    hsn_code: str | None
    pack_size: str | None
    unit_of_measure: str | None
    mrp: Decimal | None
    rate: Decimal | None
    gst_percent: Decimal | None


_optional_text = st.one_of(st.none(), _token)
_nonneg_amount = st.one_of(
    st.none(),
    st.decimals(
        min_value=Decimal("0"),
        max_value=Decimal("100000"),
        allow_nan=False,
        allow_infinity=False,
        places=2,
    ),
)
_valid_gst = st.one_of(
    st.none(),
    st.decimals(
        min_value=Decimal("0"),
        max_value=Decimal("100"),
        allow_nan=False,
        allow_infinity=False,
        places=2,
    ),
)


@st.composite
def _valid_cases(draw: st.DrawFn) -> ValidCase:
    return ValidCase(
        child_code=draw(
            st.text(
                alphabet=string.ascii_letters + string.digits + "-",
                min_size=1,
                max_size=50,
            ).filter(lambda s: s.strip() != "")
        ),
        variant_description=draw(_optional_text),
        hsn_code=draw(st.one_of(st.none(), st.text(alphabet=string.digits, min_size=1, max_size=20))),
        pack_size=draw(st.one_of(st.none(), st.text(alphabet=string.ascii_letters + string.digits, min_size=1, max_size=50))),
        unit_of_measure=draw(st.one_of(st.none(), st.text(alphabet=string.ascii_letters, min_size=1, max_size=20))),
        mrp=draw(_nonneg_amount),
        rate=draw(_nonneg_amount),
        gst_percent=draw(_valid_gst),
    )


async def _assert_valid_create_defaults_active(case: ValidCase) -> None:
    repo = FakeProductRepository()
    service = _service(repo)
    master = await _seed_master(service)

    detail = await service.create_detail(
        ProductDetailCreateInput(
            child_code=case.child_code,
            product_master_id=master.id,
            variant_description=case.variant_description,
            hsn_code=case.hsn_code,
            pack_size=case.pack_size,
            unit_of_measure=case.unit_of_measure,
            mrp=case.mrp,
            rate=case.rate,
            gst_percent=case.gst_percent,
            status=None,
        ),
        _actor(),
    )

    # Default Status is Active (Req 10.7).
    assert detail.status == ProductStatus.Active
    # Supplied fields are preserved.
    assert detail.child_code == case.child_code
    assert detail.product_master_id == master.id
    assert detail.variant_description == case.variant_description
    assert detail.hsn_code == case.hsn_code
    assert detail.pack_size == case.pack_size
    assert detail.unit_of_measure == case.unit_of_measure
    assert detail.mrp == case.mrp
    assert detail.rate == case.rate
    assert detail.gst_percent == case.gst_percent
    # Persisted exactly once.
    assert repo.details[detail.id] is detail


@settings(max_examples=20)
@given(case=_valid_cases())
def test_product_detail_valid_create_defaults_active(case: ValidCase) -> None:
    """A valid create defaults Status to ``Active`` and preserves fields.

    Validates Req 10.7: when the caller omits Status, a successful create
    stores ``Active`` while every supplied field is persisted unchanged.
    """
    asyncio.run(_assert_valid_create_defaults_active(case))
