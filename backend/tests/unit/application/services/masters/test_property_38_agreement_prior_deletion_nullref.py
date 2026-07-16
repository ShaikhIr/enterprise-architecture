# Feature: lacm-masters, Property 38: Deleting a prior agreement nulls renewal references.
"""Property-based test for Agreement deletion null-ref behaviour.

Property 38: Deleting a prior agreement nulls renewal references.

**Validates: Requirements 13.3**

*For any* renewal chain, deleting the prior Agreement sets the referencing
Renewal Agreement's Prior Agreement reference to null while retaining the
Renewal Agreement.

Strategy
--------
Each Hypothesis example builds a renewal chain of length ``N`` (1-5) for a fixed
Vendor + Product Detail: an Original Agreement followed by ``N - 1`` successive
renewals, where each renewal's ``prior_agreement_id`` points at its immediate
predecessor. Periods are sequential and non-overlapping so every renewal is
accepted. We then delete one Agreement chosen by index and assert:

* the deleted Agreement is gone and the store shrinks by exactly one;
* every other Agreement is retained; and
* any Agreement that referenced the deleted Agreement now has a ``None``
  Prior Agreement reference (the ``ON DELETE SET NULL`` behaviour), while all
  other Prior Agreement references are left unchanged.

The expected post-delete references are computed independently from the chain we
built, so the test pins the specified null-ref behaviour rather than mirroring
the repository implementation. Repositories are lightweight in-memory fakes
(duck-typed against the repository ports, not mocks); the
``FakeAgreementRepository.delete`` emulates the database ``ON DELETE SET NULL``
foreign key on ``prior_agreement_id``. The async service is driven with
``asyncio.run`` because each Hypothesis example is independent.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from uuid import UUID, uuid4

from hypothesis import given, settings
from hypothesis import strategies as st

from src.application.services.masters.agreement_service import (
    AgreementCreateInput,
    AgreementRenewalInput,
    AgreementService,
)
from src.domain.entities.masters.agreement import AgreementEntity
from src.domain.entities.user import User
from src.domain.enums.masters import AgreementStatus
from src.domain.repositories.masters.agreement_repository import IAgreementRepository


# ─────────────────────────── In-memory fakes ───────────────────────────


class FakeAgreementRepository(IAgreementRepository):
    """In-memory agreement repository emulating ON DELETE SET NULL."""

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
        # Emulate the FK ``ON DELETE SET NULL`` on prior_agreement_id (Req 13.3):
        # referencing renewals are retained, only their reference is nulled.
        for a in self.store.values():
            if a.prior_agreement_id == agreement_id:
                a.prior_agreement_id = None

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
        product_master_id: UUID,
        from_date: date,
        to_date: date,
        exclude_id: UUID | None = None,
    ) -> list[AgreementEntity]:
        return [
            a
            for a in self.store.values()
            if a.vendor_id == vendor_id
            and a.product_master_id == product_master_id
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
        self, vendor_id: UUID, product_master_id: UUID, on_date: date
    ) -> bool:  # pragma: no cover - not exercised by this property
        return any(
            a.vendor_id == vendor_id
            and a.product_master_id == product_master_id
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


# ─────────────────────────────── Strategy ──────────────────────────────


@dataclass(frozen=True)
class _ChainPlan:
    length: int  # number of agreements in the chain (1 original + renewals)
    delete_index: int  # index in [0, length) of the agreement to delete


@st.composite
def _chain_plans(draw: st.DrawFn) -> _ChainPlan:
    length = draw(st.integers(min_value=1, max_value=5))
    delete_index = draw(st.integers(min_value=0, max_value=length - 1))
    return _ChainPlan(length=length, delete_index=delete_index)


def _period(index: int) -> tuple[date, date]:
    """Sequential, non-overlapping six-month window for chain position ``index``."""
    year = 2000 + index
    return date(year, 1, 1), date(year, 6, 30)


def _create_input(
    vendor_id: UUID, detail_id: UUID, period: tuple[date, date]
) -> AgreementCreateInput:
    return AgreementCreateInput(
        vendor_id=vendor_id,
        product_master_id=detail_id,
        from_date=period[0],
        to_date=period[1],
        slab_in_days=30,
        reduction_percent=Decimal("5"),
        max_commission_percent=Decimal("10"),
        min_commission_percent=Decimal("2"),
        credit_days=45,
    )


def _renewal_input(period: tuple[date, date]) -> AgreementRenewalInput:
    return AgreementRenewalInput(
        from_date=period[0],
        to_date=period[1],
        slab_in_days=30,
        reduction_percent=Decimal("5"),
        max_commission_percent=Decimal("10"),
        min_commission_percent=Decimal("2"),
        credit_days=45,
    )


# ──────────────────────────────── Test ─────────────────────────────────


@settings(max_examples=20)
@given(plan=_chain_plans())
def test_delete_prior_nulls_referencing_renewal(plan: _ChainPlan) -> None:
    """Deleting a chain member nulls the referencing renewal, retaining it."""

    async def scenario() -> None:
        actor = User(id=uuid4(), username="tester", is_active=True)
        vendor_id = uuid4()
        detail_id = uuid4()
        repo = FakeAgreementRepository()
        service = AgreementService(
            session=None,  # type: ignore[arg-type]
            agreement_repo=repo,
            vendor_repo=FakeVendorRepository({vendor_id}),  # type: ignore[arg-type]
            product_repo=FakeProductRepository({detail_id}),  # type: ignore[arg-type]
        )

        # Build the renewal chain: an Original followed by successive renewals.
        chain: list[UUID] = []
        original = await service.create_agreement(
            _create_input(vendor_id, detail_id, _period(0)), actor
        )
        chain.append(original.id)
        for i in range(1, plan.length):
            renewal = await service.renew_agreement(
                chain[-1], _renewal_input(_period(i)), actor
            )
            chain.append(renewal.id)

        # Snapshot the prior-references just before the delete.
        before: dict[UUID, UUID | None] = {
            aid: repo.store[aid].prior_agreement_id for aid in chain
        }
        deleted_id = chain[plan.delete_index]

        await service.delete_agreement(deleted_id, actor)

        # The deleted Agreement is gone; exactly one record was removed.
        assert deleted_id not in repo.store
        assert len(repo.store) == plan.length - 1

        # Every surviving Agreement is retained, and its prior reference is the
        # original one unless it pointed at the deleted Agreement (now null).
        for aid in chain:
            if aid == deleted_id:
                continue
            assert aid in repo.store  # renewal retained (not cascade-deleted)
            expected_prior = None if before[aid] == deleted_id else before[aid]
            assert repo.store[aid].prior_agreement_id == expected_prior

    asyncio.run(scenario())
