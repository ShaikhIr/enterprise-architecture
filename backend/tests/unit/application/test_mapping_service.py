"""
Unit tests for MappingService (CRUD, overlap, filter, dates-only update).

Uses lightweight in-memory fakes for the Mapping, Vendor, and Customer
repositories so the service's business rules run against real logic (no mocking
of the behaviour under test). Covers Requirements 14.2–14.9 and 20.4.
"""

from __future__ import annotations

from datetime import date
from uuid import UUID, uuid4

import pytest

from src.application.exceptions.application_exceptions import (
    MasterConflictError,
    MasterNotFoundError,
    MasterValidationError,
)
from src.application.services.masters.mapping_service import (
    MappingCreateInput,
    MappingService,
    MappingUpdateInput,
)
from src.domain.entities.masters.mapping import MappingEntity
from src.domain.entities.user import User
from src.domain.enums.masters import MappingStatus

# ─── In-memory fakes ───


class FakeMappingRepository:
    """Minimal in-memory IMappingRepository for service unit tests."""

    def __init__(self) -> None:
        self._store: dict[UUID, MappingEntity] = {}

    async def get_by_id(self, mapping_id: UUID) -> MappingEntity | None:
        return self._store.get(mapping_id)

    async def create(self, mapping: MappingEntity) -> MappingEntity:
        self._store[mapping.id] = mapping
        return mapping

    async def update(self, mapping: MappingEntity) -> MappingEntity:
        if mapping.id not in self._store:
            raise ValueError("Mapping not found")
        self._store[mapping.id] = mapping
        return mapping

    async def delete(self, mapping_id: UUID) -> None:
        self._store.pop(mapping_id, None)

    def _matches(
        self,
        m: MappingEntity,
        vendor_id: UUID | None,
        customer_id: UUID | None,
    ) -> bool:
        if vendor_id is not None and m.vendor_id != vendor_id:
            return False
        if customer_id is not None and m.customer_id != customer_id:
            return False
        return True

    async def list_mappings(
        self,
        skip: int = 0,
        limit: int = 20,
        vendor_id: UUID | None = None,
        customer_id: UUID | None = None,
    ) -> list[MappingEntity]:
        ordered = sorted(self._store.values(), key=lambda m: m.created_date)
        filtered = [
            m for m in ordered if self._matches(m, vendor_id, customer_id)
        ]
        return filtered[skip : skip + limit]

    async def count(
        self,
        vendor_id: UUID | None = None,
        customer_id: UUID | None = None,
    ) -> int:
        return sum(
            1
            for m in self._store.values()
            if self._matches(m, vendor_id, customer_id)
        )

    async def find_overlapping_active(
        self,
        vendor_id: UUID,
        customer_id: UUID,
        validity_from: date,
        validity_to: date,
        exclude_id: UUID | None = None,
    ) -> list[MappingEntity]:
        result: list[MappingEntity] = []
        for m in self._store.values():
            if exclude_id is not None and m.id == exclude_id:
                continue
            if m.status is not MappingStatus.Active:
                continue
            if m.vendor_id != vendor_id or m.customer_id != customer_id:
                continue
            # Inclusive overlap test.
            if m.validity_from <= validity_to and validity_from <= m.validity_to:
                result.append(m)
        return result

    async def list_active_due_for_expiry(
        self, today: date
    ) -> list[MappingEntity]:
        return [
            m
            for m in self._store.values()
            if m.status is MappingStatus.Active and m.validity_to < today
        ]


class FakeVendorRepository:
    """In-memory vendor existence store (only get_by_id is exercised here)."""

    def __init__(self) -> None:
        self._ids: set[UUID] = set()

    def add(self, vendor_id: UUID) -> None:
        self._ids.add(vendor_id)

    async def get_by_id(self, vendor_id: UUID):
        return object() if vendor_id in self._ids else None


class FakeCustomerRepository:
    """In-memory customer existence store (only get_by_id is exercised here)."""

    def __init__(self) -> None:
        self._ids: set[UUID] = set()

    def add(self, customer_id: UUID) -> None:
        self._ids.add(customer_id)

    async def get_by_id(self, customer_id: UUID):
        return object() if customer_id in self._ids else None


# ─── Fixtures ───


@pytest.fixture
def actor() -> User:
    return User(id=uuid4(), username="admin", password_hash="x", is_active=True)


@pytest.fixture
def mapping_repo() -> FakeMappingRepository:
    return FakeMappingRepository()


@pytest.fixture
def vendor_repo() -> FakeVendorRepository:
    return FakeVendorRepository()


@pytest.fixture
def customer_repo() -> FakeCustomerRepository:
    return FakeCustomerRepository()


@pytest.fixture
def known_vendor(vendor_repo) -> UUID:
    vid = uuid4()
    vendor_repo.add(vid)
    return vid


