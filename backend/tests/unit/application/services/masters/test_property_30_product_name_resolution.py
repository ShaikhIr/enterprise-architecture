# Feature: lacm-masters, Property 30: Product name resolves through the hierarchy.
"""Property-based test for product-name resolution through the hierarchy.

Property 30: Product name resolves through the hierarchy.

**Validates: Requirements 10.10**

*For any* Product Detail, the product name resolved for downstream display by
``ProductService.get_product_name`` equals the Product Name of the Detail's
parent Product Master.

The service is exercised end-to-end against a real in-memory implementation of
its repository port (``IProductRepository``), not a mock. The in-memory
repository reproduces the production resolution contract: it looks up the
Detail, follows its ``product_master_id`` to the parent Product Master and
returns that master's ``product_name`` (and ``None`` when the Detail or its
parent is unknown). A fresh service/repository pair is built per generated
example so no state leaks between examples, and the async service is driven
with ``asyncio.run`` because each Hypothesis example is independent.
"""

from __future__ import annotations

import asyncio
import string
from uuid import UUID, uuid4

from hypothesis import given, settings
from hypothesis import strategies as st

from src.application.services.masters.product_service import ProductService
from src.domain.entities.masters.product import (
    ProductDetailEntity,
    ProductMasterEntity,
)
from src.domain.enums.masters import ProductStatus
from src.domain.repositories.masters.product_repository import IProductRepository

_NOT_USED = "method not exercised by the product-name resolution property"


class _InMemoryProductRepository(IProductRepository):
    """In-memory ``IProductRepository`` (product-name resolution only).

    ``get_product_name_for_detail`` reproduces the production contract: it
    follows the Detail's ``product_master_id`` to its parent Product Master and
    returns that master's ``product_name``, or ``None`` when the Detail is
    unknown / has no parent / its parent is missing.
    """

    def __init__(
        self,
        masters: dict[UUID, ProductMasterEntity],
        details: dict[UUID, ProductDetailEntity],
    ) -> None:
        self._masters = dict(masters)
        self._details = dict(details)

    async def get_product_name_for_detail(self, detail_id: UUID) -> str | None:
        detail = self._details.get(detail_id)
        if detail is None or detail.product_master_id is None:
            return None
        master = self._masters.get(detail.product_master_id)
        return master.product_name if master else None

    # --- Product Detail (unused) ---
    async def create_detail(
        self, detail: ProductDetailEntity
    ) -> ProductDetailEntity:
        raise NotImplementedError(_NOT_USED)

    async def update_detail(
        self, detail: ProductDetailEntity
    ) -> ProductDetailEntity:
        raise NotImplementedError(_NOT_USED)

    async def get_detail_by_id(
        self, detail_id: UUID
    ) -> ProductDetailEntity | None:
        raise NotImplementedError(_NOT_USED)

    async def delete_detail(self, detail_id: UUID) -> None:
        raise NotImplementedError(_NOT_USED)

    async def list_details(
        self,
        skip: int = 0,
        limit: int = 20,
        product_master_id: UUID | None = None,
    ) -> list[ProductDetailEntity]:
        raise NotImplementedError(_NOT_USED)

    async def count_details(self, product_master_id: UUID | None = None) -> int:
        raise NotImplementedError(_NOT_USED)

    async def exists_detail_by_child_code(
        self, child_code: str, exclude_id: UUID | None = None
    ) -> bool:
        raise NotImplementedError(_NOT_USED)

    async def get_detail_by_child_code(
        self, child_code: str
    ) -> ProductDetailEntity | None:
        raise NotImplementedError(_NOT_USED)

    # --- Product Master (unused) ---
    async def create_master(
        self, master: ProductMasterEntity
    ) -> ProductMasterEntity:
        raise NotImplementedError(_NOT_USED)

    async def update_master(
        self, master: ProductMasterEntity
    ) -> ProductMasterEntity:
        raise NotImplementedError(_NOT_USED)

    async def get_master_by_id(
        self, master_id: UUID
    ) -> ProductMasterEntity | None:
        raise NotImplementedError(_NOT_USED)

    async def delete_master(self, master_id: UUID) -> None:
        raise NotImplementedError(_NOT_USED)

    async def list_masters(
        self, skip: int = 0, limit: int = 20
    ) -> list[ProductMasterEntity]:
        raise NotImplementedError(_NOT_USED)

    async def count_masters(self) -> int:
        raise NotImplementedError(_NOT_USED)

    async def exists_master_by_basic_material_code(
        self, basic_material_code: str, exclude_id: UUID | None = None
    ) -> bool:
        raise NotImplementedError(_NOT_USED)

    async def get_master_by_basic_material_code(
        self, basic_material_code: str
    ) -> ProductMasterEntity | None:
        raise NotImplementedError(_NOT_USED)

    async def has_details(self, master_id: UUID) -> bool:
        raise NotImplementedError(_NOT_USED)


# ─── Generators ───

_product_name = st.text(
    alphabet=string.ascii_letters + string.digits + " -",
    min_size=1,
    max_size=40,
).filter(lambda s: s.strip() != "")


@st.composite
def _hierarchies(
    draw: st.DrawFn,
) -> tuple[
    dict[UUID, ProductMasterEntity],
    dict[UUID, ProductDetailEntity],
]:
    """Build a Product Master/Detail hierarchy.

    Each generated example produces one or more Product Masters (each with a
    distinct, non-blank Product Name) and a set of Product Details, every one of
    which references one of the generated masters. Distinct names let the test
    detect resolution that returns the wrong master's name.
    """
    names = draw(st.lists(_product_name, min_size=1, max_size=6, unique=True))
    masters: dict[UUID, ProductMasterEntity] = {}
    for i, name in enumerate(names):
        master_id = uuid4()
        masters[master_id] = ProductMasterEntity(
            id=master_id,
            basic_material_code=f"BM{i}",
            product_name=name,
            status=ProductStatus.Active,
        )

    master_ids = list(masters.keys())
    parent_choices = draw(
        st.lists(st.sampled_from(master_ids), min_size=1, max_size=25)
    )
    details: dict[UUID, ProductDetailEntity] = {}
    for i, parent_id in enumerate(parent_choices):
        detail_id = uuid4()
        details[detail_id] = ProductDetailEntity(
            id=detail_id,
            child_code=f"CC{i}",
            product_master_id=parent_id,
        )
    return masters, details


@settings(max_examples=20)
@given(hierarchy=_hierarchies())
def test_product_name_resolves_to_parent_master(
    hierarchy: tuple[
        dict[UUID, ProductMasterEntity], dict[UUID, ProductDetailEntity]
    ],
) -> None:
    """Resolved name equals the parent Product Master's Product Name.

    For every Product Detail in the dataset,
    ``ProductService.get_product_name`` traverses the Detail to its parent
    Product Master and returns that master's ``product_name`` (Req 10.10).
    """
    masters, details = hierarchy

    async def scenario() -> None:
        service = ProductService(
            session=None,  # type: ignore[arg-type]
            product_repo=_InMemoryProductRepository(masters, details),
        )
        for detail in details.values():
            assert detail.product_master_id is not None
            expected = masters[detail.product_master_id].product_name
            resolved = await service.get_product_name(detail.id)
            assert resolved == expected, (
                f"resolved name {resolved!r} != parent master name "
                f"{expected!r} for detail {detail.id}"
            )

    asyncio.run(scenario())
