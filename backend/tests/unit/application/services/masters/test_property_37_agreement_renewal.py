# Feature: lacm-masters, Property 37: Renewal marks prior and links new agreement.
"""Property-based test for Agreement renewal.

Property 37: Renewal marks prior and links new agreement.

**Validates: Requirements 13.1, 13.2**

*For any* existing Agreement, a renew operation sets the prior Agreement's
Status to ``Renewed`` (Req 13.1) and creates a new Agreement of type
``Renewal`` whose Prior Agreement reference (``prior_agreement_id``) points to
the prior Agreement (Req 13.2).

The service is exercised against real in-memory implementations of the
agreement/vendor/product repository ports (fakes, not mocks), so the property
validates actual ``AgreementService.renew_agreement`` logic end-to-end through
the ports. Each Hypothesis example drives the async service via ``asyncio.run``
so examples stay isolated.
"""

from __future__ import annotations

import asyncio
from dataclasses import replace
from datetime import date, timedelta
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
from src.domain.enums.masters import AgreementStatus, AgreementType
from src.domain.repositories.masters.agreement_repository import IAgreementRepository


# ─── In-memory fakes (real port implementations, not mocks) ───


class FakeAgreementRepository(IAgreementRepository):
    """In-memory implementation of the agreement repository port."""

    def __init__(self) -> None:
        self.store: dict[UUID, AgreementEntity] = {}

    async def get_by_id(self, agreement_id: UUID) -> AgreementEntity | None:
        # Return a detached copy: the service mutates its working entity during
        # validation, but those changes only become persisted state when
        # ``update`` is called (mirroring a DB load/commit boundary).
        stored = self.store.get(agreement_id)
        return replace(stored) if stored is not None else None

    async def create(self, agreement: AgreementEntity) -> AgreementEntity:
        self.store[agreement.id] = agreement
        return agreement

    async def update(self, agreement: AgreementEntity) -> AgreementEntity:
        self.store[agreement.id] = agreement
        return agreement

    async def delete(self, agreement_id: UUID) -> None:
        self.store.pop(agreement_id, None)
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
        product_detail_id: UUID,
        from_date: date,
        to_date: date,
        exclude_id: UUID | None = None,
    ) -> list[AgreementEntity]:
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
    ) -> bool:
        return any(
            a.vendor_id == vendor_id
            and a.product_detail_id == product_detail_id
            and a.to_date < on_date
            for a in self.store.values()
        )


class FakeVendorRepository:
    """Minimal vendor-lookup fake (only the method the service uses)."""

    def __init__(self) -> None:
        self.ids: set[UUID] = set()

    def add(self, vendor_id: UUID) -> None:
        self.ids.add(vendor_id)

    async def get_by_id(self, vendor_id: UUID):
        return object() if vendor_id in self.ids else None


class FakeProductRepository:
    """Minimal product-detail-lookup fake (only the method the service uses)."""

    def __init__(self) -> None:
        self.detail_ids: set[UUID] = set()

    def add_detail(self, detail_id: UUID) -> None:
        self.detail_ids.add(detail_id)

    async def get_detail_by_id(self, detail_id: UUID):
        return object() if detail_id in self.detail_ids else None


def _actor() -> User:
    return User(id=uuid4(), username="tester", is_active=True)


def _seeded_service() -> tuple[AgreementService, UUID, UUID]:
    """Build a service with one seeded Vendor and Product Detail."""
    agreement_repo = FakeAgreementRepository()
    vendor_repo = FakeVendorRepository()
    product_repo = FakeProductRepository()
    vendor_id = uuid4()
    detail_id = uuid4()
    vendor_repo.add(vendor_id)
    product_repo.add_detail(detail_id)
    service = AgreementService(
        session=None,  # type: ignore[arg-type]
        agreement_repo=agreement_repo,
        vendor_repo=vendor_repo,  # type: ignore[arg-type]
        product_repo=product_repo,  # type: ignore[arg-type]
    )
    return service, vendor_id, detail_id


# ─── Strategies for valid commission parameters and validity periods ───

_percent = st.decimals(
    min_value=Decimal("0"),
    max_value=Decimal("100"),
    allow_nan=False,
    allow_infinity=False,
    places=2,
)