@pytest.fixture
def known_customer(customer_repo) -> UUID:
    cid = uuid4()
    customer_repo.add(cid)
    return cid


def _service(mapping_repo, vendor_repo, customer_repo) -> MappingService:
    return MappingService(
        session=None,  # type: ignore[arg-type]  # unused by the fakes
        mapping_repo=mapping_repo,
        vendor_repo=vendor_repo,
        customer_repo=customer_repo,
    )


def _create_input(vendor_id, customer_id, **overrides) -> MappingCreateInput:
    base = dict(
        vendor_id=vendor_id,
        customer_id=customer_id,
        validity_from=date(2025, 1, 1),
        validity_to=date(2025, 12, 31),
    )
    base.update(overrides)
    return MappingCreateInput(**base)


# ─── Create: defaults Active (Req 14.5) ───


async def test_create_defaults_status_active(
    mapping_repo, vendor_repo, customer_repo, actor, known_vendor, known_customer
):
    service = _service(mapping_repo, vendor_repo, customer_repo)

    mapping = await service.create_mapping(
        _create_input(known_vendor, known_customer), actor
    )

    assert mapping.status is MappingStatus.Active
    assert mapping.vendor_id == known_vendor
    assert mapping.customer_id == known_customer
    assert await mapping_repo.count() == 1


# ─── Create: existence validation (Req 14.2) ───


async def test_create_rejects_unknown_vendor(
    mapping_repo, vendor_repo, customer_repo, actor, known_customer
):
    service = _service(mapping_repo, vendor_repo, customer_repo)

    with pytest.raises(MasterValidationError) as exc:
        await service.create_mapping(
            _create_input(uuid4(), known_customer), actor
        )

    assert exc.value.field == "vendor_id"
    assert await mapping_repo.count() == 0


async def test_create_rejects_unknown_customer(
    mapping_repo, vendor_repo, customer_repo, actor, known_vendor
):
    service = _service(mapping_repo, vendor_repo, customer_repo)

    with pytest.raises(MasterValidationError) as exc:
        await service.create_mapping(
            _create_input(known_vendor, uuid4()), actor
        )

    assert exc.value.field == "customer_id"
    assert await mapping_repo.count() == 0


# ─── Create: From ≤ To validation (Req 14.3) ───


async def test_create_rejects_from_after_to(
    mapping_repo, vendor_repo, customer_repo, actor, known_vendor, known_customer
):
    service = _service(mapping_repo, vendor_repo, customer_repo)

    with pytest.raises(MasterValidationError) as exc:
        await service.create_mapping(
            _create_input(
                known_vendor,
                known_customer,
                validity_from=date(2025, 6, 1),
                validity_to=date(2025, 1, 1),
            ),
            actor,
        )

    assert exc.value.field == "validity_from"
    assert await mapping_repo.count() == 0


async def test_create_accepts_equal_from_and_to(
    mapping_repo, vendor_repo, customer_repo, actor, known_vendor, known_customer
):
    service = _service(mapping_repo, vendor_repo, customer_repo)

    same_day = date(2025, 3, 15)
    mapping = await service.create_mapping(
        _create_input(
            known_vendor,
            known_customer,
            validity_from=same_day,
            validity_to=same_day,
        ),
        actor,
    )
    assert mapping.validity_from == mapping.validity_to == same_day


# ─── Create: inclusive overlap rejection (Req 14.4) ───


async def test_create_rejects_overlapping_active_mapping(
    mapping_repo, vendor_repo, customer_repo, actor, known_vendor, known_customer
):
    service = _service(mapping_repo, vendor_repo, customer_repo)
    await service.create_mapping(
        _create_input(
            known_vendor,
            known_customer,
            validity_from=date(2025, 1, 1),
            validity_to=date(2025, 6, 30),
        ),
        actor,
    )

    with pytest.raises(MasterConflictError):
        await service.create_mapping(
            _create_input(
                known_vendor,
                known_customer,
                validity_from=date(2025, 6, 30),  # touches the prior end (inclusive)
                validity_to=date(2025, 12, 31),
            ),
            actor,
        )
    assert await mapping_repo.count() == 1


async def test_create_allows_adjacent_non_overlapping_period(
    mapping_repo, vendor_repo, customer_repo, actor, known_vendor, known_customer
):
    service = _service(mapping_repo, vendor_repo, customer_repo)
    await service.create_mapping(
        _create_input(
            known_vendor,
            known_customer,
            validity_from=date(2025, 1, 1),
            validity_to=date(2025, 6, 30),
        ),
        actor,
    )

    # Starts the day after the prior period ends → no overlap.
    second = await service.create_mapping(
        _create_input(
            known_vendor,
            known_customer,
            validity_from=date(2025, 7, 1),
            validity_to=date(2025, 12, 31),
        ),
        actor,
    )
    assert second.id is not None
    assert await mapping_repo.count() == 2


