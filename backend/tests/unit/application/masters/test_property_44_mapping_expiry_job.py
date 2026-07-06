# Feature: lacm-masters, Property 44: End-of-day job expires only past-due active mappings.
"""Property-based test for the end-of-day Vendor-Customer Mapping expiry job.

Property 44: End-of-day job expires only past-due active mappings.

**Validates: Requirements 15.1, 15.2**

*For any* set of Mappings and any current date, the end-of-day expiry job sets
Status to ``Expired`` for exactly those Mappings whose Status is ``Active`` and
whose ``validity_to`` is earlier than the current date, and leaves all other
Mappings unchanged (on-or-after-date active Mappings and already-expired
Mappings are untouched).

The property drives the real
:meth:`MappingService.expire_due_mappings` over an in-memory fake repository
that implements the Mapping repository port (the same port the scheduler task
uses), so no database is required. For each randomly generated population of
Mappings and an arbitrary ``today``, the test computes the expected set of
Mappings that must transition to ``Expired`` (Active and ``validity_to``
strictly before ``today``) and asserts that:

* exactly those Mappings end up ``Expired`` and carry the system modifier,
* every other Mapping keeps its original Status untouched, and
* the returned count equals the size of the expected set.
"""

from __future__ import annotations

import asyncio
from datetime import date
from uuid import UUID, uuid4

from hypothesis import given, settings
from hypothesis import strategies as st

from src.application.services.masters.mapping_service import MappingService
from src.domain.entities.masters.mapping import MappingEntity
from src.domain.enums.masters import MappingStatus
from src.domain.repositories.masters.mapping_repository import IMappingRepository


class FakeMappingRepository(IMappingRepository):
    """In-memory Mapping repository implementing the expiry-sweep port."""

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
        return list(self.store.values())[skip : skip + limit]

    async def count(
        self,
        vendor_id: UUID | None = None,
        customer_id: UUID | None = None,
    ) -> int:
        return len(self.store)

    async def find_overlapping_active(
        self,
        vendor_id: UUID,
        customer_id: UUID,
        validity_from: date,
        validity_to: date,
        exclude_id: UUID | None = None,
    ) -> list[MappingEntity]:
        return []

    async def list_active_due_for_expiry(
        self, today: date
    ) -> list[MappingEntity]:
        return [
            m
            for m in self.store.values()
            if m.status is MappingStatus.Active and m.validity_to < today
        ]


def _make_service(repo: FakeMappingRepository) -> MappingService:
    return MappingService(
        session=None,  # type: ignore[arg-type]
        mapping_repo=repo,  # type: ignore[arg-type]
        vendor_repo=None,  # type: ignore[arg-type]  # unused by the expiry sweep
        customer_repo=None,  # type: ignore[arg-type]  # unused by the expiry sweep
    )


# A bounded date window so generated validity_to dates straddle ``today`` often,
# exercising both the past-due and not-yet-due branches.
_dates = st.dates(min_value=date(2020, 1, 1), max_value=date(2030, 12, 31))
_statuses = st.sampled_from(list(MappingStatus))


@st.composite
def _mappings(draw: st.DrawFn) -> list[tuple[date, MappingStatus]]:
    """Generate a population of (validity_to, status) pairs for Mappings."""
    return draw(
        st.lists(st.tuples(_dates, _statuses), min_size=0, max_size=12)
    )


@settings(max_examples=20, deadline=None)
@given(population=_mappings(), today=_dates)
def test_end_of_day_job_expires_only_past_due_active_mappings(
    population: list[tuple[date, MappingStatus]], today: date
) -> None:
    """Exactly Active + validity_to < today become Expired; all else unchanged."""
    repo = FakeMappingRepository()
    original_status: dict[UUID, MappingStatus] = {}
    expected_expired: set[UUID] = set()

    for validity_to, status in population:
        mapping = MappingEntity(
            id=uuid4(),
            vendor_id=uuid4(),
            customer_id=uuid4(),
            validity_from=date(2020, 1, 1),
            validity_to=validity_to,
            status=status,
            created_by="tester",
            modified_by="tester",
        )
        repo.store[mapping.id] = mapping
        original_status[mapping.id] = status
        if status is MappingStatus.Active and validity_to < today:
            expected_expired.add(mapping.id)

    service = _make_service(repo)
    count = asyncio.run(service.expire_due_mappings(today))

    # The returned count matches the number of past-due active Mappings.
    assert count == len(expected_expired)

    for mapping_id, mapping in repo.store.items():
        if mapping_id in expected_expired:
            # Targeted Mappings transition to Expired with the system modifier.
            assert mapping.status is MappingStatus.Expired
            assert mapping.modified_by == "system"
        else:
            # Every other Mapping keeps its original Status untouched.
            assert mapping.status == original_status[mapping_id]
