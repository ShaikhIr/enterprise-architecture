# Feature: lacm-masters, Property 29: Product Detail master filter.
"""Property-based test for the Product Detail master filter.

Property 29: Product Detail master filter.

**Validates: Requirements 10.9**

For any Product Detail dataset and any ``product_master_id`` filter, every
Product Detail returned by ``ProductService.list_details`` belongs to that
Product Master and no belonging detail is omitted.

The service is exercised end-to-end through a real in-memory implementation of
its repository port (``IProductRepository``), not a mock. The in-memory
repository preserves insertion order and applies the master filter exactly the
way the production SQL repository is contracted to: it restricts to the
requested ``product_master_id`` before slicing/counting. A fresh
service/repository pair is built per generated example so no state leaks
between examples, and the async service is driven with ``asyncio.run`` because
each Hypothesis example is independent.
"""

from __future__ import annotations

import asyncio
from uuid import UUID, uuid4

from hypothesis import given, settings
from hypothesis import strategies as st

from src.application.services.masters.product_service import ProductService
from src.domain.entities.masters.product import (
    ProductDetailEntity,
    ProductMasterEntity,
)
from src.domain.repositories.masters.product_repository import IProductRepository

_NOT_USED = "method not exercised by the master-filter property"

# A small, fixed pool of Product Master ids the details are distributed across.
# Using a fixed pool keeps generated datasets dense enough that most filters
# match several details (and a few match none), exercising both branches.
_MASTER_IDS: tuple[UUID, ...] = tuple(uuid4() for _ in range(4))


class _InMemoryProductRepository(IProductRepository):
    """Ordered in-memory ``IProductRepository`` (detail master-filter only).

    ``list_details``/``count_details`` reproduce the production contract: when a
    ``product_master_id`` is supplied only details whose ``product_master_id``
    equals it are considered, in insertion order, before the page slice is
    applied. When the filter is ``None`` every detail is considered.
    """

    def __init__(self, details: list[ProductDetailEntity]) -> None:
        self._details = list(details)

    def _filtered(
        self, product_master_id: UUID | None
    ) -> list[ProductDetailEntity]:
        if product_master_id is None:
            return list(self._details)
        return [
            d for d in self._details if d.product_master_id == product_master_id
        ]

    async def list_details(
        self,
        skip: int = 0,
        limit: int = 20,
        product_master_id: UUID | None = None,
    ) -> list[ProductDetailEntity]:
        return self._filtered(product_master_id)[skip : skip + limit]

    async def count_details(self, product_master_id: UUID | None = None) -> int:
        return len(self._filtered(product_master_id))

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

    async def exists_detail_by_child_code(
        self, child_code: str, exclude_id: UUID | None = None
    ) -> bool:
        raise NotImplementedError(_NOT_USED)

    async def get_detail_by_child_code(
        self, child_code: str
    ) -> ProductDetailEntity | None:
        raise NotImplementedError(_NOT_USED)

    async def get_product_name_for_detail(self, detail_id: UUID) -> str | None:
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

# Each detail is assigned a master id drawn from the fixed pool. Distinct child
# codes / ids keep the records individually identifiable.
_master_id_strategy = st.sampled_from(_MASTER_IDS)


@st.composite
def _detail_datasets(draw: st.DrawFn) -> list[ProductDetailEntity]:
    """Build an insertion-ordered list of distinct Product Details.

    Master assignment is drawn from the fixed pool so a given filter typically
    matches several details while some masters may match none.
    """
    master_choices = draw(
        st.lists(_master_id_strategy, min_size=0, max_size=25)
    )
    return [
        ProductDetailEntity(
            id=uuid4(),
            child_code=f"CC{i}",
            product_master_id=master_id,
        )
        for i, master_id in enumerate(master_choices)
    ]


@settings(max_examples=20)
@given(
    details=_detail_datasets(),
    # ``None`` exercises the unfiltered listing; a pool id exercises filtering
    # (including ids that match no detail).
    filter_id=st.one_of(st.none(), st.sampled_from(_MASTER_IDS)),
)
def test_list_details_master_filter_is_exact(
    details: list[ProductDetailEntity], filter_id: UUID | None
) -> None:
    """Listing by master returns all and only that master's details.

    With a large enough limit to cover the whole dataset, the returned details
    are exactly the set of details whose ``product_master_id`` equals the filter
    (or every detail when the filter is ``None``): every returned detail belongs
    to the filtered master, and no belonging detail is omitted. The reported
    total matches that same count (Req 10.9).
    """

    async def scenario() -> None:
        service = ProductService(
            session=None,  # type: ignore[arg-type]
            product_repo=_InMemoryProductRepository(details),
        )

        # A limit >= dataset size guarantees the page covers all matches, so
        # "no belonging detail is omitted" is observable.
        items, total = await service.list_details(
            skip=0, limit=max(len(details), 1), product_master_id=filter_id
        )

        returned_ids = {d.id for d in items}
        expected_ids = {
            d.id
            for d in details
            if filter_id is None or d.product_master_id == filter_id
        }

        # Every returned detail belongs to the requested master.
        if filter_id is not None:
            assert all(d.product_master_id == filter_id for d in items), (
                "a returned detail does not belong to the filtered master"
            )

        # All and only the belonging details are returned (none omitted, none
        # spurious), and total reflects that exact count.
        assert returned_ids == expected_ids, (
            "filtered details mismatch: "
            f"returned={returned_ids}, expected={expected_ids}"
        )
        assert total == len(expected_ids), (
            f"reported total {total} != matching count {len(expected_ids)}"
        )

    asyncio.run(scenario())
