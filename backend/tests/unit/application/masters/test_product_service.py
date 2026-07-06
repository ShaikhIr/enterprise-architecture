"""
Unit tests for :class:`ProductService` (Product Master + Product Detail CRUD).

These tests exercise the service's business rules in isolation using an
in-memory fake repository that implements :class:`IProductRepository`, so no
database is required. They cover the requirements assigned to task 7.2
(Requirements 9.2–9.7 and 10.2–10.10).
"""

from __future__ import annotations

from decimal import Decimal
from uuid import UUID, uuid4

import pytest

from src.application.exceptions.application_exceptions import (
    MasterConflictError,
    MasterNotFoundError,
    MasterValidationError,
)
from src.application.services.masters.product_service import (
    ProductDetailCreateInput,
    ProductDetailUpdateInput,
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


class FakeProductRepository(IProductRepository):
    """In-memory implementation of the product repository port."""

    def __init__(self) -> None:
        self.masters: dict[UUID, ProductMasterEntity] = {}
        self.details: dict[UUID, ProductDetailEntity] = {}

    # --- Product Master ---

    async def create_master(self, master: ProductMasterEntity) -> ProductMasterEntity:
        self.masters[master.id] = master
        return master

    async def update_master(self, master: ProductMasterEntity) -> ProductMasterEntity:
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

    async def create_detail(self, detail: ProductDetailEntity) -> ProductDetailEntity:
        self.details[detail.id] = detail
        return detail

    async def update_detail(self, detail: ProductDetailEntity) -> ProductDetailEntity:
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


@pytest.fixture
def actor() -> User:
    return User(id=uuid4(), username="tester", is_active=True)


@pytest.fixture
def repo() -> FakeProductRepository:
    return FakeProductRepository()


@pytest.fixture
def service(repo: FakeProductRepository) -> ProductService:
    return ProductService(session=None, product_repo=repo)  # type: ignore[arg-type]


async def _make_master(service: ProductService, actor: User, code: str = "BM-1"):
    return await service.create_master(
        ProductMasterCreateInput(basic_material_code=code, product_name="Paracetamol"),
        actor,
    )


# ─────────────────────────── Product Master ───────────────────────────


class TestProductMaster:
    async def test_create_defaults_status_active(self, service, actor):
        master = await _make_master(service, actor)
        assert master.status == ProductStatus.Active
        assert master.created_by == "tester"

    @pytest.mark.parametrize("code", ["", "   "])
    async def test_create_rejects_empty_basic_material_code(self, service, actor, code):
        with pytest.raises(MasterValidationError) as exc:
            await service.create_master(
                ProductMasterCreateInput(basic_material_code=code, product_name="X"),
                actor,
            )
        assert exc.value.field == "basic_material_code"

    async def test_create_rejects_empty_product_name(self, service, actor):
        with pytest.raises(MasterValidationError) as exc:
            await service.create_master(
                ProductMasterCreateInput(basic_material_code="BM-9", product_name=" "),
                actor,
            )
        assert exc.value.field == "product_name"

    async def test_create_rejects_duplicate_basic_material_code(self, service, actor):
        await _make_master(service, actor, "BM-DUP")
        with pytest.raises(MasterConflictError):
            await _make_master(service, actor, "BM-DUP")

    async def test_get_unknown_master_raises_not_found(self, service):
        with pytest.raises(MasterNotFoundError):
            await service.get_master(uuid4())

    async def test_update_is_partial(self, service, actor):
        master = await _make_master(service, actor)
        updated = await service.update_master(
            master.id,
            ProductMasterUpdateInput(product_name="Ibuprofen"),
            actor,
        )
        assert updated.product_name == "Ibuprofen"
        assert updated.basic_material_code == master.basic_material_code

    async def test_update_unknown_master_raises_not_found(self, service, actor):
        with pytest.raises(MasterNotFoundError):
            await service.update_master(
                uuid4(), ProductMasterUpdateInput(product_name="X"), actor
            )

    async def test_list_returns_items_and_total(self, service, actor):
        await _make_master(service, actor, "BM-A")
        await _make_master(service, actor, "BM-B")
        items, total = await service.list_masters(skip=0, limit=1)
        assert total == 2
        assert len(items) == 1

    async def test_delete_blocked_when_children_exist(self, service, actor):
        master = await _make_master(service, actor)
        await service.create_detail(
            ProductDetailCreateInput(
                child_code="C-1", product_master_id=master.id
            ),
            actor,
        )
        with pytest.raises(MasterConflictError):
            await service.delete_master(master.id, actor)
        # master retained
        assert await service.get_master(master.id) is not None

    async def test_delete_succeeds_without_children(self, service, actor):
        master = await _make_master(service, actor)
        await service.delete_master(master.id, actor)
        with pytest.raises(MasterNotFoundError):
            await service.get_master(master.id)

    async def test_delete_unknown_master_raises_not_found(self, service, actor):
        with pytest.raises(MasterNotFoundError):
            await service.delete_master(uuid4(), actor)


# ─────────────────────────── Product Detail ───────────────────────────


class TestProductDetail:
    async def test_create_defaults_status_active(self, service, actor):
        master = await _make_master(service, actor)
        detail = await service.create_detail(
            ProductDetailCreateInput(child_code="C-10", product_master_id=master.id),
            actor,
        )
        assert detail.status == ProductStatus.Active

    @pytest.mark.parametrize("code", ["", "  "])
    async def test_create_rejects_empty_child_code(self, service, actor, code):
        master = await _make_master(service, actor)
        with pytest.raises(MasterValidationError) as exc:
            await service.create_detail(
                ProductDetailCreateInput(
                    child_code=code, product_master_id=master.id
                ),
                actor,
            )
        assert exc.value.field == "child_code"

    async def test_create_rejects_missing_master_reference(self, service, actor):
        with pytest.raises(MasterValidationError) as exc:
            await service.create_detail(
                ProductDetailCreateInput(child_code="C-11", product_master_id=None),
                actor,
            )
        assert exc.value.field == "product_master_id"

    async def test_create_rejects_nonexistent_master(self, service, actor):
        with pytest.raises(MasterValidationError) as exc:
            await service.create_detail(
                ProductDetailCreateInput(
                    child_code="C-12", product_master_id=uuid4()
                ),
                actor,
            )
        assert exc.value.field == "product_master_id"

    async def test_create_rejects_duplicate_child_code(self, service, actor):
        master = await _make_master(service, actor)
        await service.create_detail(
            ProductDetailCreateInput(child_code="C-DUP", product_master_id=master.id),
            actor,
        )
        with pytest.raises(MasterConflictError):
            await service.create_detail(
                ProductDetailCreateInput(
                    child_code="C-DUP", product_master_id=master.id
                ),
                actor,
            )

    @pytest.mark.parametrize("mrp", [Decimal("-0.01"), Decimal("-100")])
    async def test_create_rejects_negative_mrp(self, service, actor, mrp):
        master = await _make_master(service, actor)
        with pytest.raises(MasterValidationError) as exc:
            await service.create_detail(
                ProductDetailCreateInput(
                    child_code="C-13", product_master_id=master.id, mrp=mrp
                ),
                actor,
            )
        assert exc.value.field == "mrp"

    async def test_create_rejects_negative_rate(self, service, actor):
        master = await _make_master(service, actor)
        with pytest.raises(MasterValidationError) as exc:
            await service.create_detail(
                ProductDetailCreateInput(
                    child_code="C-14",
                    product_master_id=master.id,
                    rate=Decimal("-1"),
                ),
                actor,
            )
        assert exc.value.field == "rate"

    @pytest.mark.parametrize("gst", [Decimal("-0.01"), Decimal("100.01"), Decimal("150")])
    async def test_create_rejects_out_of_range_gst(self, service, actor, gst):
        master = await _make_master(service, actor)
        with pytest.raises(MasterValidationError) as exc:
            await service.create_detail(
                ProductDetailCreateInput(
                    child_code="C-15",
                    product_master_id=master.id,
                    gst_percent=gst,
                ),
                actor,
            )
        assert exc.value.field == "gst_percent"

    @pytest.mark.parametrize("gst", [Decimal("0"), Decimal("18"), Decimal("100")])
    async def test_create_accepts_boundary_gst(self, service, actor, gst):
        master = await _make_master(service, actor)
        detail = await service.create_detail(
            ProductDetailCreateInput(
                child_code=f"C-gst-{gst}",
                product_master_id=master.id,
                gst_percent=gst,
            ),
            actor,
        )
        assert detail.gst_percent == gst

    async def test_get_unknown_detail_raises_not_found(self, service):
        with pytest.raises(MasterNotFoundError):
            await service.get_detail(uuid4())

    async def test_update_detail_is_partial(self, service, actor):
        master = await _make_master(service, actor)
        detail = await service.create_detail(
            ProductDetailCreateInput(
                child_code="C-16",
                product_master_id=master.id,
                rate=Decimal("5"),
            ),
            actor,
        )
        updated = await service.update_detail(
            detail.id,
            ProductDetailUpdateInput(rate=Decimal("9")),
            actor,
        )
        assert updated.rate == Decimal("9")
        assert updated.child_code == "C-16"

    async def test_list_details_filters_by_master(self, service, actor):
        master_a = await _make_master(service, actor, "BM-A")
        master_b = await _make_master(service, actor, "BM-B")
        await service.create_detail(
            ProductDetailCreateInput(child_code="A-1", product_master_id=master_a.id),
            actor,
        )
        await service.create_detail(
            ProductDetailCreateInput(child_code="B-1", product_master_id=master_b.id),
            actor,
        )
        items, total = await service.list_details(product_master_id=master_a.id)
        assert total == 1
        assert all(d.product_master_id == master_a.id for d in items)

    async def test_get_product_name_resolves_through_hierarchy(self, service, actor):
        master = await service.create_master(
            ProductMasterCreateInput(
                basic_material_code="BM-X", product_name="Amoxicillin"
            ),
            actor,
        )
        detail = await service.create_detail(
            ProductDetailCreateInput(child_code="C-20", product_master_id=master.id),
            actor,
        )
        assert await service.get_product_name(detail.id) == "Amoxicillin"

    async def test_get_product_name_unknown_detail_raises_not_found(self, service):
        with pytest.raises(MasterNotFoundError):
            await service.get_product_name(uuid4())

    async def test_delete_detail_unknown_raises_not_found(self, service, actor):
        with pytest.raises(MasterNotFoundError):
            await service.delete_detail(uuid4(), actor)
