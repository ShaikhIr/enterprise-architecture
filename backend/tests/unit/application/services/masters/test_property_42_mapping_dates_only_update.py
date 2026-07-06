# Feature: lacm-masters, Property 42: Mapping update changes only validity dates.
"""Property-based test for the dates-only Vendor-Customer Mapping update.

Property 42: Mapping update changes only validity dates.

**Validates: Requirements 14.6**

*For any* existing Mapping and any (valid) update request, only Validity From
and Validity To change to the supplied values; every other field — Vendor,
Customer, and Status in particular — remains unchanged.

The service is exercised against real in-memory implementations of the
mapping/vendor/customer repository ports (fakes, not mocks), so the property
validates actual ``MappingService.update_mapping`` logic end-to-end through the
ports. Each Hypothesis example drives the async service via ``asyncio.run`` so
examples stay isolated.

Scope notes: only a single Mapping is seeded per example, so the inclusive
overlap rule (Req 14.4) is trivially satisfied (the record excludes itself) and
the From ≤ To rule (Req 14.3) is upheld by generating ordered date pairs. Those
rejection behaviours are the subject of Properties 40/41 and are out of scope
here — this property concerns only *which fields change* on a successful update.
"""

from __future__ import annotations

import asyncio
from datetime import date
from uuid import UUID, uuid4

from hypothesis import given, settings
from hypothesis import strategies as st

from src.application.services.masters.mapping_service import (
    MappingCreateInput,
    MappingService,
    MappingUpdateInput,
)
from src.domain.entities.masters.mapping import MappingEntity
from src.domain.entities.user import User
from src.domain.enums.masters import MappingStatus


# ─── In-memory fakes (real port implementations, not mocks) ───


class FakeMappingRepository:
    """In-memory implementation of the mapping repository port."""

    def __init__(self) -> None:
        self.store: dict[UUID, MappingEntity] = {}

    async def get_by_id(self, mapping_id: UUID) -> MappingEntity | None:
        return self.store.get(mapping_id)

    async def create(self, mapping: MappingEntity) -> MappingEntity:
        self.store[mapping.id] = mapping
        return mapping

    async def update(self, mapping: MappingEntity) -> MappingEntity:
        self.store[mapping.id] = mapping
        return mapping

    async def delete(self, mapping_id: UUID) -> None:
        self.store.pop(mapping_id, None)

    async def list_mappings(
        self,
        skip: int = 0,
        limit: int = 20,
        vendor_id: UUID | None = None,
        customer_id: UUID | None = None,
    ) -> list[MappingEntity]:
        items = [
            m
            for m in self.store.values()
            if (vendor_id is None or m.vendor_id == vendor_id)
            and (customer_id is None or m.customer_id == customer_id)
        ]
        return items[skip : skip + limit]

    async def count(
        self,
        vendor_id: UUID | None = None,
        customer_id: UUID | None = None,
    ) -> int:
        return len(
            [
                m
                for m in self.store.values()
                if (vendor_id is None or m.vendor_id == vendor_id)
                and (customer_id is None or m.customer_id == customer_id)
            ]
        )

    async def find_overlapping_active(
        self,
        vendor_id: UUID,
        customer_id: UUID,
        validity_from: date,
        validity_to: date,
        exclude_id: UUID | None = None,
    ) -> list[MappingEntity]:
        return [
            m
            for m in self.store.values()
            if m.vendor_id == vendor_id
            and m.customer_id == customer_id
            and m.status is MappingStatus.Active
            and m.id != exclude_id
            and m.validity_from <= validity_to
            and validity_from <= m.validity_to
        ]

    async def list_active_due_for_expiry(self, today: date) -> list[MappingEntity]:
        return [
            m
            for m in self.store.values()
            if m.status is MappingStatus.Active and m.validity_to < today
        ]