async def test_create_allows_overlap_for_different_customer(
    mapping_repo, vendor_repo, customer_repo, actor, known_vendor
):
    other_customer = uuid4()
    customer_repo.add(other_customer)
    first_customer = uuid4()
    customer_repo.add(first_customer)
    service = _service(mapping_repo, vendor_repo, customer_repo)

    await service.create_mapping(
        _create_input(known_vendor, first_customer), actor
    )
    # Same vendor, same dates, different customer → allowed.
    second = await service.create_mapping(
        _create_input(known_vendor, other_customer), actor
    )
    assert second.id is not None
    assert await mapping_repo.count() == 2


# ─── Read (Req 14.9) ───


async def test_get_returns_existing_mapping(
    mapping_repo, vendor_repo, customer_repo, actor, known_vendor, known_customer
):
    service = _service(mapping_repo, vendor_repo, customer_repo)
    created = await service.create_mapping(
        _create_input(known_vendor, known_customer), actor
    )

    fetched = await service.get_mapping(created.id)
    assert fetched.id == created.id


async def test_get_unknown_id_raises_not_found(
    mapping_repo, vendor_repo, customer_repo
):
    service = _service(mapping_repo, vendor_repo, customer_repo)
    with pytest.raises(MasterNotFoundError):
        await service.get_mapping(uuid4())


# ─── Update: dates only (Req 14.6) ───


async def test_update_changes_only_validity_dates(
    mapping_repo, vendor_repo, customer_repo, actor, known_vendor, known_customer
):
    service = _service(mapping_repo, vendor_repo, customer_repo)
    created = await service.create_mapping(
        _create_input(
            known_vendor,
            known_customer,
            validity_from=date(2025, 1, 1),
            validity_to=date(2025, 6, 30),
        ),
        actor,
    )
    original_status = created.status
    original_vendor = created.vendor_id
    original_customer = created.customer_id

    updated = await service.update_mapping(
        created.id,
        MappingUpdateInput(
            validity_from=date(2025, 2, 1), validity_to=date(2025, 8, 31)
        ),
        actor,
    )

    assert updated.validity_from == date(2025, 2, 1)
    assert updated.validity_to == date(2025, 8, 31)
    # Everything else untouched.
    assert updated.status is original_status
    assert updated.vendor_id == original_vendor
    assert updated.customer_id == original_customer


async def test_update_partial_dates_preserves_unsupplied_date(
    mapping_repo, vendor_repo, customer_repo, actor, known_vendor, known_customer
):
    service = _service(mapping_repo, vendor_repo, customer_repo)
    created = await service.create_mapping(
        _create_input(
            known_vendor,
            known_customer,
            validity_from=date(2025, 1, 1),
            validity_to=date(2025, 6, 30),
        ),
        actor,
    )

    updated = await service.update_mapping(
        created.id, MappingUpdateInput(validity_to=date(2025, 9, 30)), actor
    )

    assert updated.validity_from == date(2025, 1, 1)  # unchanged
    assert updated.validity_to == date(2025, 9, 30)


async def test_update_rejects_from_after_to(
    mapping_repo, vendor_repo, customer_repo, actor, known_vendor, known_customer
):
    service = _service(mapping_repo, vendor_repo, customer_repo)
    created = await service.create_mapping(
        _create_input(known_vendor, known_customer), actor
    )

    with pytest.raises(MasterValidationError):
        await service.update_mapping(
            created.id,
            MappingUpdateInput(
                validity_from=date(2025, 12, 1), validity_to=date(2025, 1, 1)
            ),
            actor,
        )


async def test_update_rejects_overlap_with_other_mapping(
    mapping_repo, vendor_repo, customer_repo, actor, known_vendor, known_customer
):
    service = _service(mapping_repo, vendor_repo, customer_repo)
    await service.create_mapping(
        _create_input(
            known_vendor,
            known_customer,
            validity_from=date(2025, 1, 1),
            validity_to=date(2025, 6, 30),
        ),
        actor,
    )
    second = await service.create_mapping(
        _create_input(
            known_vendor,
            known_customer,
            validity_from=date(2025, 7, 1),
            validity_to=date(2025, 12, 31),
        ),
        actor,
    )

    # Stretch the second period back to collide with the first.
    with pytest.raises(MasterConflictError):
        await service.update_mapping(
            second.id, MappingUpdateInput(validity_from=date(2025, 6, 1)), actor
        )


