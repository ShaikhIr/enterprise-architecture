# Feature: lacm-masters, Property 34: Agreement vendor-scoped listing.
"""Property-based test for vendor-scoped Agreement listing.

Property 34: Agreement vendor-scoped listing.

**Validates: Requirements 11.10, 20.4**

*For any* agreement dataset and any ``vendor_id`` filter, the result contains
only agreements belonging to that Vendor; and for any vendor-agent actor the
result contains only agreements belonging to the agent's own Vendor.

``AgreementService.list_agreements`` implements the filter directly (Req 11.10),
and the controller enforces vendor-agent scoping (Req 20.4) by passing the
agent's own Vendor as ``vendor_id``. The vendor-agent guarantee therefore
reduces, at the service boundary, to the same ``vendor_id`` filter: when a
Vendor is supplied the page and total must contain *only* that Vendor's
Agreements and must *exclude every* record belonging to any other Vendor.

The service is exercised end-to-end through a real in-memory implementation of
the agreement repository port (not a mock); its ``list_all``/``count_all``
apply the documented vendor filter and preserve insertion order. A fresh
service/repository pair is built per generated example so no state leaks
between examples, and the async service is driven with ``asyncio.run`` because
each Hypothesis example is independent.
"""

from __future__ import annotations

import asyncio
from datetime import date
from decimal import Decimal
from uuid import UUID, uuid4

from hypothesis import given, settings
from hypothesis import strategies as st

from src.application.services.masters.agreement_service import AgreementService
from src.domain.entities.masters.agreement import AgreementEntity
from src.domain.enums.masters import AgreementStatus
from src.domain.repositories.masters.agreement_repository import IAgreementRepository

_NOT_USED = "method not exercised by the vendor-scoped listing property"

# A wide page so the returned slice captures the whole matching set; this lets
# the property assert on the *complete* vendor-scoped result, independent of
# pagination (which is covered by Property 6).
_WIDE_LIMIT = 10_000

# Fixed pool of distinct Vendors the dataset draws from. Index 5 is reserved as
# a Vendor that owns no Agreement (an "empty" filter target).
_VENDOR_COUNT = 5


class _InMemoryAgreementRepository(IAgreementRepository):
    """Ordered in-memory ``IAgreementRepository`` honouring the vendor filter."""

    def __init__(self, records: list[AgreementEntity]) -> None:
        self._records = list(records)

    async def list_all(
        self, skip: int = 0, limit: int = 20, vendor_id: UUID | None = None
    ) -> list[AgreementEntity]:
        items = [
            a
            for a in self._records
            if vendor_id is None or a.vendor_id == vendor_id
        ]
        return items[skip : skip + limit]

    async def count_all(self, vendor_id: UUID | None = None) -> int:
        return len(
            [
                a
                for a in self._records
                if vendor_id is None or a.vendor_id == vendor_id
            ]
        )

    # --- Unused by Property 34 ---
    async def get_by_id(self, agreement_id: UUID) -> AgreementEntity | None:
        raise NotImplementedError(_NOT_USED)

    async def create(self, agreement: AgreementEntity) -> AgreementEntity:
        raise NotImplementedError(_NOT_USED)

    async def update(self, agreement: AgreementEntity) -> AgreementEntity:
        raise NotImplementedError(_NOT_USED)

    async def delete(self, agreement_id: UUID) -> None:
        raise NotImplementedError(_NOT_USED)

    async def find_overlapping_active(
        self,
        vendor_id: UUID,
        product_detail_id: UUID,
        from_date: date,
        to_date: date,
        exclude_id: UUID | None = None,
    ) -> list[AgreementEntity]:
        raise NotImplementedError(_NOT_USED)

    async def list_due_for_expiry(self, today: date) -> list[AgreementEntity]:
        raise NotImplementedError(_NOT_USED)

    async def exists_expired_for_vendor_and_detail(
        self, vendor_id: UUID, product_detail_id: UUID, on_date: date
    ) -> bool:
        raise NotImplementedError(_NOT_USED)


def _make_agreement(vendor_id: UUID) -> AgreementEntity:
    """Build a distinct, valid-enough Agreement owned by ``vendor_id``.

    Only ``vendor_id`` and identity matter for the scoping property; the slab
    parameters are arbitrary fixed values.
    """
    return AgreementEntity(
        vendor_id=vendor_id,
        product_detail_id=uuid4(),
        from_date=date(2024, 1, 1),
        to_date=date(2024, 12, 31),
        slab_in_days=30,
        reduction_percent=Decimal("5"),
        max_commission_percent=Decimal("10"),
        min_commission_percent=Decimal("2"),
        credit_days=45,
        status=AgreementStatus.Active,
    )


@settings(max_examples=20)
@given(
    # Each integer assigns one Agreement to a Vendor in the pool [0, 4].
    assignments=st.lists(
        st.integers(min_value=0, max_value=_VENDOR_COUNT - 1), max_size=30
    ),
    # 0..4 select an existing pool Vendor; 5 selects a Vendor owning no records.
    filter_choice=st.integers(min_value=0, max_value=_VENDOR_COUNT),
)
def test_listing_is_scoped_to_the_filtered_vendor(
    assignments: list[int], filter_choice: int
) -> None:
    """A ``vendor_id`` filter returns only that Vendor's Agreements.

    The returned page contains exactly the dataset's Agreements for the filtered
    Vendor (by identity), every returned record belongs to that Vendor, no other
    Vendor's record appears, and ``total`` equals the count of that Vendor's
    Agreements. The unfiltered listing reports the whole dataset (Req 11.10,
    20.4).
    """

    async def scenario() -> None:
        vendors = [uuid4() for _ in range(_VENDOR_COUNT)]
        dataset = [_make_agreement(vendors[i]) for i in assignments]
        service = AgreementService(
            session=None,  # type: ignore[arg-type]
            agreement_repo=_InMemoryAgreementRepository(dataset),
            vendor_repo=None,  # type: ignore[arg-type]  # unused by list_agreements
            product_repo=None,  # type: ignore[arg-type]  # unused by list_agreements
        )

        # An existing pool Vendor, or a fresh Vendor that owns nothing.
        filter_vendor = (
            vendors[filter_choice] if filter_choice < _VENDOR_COUNT else uuid4()
        )
        expected = [a for a in dataset if a.vendor_id == filter_vendor]

        items, total = await service.list_agreements(
            vendor_id=filter_vendor, limit=_WIDE_LIMIT
        )

        # Every returned record belongs to the filtered Vendor only ...
        assert all(a.vendor_id == filter_vendor for a in items), (
            "vendor-scoped listing leaked another Vendor's Agreement"
        )
        # ... and no other Vendor's record appears (exclusion, Req 20.4).
        assert {a.id for a in items} == {a.id for a in expected}, (
            "scoped page is not exactly the filtered Vendor's Agreements"
        )
        # total reflects the filtered Vendor's full count.
        assert total == len(expected), (
            f"total {total} != filtered count {len(expected)}"
        )

        # Sanity: the unfiltered listing still reports the whole dataset.
        all_items, all_total = await service.list_agreements(limit=_WIDE_LIMIT)
        assert all_total == len(dataset)
        assert len(all_items) == len(dataset)

    asyncio.run(scenario())
