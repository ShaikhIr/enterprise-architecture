# Feature: lacm-masters, Property 32: Agreement defaults applied before validation.
"""Property-based test for Agreement creation defaults (Type=Original, Status=Active).

Property 32: Agreement defaults applied before validation.

**Validates: Requirements 11.8**

*For any* valid create-Agreement request that omits Agreement Type and Status,
the stored Agreement has Agreement Type ``Original`` and Status ``Active``.

``AgreementCreateInput`` carries no Agreement Type / Status fields, so every
create request implicitly omits them and the service must stamp the
``Original`` / ``Active`` defaults. This test generates a wide range of *valid*
create requests (existing Vendor + Product Detail, From <= To, percentages in
0-100 with Min <= Max, Slab > 0, Credit Days >= 0, and an optional valid
document) and confirms the persisted Agreement always carries the defaults while
preserving the supplied fields.

The service is exercised end-to-end through real in-memory implementations of
the agreement / vendor / product repository ports (not mocks). A fresh
service/repository set is built per generated example so no state leaks between
examples. The async service is driven with ``asyncio.run`` because each
Hypothesis example is independent.
"""

from __future__ import annotations

import asyncio
from datetime import date
from decimal import Decimal
from uuid import UUID, uuid4

from hypothesis import given, settings
from hypothesis import strategies as st

from src.application.services.masters.agreement_service import (
    AgreementCreateInput,
    AgreementDocumentInput,
    AgreementService,
)
from src.domain.entities.masters.agreement import AgreementEntity
from src.domain.entities.user import User
from src.domain.enums.masters import AgreementStatus, AgreementType
from src.domain.repositories.masters.agreement_repository import IAgreementRepository


