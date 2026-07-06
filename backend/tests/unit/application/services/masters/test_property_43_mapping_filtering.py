# Feature: lacm-masters, Property 43: Mapping filtering by vendor and/or customer.
"""Property-based test for Vendor-Customer Mapping combined-filter listing.

Property 43: Mapping filtering by vendor and/or customer.

**Validates: Requirements 14.7**

*For any* set of stored Mappings and *any* combination of ``vendor_id`` and/or
``customer_id`` filters, ``MappingService.list_mappings`` returns exactly the
Mappings that match **all** supplied filters (an unsupplied filter matches
everything), and the reported total equals the number of matching Mappings.

Strategy
--------
Each Hypothesis example builds a small pool of Vendors and Customers and a list
of Mapping "selections" (a Vendor index + Customer index). Every generated
Mapping is given a **unique calendar year** for its validity period, so no two
Mappings ever overlap; this lets us freely create many Mappings for the same
Vendor + Customer pair without tripping the inclusive-overlap rule (Req 14.4,
covered by Property 41) which is out of scope here.

After creating all Mappings against real in-memory repository fakes (duck-typed
against the ports, not mocks), we exercise every interesting filter combination:

* no filter (matches all),
* ``vendor_id`` only (each known Vendor, plus an unknown Vendor),
* ``customer_id`` only (each known Customer, plus an unknown Customer),
* both ``vendor_id`` and ``customer_id`` together (each known pair, plus
  unknown combinations).

For each combination the expected matching set is computed independently from
the create log via the plain predicate "matches every supplied filter", so the
test pins the specified behaviour rather than mirroring the service. A list
limit large enough to cover every stored Mapping is used so filtering — not
pagination — is what is under test.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from datetime import date
from uuid import UUID, uuid4

from hypothesis import given, settings
from hypothesis import strategies as st

from src.application.services.masters.mapping_service import (
    MappingCreateInput,
    MappingService,
)
from src.domain.entities.masters.mapping import MappingEntity
from src.domain.entities.user import User
from src.domain.enums.masters import MappingStatus


# ─────────────────────────── In-memory fakes ───────────────────────────


class FakeMappingRepository:
    """In-memory mapping repository implementing the combined-filter query."""

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
        # Inclusive overlap; unique years per Mapping means this never fires here.
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

    async def list_active_due_for_expiry(
        self, today: date
    ) -> list[MappingEntity]:  # pragma: no cover - not exercised by this property
        return [
            m
            for m in self.store.values()
            if m.status is MappingStatus.Active and m.validity_to < today
        ]


class FakeVendorRepository:
    """Minimal vendor lookup fake that accepts a known set of ids."""

    def __init__(self, known: set[UUID]) -> None:
        self._known = known

    async def get_by_id(self, vendor_id: UUID):
        return object() if vendor_id in self._known else None


class FakeCustomerRepository:
    """Minimal customer lookup fake that accepts a known set of ids."""

    def __init__(self, known: set[UUID]) -> None:
        self._known = known

    async def get_by_id(self, customer_id: UUID):
        return object() if customer_id in self._known else None


def _actor() -> User:
    return User(id=uuid4(), username="tester", is_active=True)


# Large enough to cover every Mapping a single example can generate, so the list
# slice never drops a matching row — filtering, not pagination, is under test.
_BIG_LIMIT = 10_000


# ─────────────────────────────── Strategy ──────────────────────────────


@dataclass(frozen=True)
class _Scenario:
    n_vendors: int
    n_customers: int
    selections: tuple[tuple[int, int], ...]


@st.composite
def _scenarios(draw: st.DrawFn) -> _Scenario:
    n_vendors = draw(st.integers(min_value=1, max_value=3))
    n_customers = draw(st.integers(min_value=1, max_value=3))
    selections = draw(
        st.lists(
            st.tuples(
                st.integers(min_value=0, max_value=n_vendors - 1),
                st.integers(min_value=0, max_value=n_customers - 1),
            ),
            min_size=0,
            max_size=8,
        )
    )
    return _Scenario(
        n_vendors=n_vendors,
        n_customers=n_customers,
        selections=tuple(selections),
    )


# ──────────────────────────────── Test ─────────────────────────────────


@settings(max_examples=20)
@given(scenario=_scenarios())
def test_list_mappings_filters_by_vendor_and_or_customer(
    scenario: _Scenario,
) -> None:
    """list_mappings returns exactly the Mappings matching all supplied filters."""

    async def run() -> None:
        vendor_ids = [uuid4() for _ in range(scenario.n_vendors)]
        customer_ids = [uuid4() for _ in range(scenario.n_customers)]

        mapping_repo = FakeMappingRepository()
        service = MappingService(
            session=None,  # type: ignore[arg-type]
            mapping_repo=mapping_repo,  # type: ignore[arg-type]
            vendor_repo=FakeVendorRepository(set(vendor_ids)),  # type: ignore[arg-type]
            customer_repo=FakeCustomerRepository(set(customer_ids)),  # type: ignore[arg-type]
        )

        # Create every selected Mapping, each in a unique year so no two periods
        # ever overlap (sidesteps the overlap rule, which Property 41 covers).
        created: list[tuple[UUID, UUID, UUID]] = []  # (mapping_id, vendor, customer)
        for offset, (vi, ci) in enumerate(scenario.selections):
            year = 2000 + offset  # unique per Mapping → globally non-overlapping
            mapping = await service.create_mapping(
                MappingCreateInput(
                    vendor_id=vendor_ids[vi],
                    customer_id=customer_ids[ci],
                    validity_from=date(year, 1, 1),
                    validity_to=date(year, 6, 1),
                ),
                _actor(),
            )
            created.append((mapping.id, vendor_ids[vi], customer_ids[ci]))

        def expected_ids(
            vendor_id: UUID | None, customer_id: UUID | None
        ) -> set[UUID]:
            return {
                mid
                for (mid, v, c) in created
                if (vendor_id is None or v == vendor_id)
                and (customer_id is None or c == customer_id)
            }

        async def check(vendor_id: UUID | None, customer_id: UUID | None) -> None:
            items, total = await service.list_mappings(
                skip=0,
                limit=_BIG_LIMIT,
                vendor_id=vendor_id,
                customer_id=customer_id,
            )
            want = expected_ids(vendor_id, customer_id)
            got = {m.id for m in items}
            assert got == want
            assert total == len(want)
            # Every returned Mapping genuinely satisfies all supplied filters.
            for m in items:
                assert vendor_id is None or m.vendor_id == vendor_id
                assert customer_id is None or m.customer_id == customer_id

        unknown_vendor = uuid4()
        unknown_customer = uuid4()
        vendor_choices: list[UUID | None] = [None, *vendor_ids, unknown_vendor]
        customer_choices: list[UUID | None] = [None, *customer_ids, unknown_customer]

        # Exercise every combination: none, vendor-only, customer-only, and both,
        # including unknown ids that must match nothing.
        for vid in vendor_choices:
            for cid in customer_choices:
                await check(vid, cid)

    asyncio.run(run())
