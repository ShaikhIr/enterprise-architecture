# Feature: lacm-masters, Property 6: Pagination returns the requested slice with full total.
"""Property-based test for paginated master listing (cross-master).

Property 6: Pagination returns the requested slice with full total.

**Validates: Requirements 1.9, 6.11, 8.7, 9.7**

For any dataset and any valid ``skip`` (>= 0) and ``limit`` (1-100), a paginated
master list returns *exactly* the records of the dataset slice
``[skip, skip + limit)`` under the list's deterministic ordering, and reports
``total`` equal to the count of all matching records.

This property is cross-master: it is written once (here, alongside the Entity
suite) and exercises **every** paginated master list, per the design's
traceability table:

* ``EntityService.list_entities``       -> Requirement 1.9
* ``VendorService.list_vendors``        -> Requirement 6.11
* ``CustomerService.list_customers``    -> Requirement 8.7
* ``ProductService.list_masters``       -> Requirement 9.7

Each service is exercised end-to-end through a real in-memory implementation of
its repository port (not a mock). Every repository preserves insertion order, so
the "deterministic ordering" the service relies on is well defined and the
expected page is simply the seeded list sliced with the same ``skip``/``limit``.
A fresh service/repository set is built per generated example so no state leaks
between examples. The async services are driven with ``asyncio.run`` because each
Hypothesis example is independent.
"""

from __future__ import annotations

import asyncio
from uuid import UUID

from hypothesis import given, settings
from hypothesis import strategies as st

from src.application.services.masters.customer_service import CustomerService
from src.application.services.masters.entity_service import EntityService
from src.application.services.masters.product_service import ProductService
from src.application.services.masters.vendor_service import VendorService
from src.domain.entities.masters.customer import CustomerEntity
from src.domain.entities.masters.entity import EntityEntity
from src.domain.entities.masters.product import (
    ProductDetailEntity,
    ProductMasterEntity,
)
from src.domain.entities.masters.vendor import VendorEntity
from src.domain.repositories.masters.customer_repository import ICustomerRepository
from src.domain.repositories.masters.entity_repository import IEntityRepository
from src.domain.repositories.masters.product_repository import IProductRepository
from src.domain.repositories.masters.vendor_repository import IVendorRepository

_NOT_USED = "method not exercised by the pagination property"


# ─── In-memory repositories (insertion-ordered, real port implementations) ───


class _InMemoryEntityRepository(IEntityRepository):
    """Ordered in-memory ``IEntityRepository`` returning ``(slice, total)``."""

    def __init__(self, records: list[EntityEntity]) -> None:
        self._records = list(records)

    async def list(
        self,
        skip: int = 0,
        limit: int = 20,
        search: str | None = None,
        is_active: bool | None = None,
    ) -> tuple[list[EntityEntity], int]:
        # No search/active filter is supplied by the property, so every record
        # matches; the slice and the full total follow the contract directly.
        return self._records[skip : skip + limit], len(self._records)

    async def get_by_id(self, entity_id: UUID) -> EntityEntity | None:
        raise NotImplementedError(_NOT_USED)

    async def create(self, entity: EntityEntity) -> EntityEntity:
        raise NotImplementedError(_NOT_USED)

    async def update(self, entity: EntityEntity) -> EntityEntity:
        raise NotImplementedError(_NOT_USED)

    async def delete(self, entity_id: UUID) -> None:
        raise NotImplementedError(_NOT_USED)

    async def list_active(self) -> list[EntityEntity]:
        raise NotImplementedError(_NOT_USED)

    async def get_by_name(self, entity_name: str) -> EntityEntity | None:
        raise NotImplementedError(_NOT_USED)

    async def get_by_company_code(self, company_code: str) -> EntityEntity | None:
        raise NotImplementedError(_NOT_USED)

    async def exists_by_name(
        self, entity_name: str, exclude_id: UUID | None = None
    ) -> bool:
        raise NotImplementedError(_NOT_USED)

    async def exists_by_company_code(
        self, company_code: str, exclude_id: UUID | None = None
    ) -> bool:
        raise NotImplementedError(_NOT_USED)


class _InMemoryVendorRepository(IVendorRepository):
    """Ordered in-memory ``IVendorRepository`` with split list/count."""

    def __init__(self, records: list[VendorEntity]) -> None:
        self._records = list(records)

    async def list_all(self, skip: int = 0, limit: int = 20) -> list[VendorEntity]:
        return self._records[skip : skip + limit]

    async def count_all(self) -> int:
        return len(self._records)

    async def get_by_id(self, vendor_id: UUID) -> VendorEntity | None:
        raise NotImplementedError(_NOT_USED)

    async def get_by_code(self, vendor_code: str) -> VendorEntity | None:
        raise NotImplementedError(_NOT_USED)

    async def get_by_email(self, vendor_email: str) -> VendorEntity | None:
        raise NotImplementedError(_NOT_USED)

    async def create(self, vendor: VendorEntity) -> VendorEntity:
        raise NotImplementedError(_NOT_USED)

    async def update(self, vendor: VendorEntity) -> VendorEntity:
        raise NotImplementedError(_NOT_USED)

    async def delete(self, vendor_id: UUID) -> None:
        raise NotImplementedError(_NOT_USED)

    async def exists_by_code(self, vendor_code: str) -> bool:
        raise NotImplementedError(_NOT_USED)

    async def exists_by_email(self, vendor_email: str) -> bool:
        raise NotImplementedError(_NOT_USED)