class _InMemoryAgreementRepository(IAgreementRepository):
    """Minimal real ``IAgreementRepository`` backed by a dict."""

    def __init__(self) -> None:
        self._store: dict[UUID, AgreementEntity] = {}

    async def get_by_id(self, agreement_id: UUID) -> AgreementEntity | None:
        return self._store.get(agreement_id)

    async def create(self, agreement: AgreementEntity) -> AgreementEntity:
        self._store[agreement.id] = agreement
        return agreement

    async def update(self, agreement: AgreementEntity) -> AgreementEntity:
        self._store[agreement.id] = agreement
        return agreement

    async def delete(self, agreement_id: UUID) -> None:
        self._store.pop(agreement_id, None)

    async def list_all(
        self, skip: int = 0, limit: int = 20, vendor_id: UUID | None = None
    ) -> list[AgreementEntity]:
        items = [
            a
            for a in self._store.values()
            if vendor_id is None or a.vendor_id == vendor_id
        ]
        return items[skip : skip + limit]

    async def count_all(self, vendor_id: UUID | None = None) -> int:
        return len(
            [
                a
                for a in self._store.values()
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
            for a in self._store.values()
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
            for a in self._store.values()
            if a.status == AgreementStatus.Active and a.to_date < today
        ]

    async def exists_expired_for_vendor_and_detail(
        self, vendor_id: UUID, product_detail_id: UUID, on_date: date
    ) -> bool:
        return any(
            a.vendor_id == vendor_id
            and a.product_detail_id == product_detail_id
            and a.to_date < on_date
            for a in self._store.values()
        )


class _InMemoryVendorRepository:
    """Minimal vendor-existence fake (only the method the service uses)."""

    def __init__(self, vendor_id: UUID) -> None:
        self._ids = {vendor_id}

    async def get_by_id(self, vendor_id: UUID):
        return object() if vendor_id in self._ids else None


class _InMemoryProductRepository:
    """Minimal product-detail-existence fake (only the method the service uses)."""

    def __init__(self, detail_id: UUID) -> None:
        self._detail_ids = {detail_id}

    async def get_detail_by_id(self, detail_id: UUID):
        return object() if detail_id in self._detail_ids else None


# ─── Strategies constrained to the VALID create-Agreement input space ───

# Percentages: 0-100 inclusive, two decimal places, as Decimal.
_percent = st.integers(min_value=0, max_value=10000).map(
    lambda cents: (Decimal(cents) / Decimal(100))
)

# A bounded date range so From <= To always holds.
_dates = st.dates(min_value=date(2000, 1, 1), max_value=date(2100, 12, 31))


@st.composite
def _ordered_dates(draw: st.DrawFn) -> tuple[date, date]:
    a = draw(_dates)
    b = draw(_dates)
    return (a, b) if a <= b else (b, a)


@st.composite
def _commission_bounds(draw: st.DrawFn) -> tuple[Decimal, Decimal]:
    """Return (min_commission, max_commission) with min <= max, both 0-100."""
    a = draw(_percent)
    b = draw(_percent)
    return (a, b) if a <= b else (b, a)


# Optional valid Agreement Document: absent, or an allowed type within 10 MB.
_allowed_doc = st.builds(
    AgreementDocumentInput,
    content_type=st.sampled_from(
        ["application/pdf", "image/jpeg", "image/jpg", "image/png"]
    ),
    size_bytes=st.integers(min_value=0, max_value=10 * 1024 * 1024),
    storage_ref=st.none() | st.text(min_size=1, max_size=50),
)
_optional_document = st.none() | _allowed_doc


@settings(max_examples=20)
@given(
    period=_ordered_dates(),
    slab_in_days=st.integers(min_value=1, max_value=3650),
    reduction_percent=_percent,
    commission=_commission_bounds(),
    credit_days=st.integers(min_value=0, max_value=3650),
    document=_optional_document,
)
def test_valid_agreement_creation_defaults_original_active(
    period: tuple[date, date],
    slab_in_days: int,
    reduction_percent: Decimal,
    commission: tuple[Decimal, Decimal],
    credit_days: int,
    document: AgreementDocumentInput | None,
) -> None:
    """Any valid create-Agreement request defaults Type=Original, Status=Active.

    The request never supplies Agreement Type or Status (the input has no such
    fields), so the service must stamp ``Original`` / ``Active`` (Req 11.8).
    Supplied fields are preserved exactly on the persisted record.
    """
    from_date, to_date = period
    min_commission, max_commission = commission

    async def scenario() -> AgreementEntity:
        vendor_id = uuid4()
        detail_id = uuid4()
        repo = _InMemoryAgreementRepository()
        service = AgreementService(
            session=None,  # type: ignore[arg-type]
            agreement_repo=repo,
            vendor_repo=_InMemoryVendorRepository(vendor_id),  # type: ignore[arg-type]
            product_repo=_InMemoryProductRepository(detail_id),  # type: ignore[arg-type]
        )
        actor = User(id=uuid4(), username="admin", is_active=True)

        created = await service.create_agreement(
            AgreementCreateInput(
                vendor_id=vendor_id,
                product_detail_id=detail_id,
                from_date=from_date,
                to_date=to_date,
                slab_in_days=slab_in_days,
                reduction_percent=reduction_percent,
                max_commission_percent=max_commission,
                min_commission_percent=min_commission,
                credit_days=credit_days,
                document=document,
                # Agreement Type / Status are not part of the create input and
                # are therefore always omitted, exercising the defaults.
            ),
            actor,
        )
        # Read it back by its generated id to confirm what was persisted.
        return await service.get_agreement(created.id)

    stored = asyncio.run(scenario())

    # Defaults applied (Req 11.8).
    assert stored.agreement_type == AgreementType.Original
    assert stored.status == AgreementStatus.Active

    # Supplied fields are preserved exactly.
    assert stored.from_date == from_date
    assert stored.to_date == to_date
    assert stored.slab_in_days == slab_in_days
    assert stored.reduction_percent == reduction_percent
    assert stored.max_commission_percent == max_commission
    assert stored.min_commission_percent == min_commission
    assert stored.credit_days == credit_days
    # New (non-renewal) agreements never reference a prior agreement.
    assert stored.prior_agreement_id is None
