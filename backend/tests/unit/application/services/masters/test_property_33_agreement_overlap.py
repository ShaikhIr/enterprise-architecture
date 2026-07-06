# Feature: lacm-masters, Property 33: No overlapping active agreements per vendor + product detail.
"""Property-based test for the Agreement overlap rule.

Property 33: No overlapping active agreements per vendor + product detail.

**Validates: Requirements 11.7**

*For any* two Agreement validity periods for the same Vendor and Product Detail,
attempting to create the second as active is rejected with a
``MasterConflictError`` *if and only if* the periods overlap, where two
inclusive ``[from, to]`` periods overlap exactly when each period's From Date is
on or before the other period's To Date
(``a.from <= b.to AND b.from <= a.to``).

Strategy
--------
Each Hypothesis example generates two validity periods (each a ``from <= to``
pair of dates drawn from a bounded window). The first Agreement is always
created successfully for a fixed Vendor + Product Detail. We then attempt to
create the second Agreement for the **same** Vendor + Product Detail and assert:

* when the periods overlap, the create is rejected with ``MasterConflictError``
  and only the first Agreement remains stored; and
* when they do not overlap, the create succeeds and both Agreements are stored.

The expected overlap outcome is computed independently from the boolean
predicate above, so the test pins the *if-and-only-if* behaviour rather than
mirroring the service's implementation.

The repositories are lightweight in-memory fakes (duck-typed against the
repository ports, not mocks) so no database is involved; the
``FakeAgreementRepository.find_overlapping_active`` query implements the same
inclusive-overlap semantics the production query is specified to use. The async
service is driven with ``asyncio.run`` because each Hypothesis example is
independent.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from uuid import UUID, uuid4

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from src.application.exceptions.application_exceptions import MasterConflictError
from src.application.services.masters.agreement_service import (
    AgreementCreateInput,
    AgreementService,
)
from src.domain.entities.masters.agreement import AgreementEntity
from src.domain.entities.user import User
from src.domain.enums.masters import AgreementStatus
from src.domain.repositories.masters.agreement_repository import IAgreementRepository


# ─────────────────────────── In-memory fakes ───────────────────────────


class FakeAgreementRepository(IAgreementRepository):
    """In-memory agreement repository with inclusive-overlap query semantics."""

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
        items = [
            a
            for a in self.store.values()
            if vendor_id is None or a.vendor_id == vendor_id
        ]
        return items[skip : skip + limit]

    async def count_all(self, vendor_id: UUID | None = None) -> int:
        return len(
            [
                a
                for a in self.store.values()
                if vendor_id is None or a.vendor_id == vendor_id
            ]
        )

    async def find_overlapping_active(
        self,
        vendor_id: UUID,
        product_detail_id: UUID,
        from_date: date,
        to_date: date,
        exclude_id: UUID | None = None,
    ) -> list[AgreementEntity]:
        # Inclusive overlap: a.from <= new.to AND new.from <= a.to (Req 11.7).
        return [
            a
            for a in self.store.values()
            if a.vendor_id == vendor_id
            and a.product_detail_id == product_detail_id
            and a.status == AgreementStatus.Active
            and a.id != exclude_id
            and a.from_date <= to_date
            and from_date <= a.to_date
        ]

    async def list_due_for_expiry(self, today: date) -> list[AgreementEntity]:
        return [
            a
            for a in self.store.values()
            if a.status == AgreementStatus.Active and a.to_date < today
        ]

    async def exists_expired_for_vendor_and_detail(
        self, vendor_id: UUID, product_detail_id: UUID, on_date: date
    ) -> bool:  # pragma: no cover - not exercised by this property
        return any(
            a.vendor_id == vendor_id
            and a.product_detail_id == product_detail_id
            and a.to_date < on_date
            for a in self.store.values()
        )


class FakeVendorRepository:
    """Minimal vendor lookup fake that accepts a known set of ids."""

    def __init__(self, known: set[UUID]) -> None:
        self._known = known

    async def get_by_id(self, vendor_id: UUID):
        return object() if vendor_id in self._known else None


class FakeProductRepository:
    """Minimal product-detail lookup fake that accepts a known set of ids."""

    def __init__(self, known: set[UUID]) -> None:
        self._known = known

    async def get_detail_by_id(self, detail_id: UUID):
        return object() if detail_id in self._known else None


@dataclass(frozen=True)
class _Period:
    from_date: date
    to_date: date


def _overlaps(a: _Period, b: _Period) -> bool:
    """Inclusive overlap predicate, computed independently of the service."""
    return a.from_date <= b.to_date and b.from_date <= a.to_date


def _make_input(
    vendor_id: UUID, detail_id: UUID, period: _Period
) -> AgreementCreateInput:
    return AgreementCreateInput(
        vendor_id=vendor_id,
        product_detail_id=detail_id,
        from_date=period.from_date,
        to_date=period.to_date,
        slab_in_days=30,
        reduction_percent=Decimal("5"),
        max_commission_percent=Decimal("10"),
        min_commission_percent=Decimal("2"),
        credit_days=45,
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
    """Second active Agreement is rejected iff its period overlaps the first."""

    async def scenario() -> None:
        actor = User(id=uuid4(), username="tester", is_active=True)
        vendor_id = uuid4()
        detail_id = uuid4()
        agreement_repo = FakeAgreementRepository()
        service = AgreementService(
            session=None,  # type: ignore[arg-type]
            agreement_repo=agreement_repo,
            vendor_repo=FakeVendorRepository({vendor_id}),  # type: ignore[arg-type]
            product_repo=FakeProductRepository({detail_id}),  # type: ignore[arg-type]
        )

        # The first active Agreement always persists successfully.
        await service.create_agreement(
            _make_input(vendor_id, detail_id, first), actor
        )

        expected_overlap = _overlaps(first, second)

        if expected_overlap:
            with pytest.raises(MasterConflictError):
                await service.create_agreement(
                    _make_input(vendor_id, detail_id, second), actor
                )
            # Rejected create persisted nothing: only the first remains.
            assert len(agreement_repo.store) == 1
        else:
            await service.create_agreement(
                _make_input(vendor_id, detail_id, second), actor
            )
            # Non-overlapping create succeeds: both Agreements are stored.
            assert len(agreement_repo.store) == 2

    asyncio.run(scenario())
