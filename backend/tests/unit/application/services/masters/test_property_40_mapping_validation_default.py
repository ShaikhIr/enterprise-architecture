# Feature: lacm-masters, Property 40: Mapping validation and default.
"""Property-based test for Vendor-Customer Mapping create/update validation.

Property 40: Mapping validation and default.

**Validates: Requirements 14.2, 14.3, 14.5**

*For any* create- or update-Mapping request, the request is rejected with no
persist/modify when:

* the referenced Vendor does not exist (Req 14.2),
* the referenced Customer does not exist (Req 14.2),
* Validity From is later than Validity To (Req 14.3);

and *for any* valid create request the stored Mapping has Status ``Active``
(Req 14.5).

The service is exercised against real in-memory implementations of the
mapping/vendor/customer repository ports (fakes, not mocks), so the property
validates actual service logic end-to-end through the ports. Each Hypothesis
example drives the async service via ``asyncio.run`` so examples stay isolated.

Note on the update path: an update changes only the validity dates (Req 14.6),
so Vendor/Customer existence is fixed at create time and not re-checked; the
From ≤ To rule (Req 14.3) is, however, re-validated on update and is asserted
on both the create and update paths here. Overlap rejection (Req 14.4) is the
subject of Property 41 and is intentionally out of scope for this property.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from datetime import date
from uuid import UUID, uuid4

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from src.application.exceptions.application_exceptions import MasterValidationError
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


def _actor() -> User:
    return User(id=uuid4(), username="tester", is_active=True)


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

# Dates kept in a sane bounded window so generated pairs stay meaningful.
_dates = st.dates(min_value=date(2000, 1, 1), max_value=date(2100, 12, 31))


@st.composite
def _ordered_dates(draw: st.DrawFn) -> tuple[date, date]:
    """A valid (from <= to) date pair (endpoints may be equal)."""
    a = draw(_dates)
    b = draw(_dates)
    return (a, b) if a <= b else (b, a)


@st.composite
def _from_after_to_dates(draw: st.DrawFn) -> tuple[date, date]:
    """An invalid (from > to) date pair."""
    to_d = draw(st.dates(min_value=date(2000, 1, 2), max_value=date(2100, 12, 30)))
    from_d = draw(_dates.filter(lambda d: d > to_d))
    return from_d, to_d


@dataclass
class InvalidCase:
    """A single invalid create scenario with exactly one violated rule."""

    rule: str
    field: str
    overrides: dict[str, object] = field(default_factory=dict)
    # When set, the offending reference replaces the seeded id with an unknown one.
    unknown_vendor: bool = False
    unknown_customer: bool = False


@st.composite
def _invalid_cases(draw: st.DrawFn) -> InvalidCase:
    rule = draw(
        st.sampled_from(
            ["nonexistent_vendor", "nonexistent_customer", "from_after_to"]
        )
    )
    if rule == "nonexistent_vendor":
        return InvalidCase(rule, "vendor_id", unknown_vendor=True)
    if rule == "nonexistent_customer":
        return InvalidCase(rule, "customer_id", unknown_customer=True)
    # from_after_to
    from_d, to_d = draw(_from_after_to_dates())
    return InvalidCase(
        rule,
        "validity_from",
        {"validity_from": from_d, "validity_to": to_d},
    )


# ─── Create-path assertion ───


async def _assert_create_rejected(case: InvalidCase) -> None:
    service, vendor_id, customer_id = _seeded_service()
    repo: FakeMappingRepository = service._mapping_repo  # type: ignore[assignment]

    payload = MappingCreateInput(
        vendor_id=uuid4() if case.unknown_vendor else vendor_id,
        customer_id=uuid4() if case.unknown_customer else customer_id,
        validity_from=case.overrides.get("validity_from", date(2024, 1, 1)),  # type: ignore[arg-type]
        validity_to=case.overrides.get("validity_to", date(2024, 12, 31)),  # type: ignore[arg-type]
    )

    with pytest.raises(MasterValidationError) as exc:
        await service.create_mapping(payload, _actor())
    assert exc.value.field == case.field
    # Nothing persisted on a rejected create.
    assert repo.store == {}


# ─── Update-path assertion (From ≤ To re-validation only) ───


async def _assert_update_from_after_to_rejected(
    from_d: date, to_d: date
) -> None:
    service, vendor_id, customer_id = _seeded_service()
    repo: FakeMappingRepository = service._mapping_repo  # type: ignore[assignment]

    seeded = await service.create_mapping(
        MappingCreateInput(
            vendor_id=vendor_id,
            customer_id=customer_id,
            validity_from=date(2024, 1, 1),
            validity_to=date(2024, 12, 31),
        ),
        _actor(),
    )
    before = (seeded.validity_from, seeded.validity_to, seeded.status)

    with pytest.raises(MasterValidationError) as exc:
        await service.update_mapping(
            seeded.id,
            MappingUpdateInput(validity_from=from_d, validity_to=to_d),
            _actor(),
        )
    assert exc.value.field == "validity_from"
    # The stored record is unchanged (no partial mutation persisted).
    stored = repo.store[seeded.id]
    assert (stored.validity_from, stored.validity_to, stored.status) == before


# ─── Properties ───


@settings(max_examples=20)
@given(case=_invalid_cases())
def test_mapping_invalid_requests_rejected(case: InvalidCase) -> None:
    """Invalid create Mapping requests are rejected and persist nothing.

    Each example violates exactly one Property-40 rule: an unknown Vendor or
    Customer (Req 14.2) or Validity From later than Validity To (Req 14.3). The
    service must raise ``MasterValidationError`` identifying the offending field
    and leave the repository unchanged.
    """
    asyncio.run(_assert_create_rejected(case))


@settings(max_examples=20)
@given(dates=_from_after_to_dates())
def test_mapping_update_rejects_from_after_to(dates: tuple[date, date]) -> None:
    """A dates-only update with From later than To is rejected (Req 14.3).

    The From ≤ To rule is re-validated on update; a violating update raises
    ``MasterValidationError`` and leaves the stored Mapping unchanged.
    """
    from_d, to_d = dates
    asyncio.run(_assert_update_from_after_to_rejected(from_d, to_d))


@settings(max_examples=20)
@given(dates=_ordered_dates())
def test_valid_create_defaults_status_active(dates: tuple[date, date]) -> None:
    """A valid create stores the Mapping with Status ``Active`` (Req 14.5).

    For any valid (From ≤ To) request referencing an existing Vendor and
    Customer, the persisted Mapping is stored exactly once with Status
    ``Active``.
    """
    from_d, to_d = dates

    async def _run() -> None:
        service, vendor_id, customer_id = _seeded_service()
        repo: FakeMappingRepository = service._mapping_repo  # type: ignore[assignment]

        mapping = await service.create_mapping(
            MappingCreateInput(
                vendor_id=vendor_id,
                customer_id=customer_id,
                validity_from=from_d,
                validity_to=to_d,
            ),
            _actor(),
        )

        assert mapping.status is MappingStatus.Active
        assert repo.store[mapping.id].status is MappingStatus.Active
        assert len(repo.store) == 1

    asyncio.run(_run())
