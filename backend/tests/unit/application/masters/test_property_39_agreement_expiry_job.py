# Feature: lacm-masters, Property 39: Daily job expires only past-due active agreements.
"""Property-based test for the daily Agreement expiry job.

Property 39: Daily job expires only past-due active agreements.

**Validates: Requirements 13.4**

*For any* set of Agreements and any current date, the daily expiry job sets
Status to ``Expired`` for exactly those Agreements whose Status is ``Active`` and
whose To Date is earlier than the current date, and leaves all other Agreements
unchanged.

The property drives the real
:meth:`AgreementService.expire_due_agreements` over an in-memory fake repository
that implements the agreement repository port (the same port the daily scheduler
task uses), so no database is required. For each randomly generated population of
Agreements and an arbitrary ``today``, the test computes the expected set of
Agreements that must transition to ``Expired`` (Active and To Date strictly
before ``today``) and asserts that:

* exactly those Agreements end up ``Expired`` and carry the system modifier,
* every other Agreement keeps its original Status untouched, and
* the returned count equals the size of the expected set.
"""

from __future__ import annotations

import asyncio
from datetime import date
from uuid import UUID, uuid4

from hypothesis import given, settings
from hypothesis import strategies as st

from src.application.services.masters.agreement_service import AgreementService
from src.domain.entities.masters.agreement import AgreementEntity
from src.domain.enums.masters import AgreementStatus, AgreementType
from src.domain.repositories.masters.agreement_repository import IAgreementRepository


class FakeAgreementRepository(IAgreementRepository):
    """In-memory agreement repository implementing the expiry-sweep port."""

    def __init__(self) -> None:
        self.store: dict[UUID, AgreementEntity] = {}

    async def get_by_id(self, agreement_id: UUID) -> AgreementEntity | None:
        return self.store.get(agreement_id)

    async def create(self, agreement: AgreementEntity) -> AgreementEntity:
        self.store[agreement.id] = agreement
        return agreement

    async def update(self, agreement: AgreementEntity) -> AgreementEntity:
        self.store[agreement.id] = agreement
        return agreement

    async def delete(self, agreement_id: UUID) -> None:
        self.store.pop(agreement_id, None)

    async def list_all(
        self, skip: int = 0, limit: int = 20, vendor_id: UUID | None = None
    ) -> list[AgreementEntity]:
        return list(self.store.values())[skip : skip + limit]

    async def count_all(self, vendor_id: UUID | None = None) -> int:
        return len(self.store)

    async def find_overlapping_active(
        self,
        vendor_id: UUID,
        product_master_id: UUID,
        from_date: date,
        to_date: date,
        exclude_id: UUID | None = None,
    ) -> list[AgreementEntity]:
        return []

    async def list_due_for_expiry(self, today: date) -> list[AgreementEntity]:
        return [
            a
            for a in self.store.values()
            if a.status == AgreementStatus.Active
            and a.to_date is not None
            and a.to_date < today
        ]

    async def exists_expired_for_vendor_and_detail(
        self, vendor_id: UUID, product_master_id: UUID, on_date: date
    ) -> bool:
        return False


def _make_service(repo: FakeAgreementRepository) -> AgreementService:
    return AgreementService(
        session=None,  # type: ignore[arg-type]
        agreement_repo=repo,
        vendor_repo=None,  # type: ignore[arg-type]  # unused by the expiry sweep
        product_repo=None,  # type: ignore[arg-type]  # unused by the expiry sweep
    )


# A bounded date window so generated To Dates straddle ``today`` often, exercising
# both the past-due and not-yet-due branches.
_dates = st.dates(min_value=date(2020, 1, 1), max_value=date(2030, 12, 31))
_statuses = st.sampled_from(list(AgreementStatus))


@st.composite
def _agreements(draw: st.DrawFn) -> list[tuple[date, AgreementStatus]]:
    """Generate a population of (to_date, status) pairs for Agreements."""
    return draw(
        st.lists(st.tuples(_dates, _statuses), min_size=0, max_size=12)
    )


@settings(max_examples=20, deadline=None)
@given(population=_agreements(), today=_dates)
def test_daily_job_expires_only_past_due_active_agreements(
    population: list[tuple[date, AgreementStatus]], today: date
) -> None:
    """Exactly Active + To Date < today become Expired; all else is unchanged."""
    repo = FakeAgreementRepository()
    original_status: dict[UUID, AgreementStatus] = {}
    expected_expired: set[UUID] = set()

    for to_date, status in population:
        agreement = AgreementEntity(
            id=uuid4(),
            vendor_id=uuid4(),
            product_master_id=uuid4(),
            from_date=date(2020, 1, 1),
            to_date=to_date,
            agreement_type=AgreementType.Original,
            status=status,
            created_by="tester",
            modified_by="tester",
        )
        repo.store[agreement.id] = agreement
        original_status[agreement.id] = status
        if status == AgreementStatus.Active and to_date < today:
            expected_expired.add(agreement.id)

    service = _make_service(repo)
    count = asyncio.run(service.expire_due_agreements(today))

    # The returned count matches the number of past-due active Agreements.
    assert count == len(expected_expired)

    for agreement_id, agreement in repo.store.items():
        if agreement_id in expected_expired:
            # Targeted Agreements transition to Expired with the system modifier.
            assert agreement.status == AgreementStatus.Expired
            assert agreement.modified_by == "system"
        else:
            # Every other Agreement keeps its original Status untouched.
            assert agreement.status == original_status[agreement_id]
