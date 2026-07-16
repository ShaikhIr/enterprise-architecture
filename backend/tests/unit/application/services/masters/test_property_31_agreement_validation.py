# Feature: lacm-masters, Property 31: Agreement field validation.
"""Property-based test for Agreement create/update field validation.

Property 31: Agreement field validation.

**Validates: Requirements 11.2, 11.3, 11.4, 11.5, 11.6, 11.9**

*For any* create- or update-Agreement request, the request is rejected with no
persist/modify when:

* the referenced Vendor is missing or does not exist (Req 11.2),
* the referenced Product Detail is missing or does not exist (Req 11.2),
* From Date is later than To Date (Req 11.3),
* Min Commission % exceeds Max Commission % (Req 11.4),
* Reduction %, Max %, or Min % is outside the 0-100 inclusive range (Req 11.5),
* Slab in Days is not greater than 0, or Credit Days is below 0 (Req 11.6),
* the Agreement Document is not PDF/JPEG/PNG, or exceeds 10 MB (Req 11.9).

The service is exercised against real in-memory implementations of the
agreement/vendor/product repository ports (fakes, not mocks), so the property
validates actual service logic end-to-end through the ports. Each Hypothesis
example drives the async service via ``asyncio.run`` so examples stay isolated.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field, replace
from datetime import date
from decimal import Decimal
from uuid import UUID, uuid4

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from src.application.exceptions.application_exceptions import MasterValidationError
from src.application.services.masters.agreement_service import (
    AgreementCreateInput,
    AgreementDocumentInput,
    AgreementService,
    AgreementUpdateInput,
)
from src.domain.entities.masters.agreement import AgreementEntity
from src.domain.entities.user import User
from src.domain.enums.masters import AgreementStatus
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
    ) -> bool:
        return any(
            a.vendor_id == vendor_id
            and a.product_master_id == product_master_id
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


# Seeded baseline dates used by the valid template.
_FROM = date(2024, 1, 1)
_TO = date(2024, 12, 31)


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


def _valid_overrides(vendor_id: UUID, detail_id: UUID) -> dict[str, object]:
    """A fully valid create payload as a kwargs dict."""
    return dict(
        vendor_id=vendor_id,
        product_master_id=detail_id,
        from_date=_FROM,
        to_date=_TO,
        slab_in_days=30,
        reduction_percent=Decimal("5"),
        max_commission_percent=Decimal("10"),
        min_commission_percent=Decimal("2"),
        credit_days=45,
    )


# ─── Strategies for invalid values ───

_out_of_range_percent = st.one_of(
    st.decimals(
        min_value=Decimal("-100000"),
        max_value=Decimal("-0.01"),
        allow_nan=False,
        allow_infinity=False,
        places=2,
    ),
    st.decimals(
        min_value=Decimal("100.01"),
        max_value=Decimal("100000"),
        allow_nan=False,
        allow_infinity=False,
        places=2,
    ),
)

_nonpositive_slab = st.integers(min_value=-10000, max_value=0)
_negative_credit = st.integers(min_value=-10000, max_value=-1)

_bad_doc_type = st.sampled_from(
    ["text/plain", "application/zip", "application/octet-stream", "image/gif", ""]
)


@dataclass
class InvalidCase:
    """A single invalid-request scenario with exactly one violated rule."""

    rule: str
    field: str
    # Overrides applied on top of the valid template (create path).
    overrides: dict[str, object] = field(default_factory=dict)


@st.composite
def _invalid_cases(draw: st.DrawFn) -> InvalidCase:
    rule = draw(
        st.sampled_from(
            [
                "missing_vendor",
                "nonexistent_vendor",
                "missing_detail",
                "nonexistent_detail",
                "from_after_to",
                "min_gt_max",
                "reduction_oor",
                "max_oor",
                "min_oor",
                "slab_nonpositive",
                "credit_negative",
                "bad_doc_type",
                "oversized_doc",
            ]
        )
    )

    if rule == "missing_vendor":
        return InvalidCase(rule, "vendor_id", {"vendor_id": None})
    if rule == "nonexistent_vendor":
        return InvalidCase(rule, "vendor_id", {"vendor_id": uuid4()})
    if rule == "missing_detail":
        return InvalidCase(rule, "product_master_id", {"product_master_id": None})
    if rule == "nonexistent_detail":
        return InvalidCase(rule, "product_master_id", {"product_master_id": uuid4()})
    if rule == "from_after_to":
        # Draw a strictly-decreasing (from > to) pair.
        to_d = draw(st.dates(min_value=date(2000, 1, 2), max_value=date(2099, 12, 30)))
        from_d = draw(
            st.dates(min_value=date(2000, 1, 3), max_value=date(2100, 1, 1)).filter(
                lambda d: d > to_d
            )
        )
        return InvalidCase(rule, "from_date", {"from_date": from_d, "to_date": to_d})
    if rule == "min_gt_max":
        max_v = draw(
            st.decimals(
                min_value=Decimal("0"),
                max_value=Decimal("99"),
                allow_nan=False,
                allow_infinity=False,
                places=2,
            )
        )
        min_v = draw(
            st.decimals(
                min_value=Decimal("0"),
                max_value=Decimal("100"),
                allow_nan=False,
                allow_infinity=False,
                places=2,
            ).filter(lambda d: d > max_v)
        )
        return InvalidCase(
            rule,
            "min_commission_percent",
            {"max_commission_percent": max_v, "min_commission_percent": min_v},
        )
    if rule == "reduction_oor":
        return InvalidCase(
            rule, "reduction_percent", {"reduction_percent": draw(_out_of_range_percent)}
        )
    if rule == "max_oor":
        return InvalidCase(
            rule,
            "max_commission_percent",
            {"max_commission_percent": draw(_out_of_range_percent)},
        )
    if rule == "min_oor":
        return InvalidCase(
            rule,
            "min_commission_percent",
            {"min_commission_percent": draw(_out_of_range_percent)},
        )
    if rule == "slab_nonpositive":
        return InvalidCase(
            rule, "slab_in_days", {"slab_in_days": draw(_nonpositive_slab)}
        )
    if rule == "credit_negative":
        return InvalidCase(
            rule, "credit_days", {"credit_days": draw(_negative_credit)}
        )
    if rule == "bad_doc_type":
        doc = AgreementDocumentInput(
            content_type=draw(_bad_doc_type), size_bytes=1024
        )
        return InvalidCase(rule, "document", {"document": doc})
    # oversized_doc
    oversize = draw(st.integers(min_value=10 * 1024 * 1024 + 1, max_value=50 * 1024 * 1024))
    doc = AgreementDocumentInput(content_type="application/pdf", size_bytes=oversize)
    return InvalidCase(rule, "document", {"document": doc})


# ─── Create-path assertion ───


async def _assert_create_rejected(case: InvalidCase) -> None:
    service, vendor_id, detail_id = _seeded_service()
    repo: FakeAgreementRepository = service._agreement_repo  # type: ignore[assignment]

    overrides = _valid_overrides(vendor_id, detail_id)
    overrides.update(case.overrides)
    payload = AgreementCreateInput(**overrides)  # type: ignore[arg-type]

    with pytest.raises(MasterValidationError) as exc:
        await service.create_agreement(payload, _actor())
    assert exc.value.field == case.field
    # Nothing persisted on a rejected create.
    assert repo.store == {}


# ─── Update-path assertion ───


async def _seed_valid_agreement(
    service: AgreementService, vendor_id: UUID, detail_id: UUID
) -> AgreementEntity:
    return await service.create_agreement(
        AgreementCreateInput(**_valid_overrides(vendor_id, detail_id)),  # type: ignore[arg-type]
        _actor(),
    )


async def _assert_update_rejected(case: InvalidCase) -> None:
    service, vendor_id, detail_id = _seeded_service()
    repo: FakeAgreementRepository = service._agreement_repo  # type: ignore[assignment]

    seeded = await _seed_valid_agreement(service, vendor_id, detail_id)
    before = replace(seeded)  # snapshot copy

    patch = AgreementUpdateInput(**case.overrides)  # type: ignore[arg-type]
    with pytest.raises(MasterValidationError) as exc:
        await service.update_agreement(seeded.id, patch, _actor())
    assert exc.value.field == case.field
    # The stored record is unchanged (no partial mutation persisted).
    stored = repo.store[seeded.id]
    assert stored.vendor_id == before.vendor_id
    assert stored.product_master_id == before.product_master_id
    assert stored.from_date == before.from_date
    assert stored.to_date == before.to_date
    assert stored.slab_in_days == before.slab_in_days
    assert stored.reduction_percent == before.reduction_percent
    assert stored.max_commission_percent == before.max_commission_percent
    assert stored.min_commission_percent == before.min_commission_percent
    assert stored.credit_days == before.credit_days
    assert stored.agreement_document_ref == before.agreement_document_ref


@settings(max_examples=20)
@given(case=_invalid_cases())
def test_agreement_invalid_requests_rejected(case: InvalidCase) -> None:
    """Invalid create/update Agreement requests are rejected and persist nothing.

    Each example violates exactly one Property-31 rule (Req 11.2, 11.3, 11.4,
    11.5, 11.6, 11.9). On both the create and partial-update paths the service
    must raise ``MasterValidationError`` identifying the offending field and
    leave the repository unchanged.
    """
    asyncio.run(_assert_create_rejected(case))
    asyncio.run(_assert_update_rejected(case))