@st.composite
def _commission_bounds(draw: st.DrawFn) -> tuple[Decimal, Decimal, Decimal]:
    """Draw (reduction, max, min) with 0 ≤ min ≤ max ≤ 100 and reduction 0-100."""
    max_v = draw(_percent)
    min_v = draw(
        st.decimals(
            min_value=Decimal("0"),
            max_value=max_v,
            allow_nan=False,
            allow_infinity=False,
            places=2,
        )
    )
    reduction = draw(_percent)
    return reduction, max_v, min_v


@st.composite
def _valid_period(draw: st.DrawFn) -> tuple[date, date]:
    """Draw a (from_date, to_date) pair with from ≤ to."""
    from_d = draw(st.dates(min_value=date(2000, 1, 1), max_value=date(2099, 1, 1)))
    span = draw(st.integers(min_value=0, max_value=3650))
    return from_d, from_d + timedelta(days=span)


@st.composite
def _renewal_scenario(draw: st.DrawFn) -> dict[str, object]:
    """Draw the parameters for the prior agreement and its renewal."""
    prior_reduction, prior_max, prior_min = draw(_commission_bounds())
    prior_from, prior_to = draw(_valid_period())

    renew_reduction, renew_max, renew_min = draw(_commission_bounds())
    renew_from, renew_to = draw(_valid_period())

    # Optionally override vendor/detail on the renewal so we exercise the
    # inherit-from-prior behaviour when these are omitted (None).
    return dict(
        prior=dict(
            from_date=prior_from,
            to_date=prior_to,
            slab_in_days=draw(st.integers(min_value=1, max_value=365)),
            reduction_percent=prior_reduction,
            max_commission_percent=prior_max,
            min_commission_percent=prior_min,
            credit_days=draw(st.integers(min_value=0, max_value=365)),
        ),
        renewal=dict(
            from_date=renew_from,
            to_date=renew_to,
            slab_in_days=draw(st.integers(min_value=1, max_value=365)),
            reduction_percent=renew_reduction,
            max_commission_percent=renew_max,
            min_commission_percent=renew_min,
            credit_days=draw(st.integers(min_value=0, max_value=365)),
        ),
    )


async def _assert_renewal(scenario: dict[str, object]) -> None:
    service, vendor_id, detail_id = _seeded_service()
    repo: FakeAgreementRepository = service._agreement_repo  # type: ignore[assignment]

    prior_kwargs = dict(scenario["prior"])  # type: ignore[arg-type]
    prior = await service.create_agreement(
        AgreementCreateInput(
            vendor_id=vendor_id,
            product_detail_id=detail_id,
            **prior_kwargs,  # type: ignore[arg-type]
        ),
        _actor(),
    )
    prior_id = prior.id

    # Renewal omits vendor_id/product_detail_id so the service inherits them.
    renewal = await service.renew_agreement(
        prior_id,
        AgreementRenewalInput(**scenario["renewal"]),  # type: ignore[arg-type]
        _actor(),
    )

    # Req 13.1: the prior agreement is now marked Renewed.
    stored_prior = repo.store[prior_id]
    assert stored_prior.status == AgreementStatus.Renewed

    # Req 13.2: the new agreement is of type Renewal and links the prior.
    assert renewal.id != prior_id
    assert renewal.agreement_type == AgreementType.Renewal
    assert renewal.prior_agreement_id == prior_id
    assert renewal.status == AgreementStatus.Active

    # The new agreement is persisted and inherits vendor/detail from the prior.
    stored_renewal = repo.store[renewal.id]
    assert stored_renewal.prior_agreement_id == prior_id
    assert stored_renewal.vendor_id == vendor_id
    assert stored_renewal.product_detail_id == detail_id


@settings(max_examples=20)
@given(scenario=_renewal_scenario())
def test_renewal_marks_prior_and_links_new_agreement(
    scenario: dict[str, object],
) -> None:
    """Renewing an Agreement marks the prior ``Renewed`` and links the new one.

    For any existing Agreement, ``renew_agreement`` must set the prior
    Agreement's Status to ``Renewed`` (Req 13.1) and create a new Agreement of
    type ``Renewal`` whose ``prior_agreement_id`` points to the prior
    Agreement (Req 13.2).
    """
    asyncio.run(_assert_renewal(scenario))