async def test_update_does_not_conflict_with_itself(
    mapping_repo, vendor_repo, customer_repo, actor, known_vendor, known_customer
):
    service = _service(mapping_repo, vendor_repo, customer_repo)
    created = await service.create_mapping(
        _create_input(
            known_vendor,
            known_customer,
            validity_from=date(2025, 1, 1),
            validity_to=date(2025, 6, 30),
        ),
        actor,
    )

    # Shrinking within its own period must not trip the overlap guard.
    updated = await service.update_mapping(
        created.id, MappingUpdateInput(validity_to=date(2025, 5, 31)), actor
    )
    assert updated.validity_to == date(2025, 5, 31)


async def test_update_unknown_id_raises_not_found(
    mapping_repo, vendor_repo, customer_repo, actor
):
    service = _service(mapping_repo, vendor_repo, customer_repo)
    with pytest.raises(MasterNotFoundError):
        await service.update_mapping(
            uuid4(), MappingUpdateInput(validity_to=date(2025, 1, 1)), actor
        )


# ─── List: combined filters + empty result (Req 14.7, 14.8, 20.4) ───


async def test_list_filters_by_vendor_and_customer(
    mapping_repo, vendor_repo, customer_repo, actor
):
    v1, v2 = uuid4(), uuid4()
    c1, c2 = uuid4(), uuid4()
    for vid in (v1, v2):
        vendor_repo.add(vid)
    for cid in (c1, c2):
        customer_repo.add(cid)
    service = _service(mapping_repo, vendor_repo, customer_repo)

    await service.create_mapping(_create_input(v1, c1), actor)
    await service.create_mapping(_create_input(v1, c2), actor)
    await service.create_mapping(_create_input(v2, c1), actor)

    # vendor-only filter (vendor-scoped listing, Req 20.4)
    items, total = await service.list_mappings(vendor_id=v1)
    assert total == 2
    assert all(m.vendor_id == v1 for m in items)

    # combined vendor + customer filter (Req 14.7)
    items, total = await service.list_mappings(vendor_id=v1, customer_id=c2)
    assert total == 1
    assert items[0].vendor_id == v1 and items[0].customer_id == c2

    # customer-only filter
    items, total = await service.list_mappings(customer_id=c1)
    assert total == 2
    assert all(m.customer_id == c1 for m in items)


async def test_list_returns_empty_when_no_match(
    mapping_repo, vendor_repo, customer_repo, actor, known_vendor, known_customer
):
    service = _service(mapping_repo, vendor_repo, customer_repo)
    await service.create_mapping(
        _create_input(known_vendor, known_customer), actor
    )

    items, total = await service.list_mappings(vendor_id=uuid4())
    assert items == []
    assert total == 0


async def test_list_paginates_slice_with_full_total(
    mapping_repo, vendor_repo, customer_repo, actor, known_vendor
):
    customers = [uuid4() for _ in range(5)]
    for cid in customers:
        customer_repo.add(cid)
    service = _service(mapping_repo, vendor_repo, customer_repo)
    for cid in customers:
        await service.create_mapping(_create_input(known_vendor, cid), actor)

    items, total = await service.list_mappings(skip=1, limit=2, vendor_id=known_vendor)
    assert total == 5
    assert len(items) == 2


# ─── Delete (Req 14.9) ───


async def test_delete_removes_mapping(
    mapping_repo, vendor_repo, customer_repo, actor, known_vendor, known_customer
):
    service = _service(mapping_repo, vendor_repo, customer_repo)
    created = await service.create_mapping(
        _create_input(known_vendor, known_customer), actor
    )

    await service.delete_mapping(created.id, actor)
    assert await mapping_repo.get_by_id(created.id) is None


async def test_delete_unknown_id_raises_not_found(
    mapping_repo, vendor_repo, customer_repo, actor
):
    service = _service(mapping_repo, vendor_repo, customer_repo)
    with pytest.raises(MasterNotFoundError):
        await service.delete_mapping(uuid4(), actor)


# ─── Scheduler entry point ───


async def test_expire_due_mappings_only_expires_past_due(
    mapping_repo, vendor_repo, customer_repo, actor, known_vendor, known_customer
):
    service = _service(mapping_repo, vendor_repo, customer_repo)
    past = await service.create_mapping(
        _create_input(
            known_vendor,
            known_customer,
            validity_from=date(2024, 1, 1),
            validity_to=date(2024, 12, 31),
        ),
        actor,
    )
    other_customer = uuid4()
    customer_repo.add(other_customer)
    current = await service.create_mapping(
        _create_input(
            known_vendor,
            other_customer,
            validity_from=date(2025, 1, 1),
            validity_to=date(2025, 12, 31),
        ),
        actor,
    )

    expired_count = await service.expire_due_mappings(date(2025, 6, 1))

    assert expired_count == 1
    assert (await mapping_repo.get_by_id(past.id)).status is MappingStatus.Expired
    assert (await mapping_repo.get_by_id(current.id)).status is MappingStatus.Active