class FakeVendorRepository:
    """Minimal vendor-lookup fake (only the method the service uses)."""

    def __init__(self) -> None:
        self.ids: set[UUID] = set()

    def add(self, vendor_id: UUID) -> None:
        self.ids.add(vendor_id)

    async def get_by_id(self, vendor_id: UUID):
        return object() if vendor_id in self.ids else None


class FakeCustomerRepository:
    """Minimal customer-lookup fake (only the method the service uses)."""

    def __init__(self) -> None:
        self.ids: set[UUID] = set()

    def add(self, customer_id: UUID) -> None:
        self.ids.add(customer_id)

    async def get_by_id(self, customer_id: UUID):
        return object() if customer_id in self.ids else None


def _actor(username: str = "updater") -> User:
    return User(id=uuid4(), username=username, is_active=True)


def _seeded_service() -> tuple[MappingService, UUID, UUID]:
    """Build a service with one seeded Vendor and Customer."""
    mapping_repo = FakeMappingRepository()
    vendor_repo = FakeVendorRepository()
    customer_repo = FakeCustomerRepository()
    vendor_id = uuid4()
    customer_id = uuid4()
    vendor_repo.add(vendor_id)
    customer_repo.add(customer_id)
    service = MappingService(
        session=None,  # type: ignore[arg-type]
        mapping_repo=mapping_repo,
        vendor_repo=vendor_repo,  # type: ignore[arg-type]
        customer_repo=customer_repo,  # type: ignore[arg-type]
    )
    return service, vendor_id, customer_id


# ─── Strategies ───

_dates = st.dates(min_value=date(2000, 1, 1), max_value=date(2100, 12, 31))


@st.composite
def _ordered_dates(draw: st.DrawFn) -> tuple[date, date]:
    """A valid (from <= to) date pair (endpoints may be equal)."""
    a = draw(_dates)
    b = draw(_dates)
    return (a, b) if a <= b else (b, a)


# ─── Property ───


@settings(max_examples=20)
@given(
    initial_dates=_ordered_dates(),
    new_dates=_ordered_dates(),
    initial_status=st.sampled_from(list(MappingStatus)),
)
def test_update_changes_only_validity_dates(
    initial_dates: tuple[date, date],
    new_dates: tuple[date, date],
    initial_status: MappingStatus,
) -> None:
    """A dates-only update changes only Validity From / To (Req 14.6).

    Given an existing Mapping with arbitrary Status and validity period, applying
    an update that supplies new (ordered) dates must leave the persisted Mapping
    with exactly those new dates and with Vendor, Customer, and Status unchanged.
    """
    init_from, init_to = initial_dates
    new_from, new_to = new_dates

    async def _run() -> None:
        service, vendor_id, customer_id = _seeded_service()
        repo: FakeMappingRepository = service._mapping_repo  # type: ignore[assignment]

        seeded = await service.create_mapping(
            MappingCreateInput(
                vendor_id=vendor_id,
                customer_id=customer_id,
                validity_from=init_from,
                validity_to=init_to,
                status=initial_status,
            ),
            _actor("creator"),
        )

        # Capture the fields that must NOT change.
        before_vendor = seeded.vendor_id
        before_customer = seeded.customer_id
        before_status = seeded.status

        updated = await service.update_mapping(
            seeded.id,
            MappingUpdateInput(validity_from=new_from, validity_to=new_to),
            _actor("updater"),
        )

        # Dates changed to exactly the supplied values...
        assert updated.validity_from == new_from
        assert updated.validity_to == new_to
        # ...and everything else is untouched.
        assert updated.vendor_id == before_vendor
        assert updated.customer_id == before_customer
        assert updated.status is before_status

        # The persisted record reflects the same outcome (one record, in place).
        assert len(repo.store) == 1
        stored = repo.store[seeded.id]
        assert stored.validity_from == new_from
        assert stored.validity_to == new_to
        assert stored.vendor_id == before_vendor
        assert stored.customer_id == before_customer
        assert stored.status is before_status

    asyncio.run(_run())
