# Feature: lacm-masters, Property 27: Product Master deletion blocked when children exist.
"""Property-based test for the Product Master delete guard.

Property 27: Product Master deletion blocked when children exist.

**Validates: Requirements 9.5**

*For any* Product Master, a delete request is rejected with a conflict error and
the master and its children are retained when it has one or more Product Detail
children; with no children the deletion succeeds.

The service is exercised end-to-end through a real in-memory implementation of
``IProductRepository`` (not a mock). A fresh service/repository pair is built
per generated example so no state leaks between examples. The async service is
driven with ``asyncio.run`` because each Hypothesis example is independent.
"""

from __future__ import annotations

import asyncio
from uuid import UUID, uuid4

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from src.application.exceptions.application_exceptions import (
    MasterConflictError,
    MasterNotFoundError,
)
from src.application.services.masters.product_service import (
    ProductDetailCreateInput,
    ProductMasterCreateInput,
    ProductService,
)
from src.domain.entities.masters.product import (
    ProductDetailEntity,
    ProductMasterEntity,
)
from src.domain.entities.user import User
from src.domain.repositories.masters.product_repository import IProductRepository


class _InMemoryProductRepository(IProductRepository):
    """Minimal real ``IProductRepository`` backed by dicts."""

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
        ordered = list(self._masters.values())
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

    async def has_details(self, master_id: UUID) -> bool:
        return any(
            d.product_master_id == master_id for d in self._details.values()
        )

    async def get_master_by_basic_material_code(
        self, basic_material_code: str
    ) -> ProductMasterEntity | None:
        for m in self._masters.values():
            if m.basic_material_code == basic_material_code:
                return m
        return None

    # --- Product Detail ---

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
        ordered = [
            d
            for d in self._details.values()
            if product_master_id is None
            or d.product_master_id == product_master_id
        ]
        return ordered[skip : skip + limit]

    async def count_details(
        self, product_master_id: UUID | None = None
    ) -> int:
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

    async def get_product_name_for_detail(self, detail_id: UUID) -> str | None:
        detail = self._details.get(detail_id)
        if detail is None or detail.product_master_id is None:
            return None
        master = self._masters.get(detail.product_master_id)
        return master.product_name if master else None

    async def get_detail_by_child_code(
        self, child_code: str
    ) -> ProductDetailEntity | None:
        for d in self._details.values():
            if d.child_code == child_code:
                return d
        return None


# Child codes: non-empty alphanumeric tokens within the 50-char cap, drawn as a
# de-duplicated list so each Product Detail has a unique Child Code (Req 10.3).
_child_code = st.text(
    alphabet=st.characters(
        min_codepoint=48, max_codepoint=90  # 0-9, A-Z (and a few symbols)
    ).filter(str.isalnum),
    min_size=1,
    max_size=12,
).filter(lambda s: s.strip() != "")

# 0 .. 5 unique child codes: 0 exercises the "no children → delete succeeds"
# branch; >= 1 exercises the "children exist → blocked" branch.
_child_code_lists = st.lists(_child_code, min_size=0, max_size=5, unique=True)


@settings(max_examples=20)
@given(child_codes=_child_code_lists)
def test_product_master_delete_blocked_when_children_exist(
    child_codes: list[str],
) -> None:
    """Deleting a Product Master is blocked iff it has Product Detail children.

    With one or more children the delete raises ``MasterConflictError`` and both
    the master and every child are retained unchanged. With no children the
    delete succeeds and the master is gone (Req 9.5).
    """

    async def scenario() -> None:
        repo = _InMemoryProductRepository()
        service = ProductService(session=None, product_repo=repo)  # type: ignore[arg-type]
        actor = User(id=uuid4(), username="admin", is_active=True)

        master = await service.create_master(
            ProductMasterCreateInput(
                basic_material_code="BM-DELETE-GUARD",
                product_name="Paracetamol",
            ),
            actor,
        )

        detail_ids: list[UUID] = []
        for code in child_codes:
            detail = await service.create_detail(
                ProductDetailCreateInput(
                    child_code=code, product_master_id=master.id
                ),
                actor,
            )
            detail_ids.append(detail.id)

        if child_codes:
            # Children exist → delete is rejected with a conflict error.
            with pytest.raises(MasterConflictError):
                await service.delete_master(master.id, actor)
            # The master is retained.
            assert await service.get_master(master.id) is not None
            # Every child is retained unchanged.
            for detail_id in detail_ids:
                assert await service.get_detail(detail_id) is not None
        else:
            # No children → deletion succeeds and the master is gone.
            await service.delete_master(master.id, actor)
            with pytest.raises(MasterNotFoundError):
                await service.get_master(master.id)

    asyncio.run(scenario())
