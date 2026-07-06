# Feature: lacm-masters, Property 41: No overlapping active mappings per vendor + customer.
"""Property-based test for the Vendor-Customer Mapping overlap rule.

Property 41: No overlapping active mappings per vendor + customer.

**Validates: Requirements 14.4**

*For any* two Mapping validity periods for the same Vendor and Customer,
creating the second as active is rejected with a ``MasterConflictError`` *if and
only if* the inclusive periods overlap, where two inclusive ``[from, to]``
periods overlap exactly when each period's From Date is on or before the other
period's To Date (``a.from <= b.to AND b.from <= a.to``).

Strategy
--------
Each Hypothesis example generates two validity periods (each a ``from <= to``
pair of dates drawn from a bounded window). The first Mapping is always created
successfully for a fixed Vendor + Customer. We then attempt to create the second
Mapping for the **same** Vendor + Customer and assert:

* when the periods overlap, the create is rejected with ``MasterConflictError``
  and only the first Mapping remains stored; and
* when they do not overlap, the create succeeds and both Mappings are stored.

The expected overlap outcome is computed independently from the boolean
predicate above, so the test pins the *if-and-only-if* behaviour rather than
mirroring the service's implementation.

The repositories are lightweight in-memory fakes (duck-typed against the
repository ports, not mocks) so no database is involved; the
``FakeMappingRepository.find_overlapping_active`` query implements the same
inclusive-overlap semantics the production query is specified to use. The async
service is driven with ``asyncio.run`` because each Hypothesis example is
independent.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from datetime import date
from uuid import UUID, uuid4

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from src.application.exceptions.application_exceptions import MasterConflictError
from src.application.services.masters.mapping_service import (
    MappingCreateInput,
    MappingService,
)
from src.domain.entities.masters.mapping import MappingEntity
from src.domain.entities.user import User
from src.domain.enums.masters import MappingStatus


# ─────────────────────────── In-memory fakes ───────────────────────────


class FakeMappingRepository:
    """In-memory mapping repository with inclusive-overlap query semantics."""

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
        # Inclusive overlap: m.from <= new.to AND new.from <= m.to (Req 14.4).
        return [
            m
            for m in self.store.values()
            if m.vendor_id == vendor_id
            and m.customer_id == customer_id
            and m.status == MappingStatus.Active
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
            if m.status == MappingStatus.Active and m.validity_to < today
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


@dataclass(frozen=True)
class _Period:
    from_date: date
    to_date: date


def _overlaps(a: _Period, b: _Period) -> bool:
    """Inclusive overlap predicate, computed independently of the service."""
    return a.from_date <= b.to_date and b.from_date <= a.to_date


def _make_input(
    vendor_id: UUID, customer_id: UUID, period: _Period
) -> MappingCreateInput:
    return MappingCreateInput(
        vendor_id=vendor_id,
        customer_id=customer_id,
        validity_from=period.from_date,
        validity_to=period.to_date,
    )


# ─────────────────────────────── Strategy ──────────────────────────────

_MIN_DATE = date(2024, 1, 1)
_MAX_DATE = date(2024, 12, 31)


@st.composite
def _periods(draw: st.DrawFn) -> _Period:
    """Generate an inclusive validity period with From <= To."""
    d1 = draw(st.dates(min_value=_MIN_DATE, max_value=_MAX_DATE))
    d2 = draw(st.dates(min_value=_MIN_DATE, max_value=_MAX_DATE))
    lo, hi = sorted((d1, d2))
    return _Period(from_date=lo, to_date=hi)


# ──────────────────────────────── Test ─────────────────────────────────


@settings(max_examples=20)
@given(first=_periods(), second=_periods())
def test_overlap_rejected_iff_periods_overlap(first: _Period, second: _Period) -> None:
    """Second active Mapping is rejected iff its period overlaps the first."""

    async def scenario() -> None:
        actor = User(id=uuid4(), username="tester", is_active=True)
        vendor_id = uuid4()
        customer_id = uuid4()
        mapping_repo = FakeMappingRepository()
        service = MappingService(
            session=None,  # type: ignore[arg-type]
            mapping_repo=mapping_repo,  # type: ignore[arg-type]
            vendor_repo=FakeVendorRepository({vendor_id}),  # type: ignore[arg-type]
            customer_repo=FakeCustomerRepository({customer_id}),  # type: ignore[arg-type]
        )

        # The first active Mapping always persists successfully.
        await service.create_mapping(
            _make_input(vendor_id, customer_id, first), actor
        )

        expected_overlap = _overlaps(first, second)

        if expected_overlap:
            with pytest.raises(MasterConflictError):
                await service.create_mapping(
                    _make_input(vendor_id, customer_id, second), actor
                )
            # Rejected create persisted nothing: only the first remains.
            assert len(mapping_repo.store) == 1
        else:
            await service.create_mapping(
                _make_input(vendor_id, customer_id, second), actor
            )
            # Non-overlapping create succeeds: both Mappings are stored.
            assert len(mapping_repo.store) == 2

    asyncio.run(scenario())