class _InMemoryCustomerRepository(ICustomerRepository):
    """Ordered in-memory ``ICustomerRepository`` with split list/count."""

    def __init__(self, records: list[CustomerEntity]) -> None:
        self._records = list(records)

    async def list_customers(
        self, skip: int = 0, limit: int = 20
    ) -> list[CustomerEntity]:
        return self._records[skip : skip + limit]

    async def count(self) -> int:
        return len(self._records)

    async def get_by_id(self, customer_id: UUID) -> CustomerEntity | None:
        raise NotImplementedError(_NOT_USED)

    async def get_by_customer_code(
        self, customer_code: str
    ) -> CustomerEntity | None:
        raise NotImplementedError(_NOT_USED)

    async def create(self, customer: CustomerEntity) -> CustomerEntity:
        raise NotImplementedError(_NOT_USED)

    async def update(self, customer: CustomerEntity) -> CustomerEntity:
        raise NotImplementedError(_NOT_USED)

    async def delete(self, customer_id: UUID) -> None:
        raise NotImplementedError(_NOT_USED)

    async def exists_by_customer_code(self, customer_code: str) -> bool:
        raise NotImplementedError(_NOT_USED)

    async def is_referenced_by_active_mapping(self, customer_id: UUID) -> bool:
        raise NotImplementedError(_NOT_USED)

    async def is_referenced_by_invoice_header(self, customer_id: UUID) -> bool:
        raise NotImplementedError(_NOT_USED)


class _InMemoryProductRepository(IProductRepository):
    """Ordered in-memory ``IProductRepository`` (master pagination only)."""

    def __init__(self, masters: list[ProductMasterEntity]) -> None:
        self._masters = list(masters)

    async def list_masters(
        self, skip: int = 0, limit: int = 20
    ) -> list[ProductMasterEntity]:
        return self._masters[skip : skip + limit]

    async def count_masters(self) -> int:
        return len(self._masters)

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

    async def get_product_name_for_detail(self, detail_id: UUID) -> str | None:
        raise NotImplementedError(_NOT_USED)


# ─── Per-master dataset factories (distinct, insertion-ordered records) ───


def _entity_dataset(n: int) -> list[EntityEntity]:
    return [EntityEntity(entity_name=f"Entity {i}") for i in range(n)]


def _vendor_dataset(n: int) -> list[VendorEntity]:
    return [
        VendorEntity(
            vendor_code=f"V{i}",
            vendor_name=f"Vendor {i}",
            vendor_email=f"vendor{i}@example.com",
        )
        for i in range(n)
    ]


def _customer_dataset(n: int) -> list[CustomerEntity]:
    return [
        CustomerEntity(customer_code=f"C{i}", customer_name=f"Customer {i}")
        for i in range(n)
    ]


def _product_master_dataset(n: int) -> list[ProductMasterEntity]:
    return [
        ProductMasterEntity(
            basic_material_code=f"BMC{i}", product_name=f"Product {i}"
        )
        for i in range(n)
    ]


async def _list_entities(
    records: list[EntityEntity], skip: int, limit: int
) -> tuple[list[object], int]:
    service = EntityService(
        session=None,  # type: ignore[arg-type]
        entity_repo=_InMemoryEntityRepository(records),
    )
    return await service.list_entities(skip=skip, limit=limit)


async def _list_vendors(
    records: list[VendorEntity], skip: int, limit: int
) -> tuple[list[object], int]:
    service = VendorService(
        session=None,  # type: ignore[arg-type]
        vendor_repo=_InMemoryVendorRepository(records),
        user_repo=None,  # type: ignore[arg-type]  # unused by list_vendors
    )
    return await service.list_vendors(skip=skip, limit=limit)


async def _list_customers(
    records: list[CustomerEntity], skip: int, limit: int
) -> tuple[list[object], int]:
    service = CustomerService(
        session=None,  # type: ignore[arg-type]
        customer_repo=_InMemoryCustomerRepository(records),
    )
    return await service.list_customers(skip=skip, limit=limit)


async def _list_product_masters(
    records: list[ProductMasterEntity], skip: int, limit: int
) -> tuple[list[object], int]:
    service = ProductService(
        session=None,  # type: ignore[arg-type]
        product_repo=_InMemoryProductRepository(records),
    )
    return await service.list_masters(skip=skip, limit=limit)


# One entry per paginated master list covered by Property 6.
_MASTERS = (
    ("entity", _entity_dataset, _list_entities),
    ("vendor", _vendor_dataset, _list_vendors),
    ("customer", _customer_dataset, _list_customers),
    ("product_master", _product_master_dataset, _list_product_masters),
)


@settings(max_examples=20)
@given(
    total=st.integers(min_value=0, max_value=30),
    skip=st.integers(min_value=0, max_value=35),
    limit=st.integers(min_value=1, max_value=100),
)
def test_pagination_returns_requested_slice_with_full_total(
    total: int, skip: int, limit: int
) -> None:
    """Every paginated master returns ``dataset[skip:skip+limit]`` and full total.

    The same valid ``skip``/``limit`` is applied to a freshly seeded dataset for
    each master. The returned page must equal the deterministically ordered
    slice (compared by record identity), and the reported ``total`` must equal
    the full dataset size regardless of the page bounds (Req 1.9, 6.11, 8.7,
    9.7).
    """

    async def scenario() -> None:
        for name, make_dataset, list_call in _MASTERS:
            dataset = make_dataset(total)
            expected_page = dataset[skip : skip + limit]

            items, reported_total = await list_call(dataset, skip, limit)

            # The page is exactly the requested slice, in order, by identity.
            assert [r.id for r in items] == [r.id for r in expected_page], (
                f"{name}: page mismatch for total={total}, "
                f"skip={skip}, limit={limit}"
            )
            # The page never exceeds the requested limit.
            assert len(items) <= limit, f"{name}: page exceeded limit"
            # total reflects the whole dataset, independent of the page bounds.
            assert reported_total == total, (
                f"{name}: total {reported_total} != dataset size {total}"
            )

    asyncio.run(scenario())
