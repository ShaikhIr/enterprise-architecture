"""
Unit tests for :class:`AgreementService` (Agreement Master CRUD, overlap,
renewal, vendor-scoped listing, expiry, and commission computation).

These tests exercise the service's business rules in isolation using in-memory
fake repositories that implement the agreement, vendor, and product repository
ports, so no database is required. They cover the requirements assigned to task
10.2 (Requirements 11.2–11.11, 13.1–13.3, 13.6, 20.4) plus the Req 12 commission
delegation.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from uuid import UUID, uuid4

import pytest

from src.application.exceptions.application_exceptions import (
    MasterConflictError,
    MasterNotFoundError,
    MasterValidationError,
)
from src.application.services.masters.agreement_service import (
    AgreementCreateInput,
    AgreementDocumentInput,
    AgreementRenewalInput,
    AgreementService,
    AgreementUpdateInput,
)
from src.domain.entities.masters.agreement import AgreementEntity
from src.domain.entities.user import User
from src.domain.enums.masters import AgreementStatus, AgreementType
from src.domain.repositories.masters.agreement_repository import IAgreementRepository


class FakeAgreementRepository(IAgreementRepository):
    """In-memory implementation of the agreement repository port."""

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
        # Emulate ON DELETE SET NULL for referencing renewals (Req 13.3).
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

    async def list_with_names(
        self, skip: int = 0, limit: int = 20, vendor_id: UUID | None = None
    ) -> list:
        """Return (entity, vendor_name, child_code, product_name) tuples."""
        items = [
            a for a in self.store.values()
            if vendor_id is None or a.vendor_id == vendor_id
        ]
        return [(a, None, None, None) for a in items[skip: skip + limit]]

    async def count_filtered(self, vendor_id: UUID | None = None, **kwargs) -> int:
        return len(
            [a for a in self.store.values()
             if vendor_id is None or a.vendor_id == vendor_id]
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
    """Minimal vendor lookup fake (only the methods the service uses)."""

    def __init__(self) -> None:
        self.ids: set[UUID] = set()

    def add(self, vendor_id: UUID) -> None:
        self.ids.add(vendor_id)

    async def get_by_id(self, vendor_id: UUID):
        return object() if vendor_id in self.ids else None


class FakeProductRepository:
    """Minimal product-detail lookup fake (only the methods the service uses)."""

    def __init__(self) -> None:
        self.detail_ids: set[UUID] = set()

    def add_detail(self, detail_id: UUID) -> None:
        self.detail_ids.add(detail_id)

    async def get_by_id(self, detail_id: UUID):
        return object() if detail_id in self.detail_ids else None

    # Legacy alias kept for compatibility
    async def get_detail_by_id(self, detail_id: UUID):
        return await self.get_by_id(detail_id)


@pytest.fixture
def actor() -> User:
    return User(id=uuid4(), username="tester", is_active=True)


@pytest.fixture
def agreement_repo() -> FakeAgreementRepository:
    return FakeAgreementRepository()


@pytest.fixture
def vendor_repo() -> FakeVendorRepository:
    return FakeVendorRepository()


@pytest.fixture
def product_repo() -> FakeProductRepository:
    return FakeProductRepository()


@pytest.fixture
def vendor_id(vendor_repo: FakeVendorRepository) -> UUID:
    vid = uuid4()
    vendor_repo.add(vid)
    return vid


@pytest.fixture
def detail_id(product_repo: FakeProductRepository) -> UUID:
    did = uuid4()
    product_repo.add_detail(did)
    return did


@pytest.fixture
def service(
    agreement_repo: FakeAgreementRepository,
    vendor_repo: FakeVendorRepository,
    product_repo: FakeProductRepository,
) -> AgreementService:
    return AgreementService(
        session=None,  # type: ignore[arg-type]
        agreement_repo=agreement_repo,
        vendor_repo=vendor_repo,  # type: ignore[arg-type]
        product_repo=product_repo,  # type: ignore[arg-type]
    )


def _create_input(vendor_id: UUID, detail_id: UUID, **overrides) -> AgreementCreateInput:
    defaults = dict(
        vendor_id=vendor_id,
        product_master_id=detail_id,
        from_date=date(2024, 1, 1),
        to_date=date(2024, 12, 31),
        slab_in_days=30,
        reduction_percent=Decimal("5"),
        max_commission_percent=Decimal("10"),
        min_commission_percent=Decimal("2"),
        credit_days=45,
    )
    defaults.update(overrides)
    return AgreementCreateInput(**defaults)  # type: ignore[arg-type]


class TestCreateDefaultsAndValidation:
    async def test_create_applies_original_active_defaults(
        self, service, actor, vendor_id, detail_id
    ):
        agreement = await service.create_agreement(
            _create_input(vendor_id, detail_id), actor
        )
        assert agreement.agreement_type == AgreementType.Original
        assert agreement.status == AgreementStatus.Active
        assert agreement.created_by == "tester"

    async def test_create_rejects_unknown_vendor(self, service, actor, detail_id):
        with pytest.raises(MasterValidationError) as exc:
            await service.create_agreement(
                _create_input(uuid4(), detail_id), actor
            )
        assert exc.value.field == "vendor_id"

    async def test_create_rejects_unknown_product_detail(
        self, service, actor, vendor_id
    ):
        with pytest.raises(MasterValidationError) as exc:
            await service.create_agreement(
                _create_input(vendor_id, uuid4()), actor
            )
        assert exc.value.field == "product_master_id"

    async def test_create_rejects_from_after_to(
        self, service, actor, vendor_id, detail_id
    ):
        with pytest.raises(MasterValidationError) as exc:
            await service.create_agreement(
                _create_input(
                    vendor_id,
                    detail_id,
                    from_date=date(2024, 12, 31),
                    to_date=date(2024, 1, 1),
                ),
                actor,
            )
        assert exc.value.field == "from_date"

    async def test_create_rejects_min_greater_than_max(
        self, service, actor, vendor_id, detail_id
    ):
        with pytest.raises(MasterValidationError) as exc:
            await service.create_agreement(
                _create_input(
                    vendor_id,
                    detail_id,
                    min_commission_percent=Decimal("20"),
                    max_commission_percent=Decimal("10"),
                ),
                actor,
            )
        assert exc.value.field == "min_commission_percent"

    @pytest.mark.parametrize(
        "field,value",
        [
            ("reduction_percent", Decimal("-1")),
            ("reduction_percent", Decimal("100.01")),
            ("max_commission_percent", Decimal("101")),
            ("min_commission_percent", Decimal("-0.01")),
        ],
    )
    async def test_create_rejects_out_of_range_percent(
        self, service, actor, vendor_id, detail_id, field, value
    ):
        with pytest.raises(MasterValidationError) as exc:
            await service.create_agreement(
                _create_input(vendor_id, detail_id, **{field: value}), actor
            )
        assert exc.value.field == field

    @pytest.mark.parametrize("slab", [0, -5])
    async def test_create_rejects_non_positive_slab(
        self, service, actor, vendor_id, detail_id, slab
    ):
        with pytest.raises(MasterValidationError) as exc:
            await service.create_agreement(
                _create_input(vendor_id, detail_id, slab_in_days=slab), actor
            )
        assert exc.value.field == "slab_in_days"

    async def test_create_rejects_negative_credit_days(
        self, service, actor, vendor_id, detail_id
    ):
        with pytest.raises(MasterValidationError) as exc:
            await service.create_agreement(
                _create_input(vendor_id, detail_id, credit_days=-1), actor
            )
        assert exc.value.field == "credit_days"

    async def test_create_rejects_bad_document_type(
        self, service, actor, vendor_id, detail_id
    ):
        doc = AgreementDocumentInput(content_type="text/plain", size_bytes=100)
        with pytest.raises(MasterValidationError) as exc:
            await service.create_agreement(
                _create_input(vendor_id, detail_id, document=doc), actor
            )
        assert exc.value.field == "document"

    async def test_create_rejects_oversized_document(
        self, service, actor, vendor_id, detail_id
    ):
        doc = AgreementDocumentInput(
            content_type="application/pdf", size_bytes=10 * 1024 * 1024 + 1
        )
        with pytest.raises(MasterValidationError) as exc:
            await service.create_agreement(
                _create_input(vendor_id, detail_id, document=doc), actor
            )
        assert exc.value.field == "document"

    async def test_create_accepts_valid_document(
        self, service, actor, vendor_id, detail_id
    ):
        doc = AgreementDocumentInput(
            content_type="image/png", size_bytes=2048, storage_ref="s3://docs/a.png"
        )
        agreement = await service.create_agreement(
            _create_input(vendor_id, detail_id, document=doc), actor
        )
        assert agreement.agreement_document_ref == "s3://docs/a.png"


class TestOverlap:
    async def test_overlapping_active_rejected(
        self, service, actor, vendor_id, detail_id
    ):
        await service.create_agreement(_create_input(vendor_id, detail_id), actor)
        with pytest.raises(MasterConflictError):
            await service.create_agreement(
                _create_input(
                    vendor_id,
                    detail_id,
                    from_date=date(2024, 6, 1),
                    to_date=date(2025, 1, 31),
                ),
                actor,
            )

    async def test_inclusive_boundary_overlap_rejected(
        self, service, actor, vendor_id, detail_id
    ):
        await service.create_agreement(
            _create_input(
                vendor_id,
                detail_id,
                from_date=date(2024, 1, 1),
                to_date=date(2024, 6, 30),
            ),
            actor,
        )
        # New period starts exactly on the prior period's To Date -> overlaps.
        with pytest.raises(MasterConflictError):
            await service.create_agreement(
                _create_input(
                    vendor_id,
                    detail_id,
                    from_date=date(2024, 6, 30),
                    to_date=date(2024, 12, 31),
                ),
                actor,
            )

    async def test_adjacent_non_overlapping_allowed(
        self, service, actor, vendor_id, detail_id
    ):
        await service.create_agreement(
            _create_input(
                vendor_id,
                detail_id,
                from_date=date(2024, 1, 1),
                to_date=date(2024, 6, 30),
            ),
            actor,
        )
        # Starts the day after the prior To Date -> no overlap.
        second = await service.create_agreement(
            _create_input(
                vendor_id,
                detail_id,
                from_date=date(2024, 7, 1),
                to_date=date(2024, 12, 31),
            ),
            actor,
        )
        assert second.status == AgreementStatus.Active


class TestReadUpdateDelete:
    async def test_get_unknown_raises_not_found(self, service):
        with pytest.raises(MasterNotFoundError):
            await service.get_agreement(uuid4())

    async def test_update_is_partial(self, service, actor, vendor_id, detail_id):
        agreement = await service.create_agreement(
            _create_input(vendor_id, detail_id), actor
        )
        updated = await service.update_agreement(
            agreement.id,
            AgreementUpdateInput(max_commission_percent=Decimal("15")),
            actor,
        )
        assert updated.max_commission_percent == Decimal("15")
        assert updated.from_date == agreement.from_date

    async def test_update_unknown_raises_not_found(self, service, actor):
        with pytest.raises(MasterNotFoundError):
            await service.update_agreement(
                uuid4(), AgreementUpdateInput(credit_days=10), actor
            )

    async def test_delete_unknown_raises_not_found(self, service, actor):
        with pytest.raises(MasterNotFoundError):
            await service.delete_agreement(uuid4(), actor)

    async def test_delete_nulls_renewal_prior_ref(
        self, service, actor, vendor_id, detail_id
    ):
        prior = await service.create_agreement(
            _create_input(
                vendor_id,
                detail_id,
                from_date=date(2024, 1, 1),
                to_date=date(2024, 6, 30),
            ),
            actor,
        )
        renewal = await service.renew_agreement(
            prior.id,
            AgreementRenewalInput(
                from_date=date(2024, 7, 1),
                to_date=date(2024, 12, 31),
                slab_in_days=30,
                reduction_percent=Decimal("5"),
                max_commission_percent=Decimal("10"),
                min_commission_percent=Decimal("2"),
                credit_days=45,
            ),
            actor,
        )
        assert renewal.prior_agreement_id == prior.id
        await service.delete_agreement(prior.id, actor)
        refreshed = await service.get_agreement(renewal.id)
        assert refreshed.prior_agreement_id is None


class TestRenewal:
    async def test_renewal_marks_prior_and_links(
        self, service, actor, vendor_id, detail_id
    ):
        prior = await service.create_agreement(
            _create_input(
                vendor_id,
                detail_id,
                from_date=date(2024, 1, 1),
                to_date=date(2024, 6, 30),
            ),
            actor,
        )
        renewal = await service.renew_agreement(
            prior.id,
            AgreementRenewalInput(
                from_date=date(2024, 7, 1),
                to_date=date(2024, 12, 31),
                slab_in_days=30,
                reduction_percent=Decimal("5"),
                max_commission_percent=Decimal("10"),
                min_commission_percent=Decimal("2"),
                credit_days=45,
            ),
            actor,
        )
        prior_after = await service.get_agreement(prior.id)
        assert prior_after.status == AgreementStatus.Renewed
        assert renewal.agreement_type == AgreementType.Renewal
        assert renewal.prior_agreement_id == prior.id
        # Inherits vendor/detail from the prior agreement.
        assert renewal.vendor_id == vendor_id
        assert renewal.product_master_id == detail_id

    async def test_renew_unknown_raises_not_found(self, service, actor):
        with pytest.raises(MasterNotFoundError):
            await service.renew_agreement(
                uuid4(),
                AgreementRenewalInput(
                    from_date=date(2024, 7, 1), to_date=date(2024, 12, 31)
                ),
                actor,
            )


class TestVendorScopedListing:
    async def test_list_filters_by_vendor(
        self, service, actor, vendor_repo, product_repo
    ):
        v1, v2 = uuid4(), uuid4()
        vendor_repo.add(v1)
        vendor_repo.add(v2)
        d = uuid4()
        product_repo.add_detail(d)
        await service.create_agreement(_create_input(v1, d), actor)
        await service.create_agreement(_create_input(v2, d), actor)
        items, total = await service.list_agreements(vendor_id=v1)
        assert total == 1
        # list_agreements returns (entity, vendor_name, child_code, product_name) tuples
        assert all(a[0].vendor_id == v1 for a in items)

    async def test_list_without_filter_returns_all(
        self, service, actor, vendor_repo, product_repo
    ):
        v1, v2 = uuid4(), uuid4()
        vendor_repo.add(v1)
        vendor_repo.add(v2)
        d = uuid4()
        product_repo.add_detail(d)
        await service.create_agreement(_create_input(v1, d), actor)
        await service.create_agreement(_create_input(v2, d), actor)
        _, total = await service.list_agreements()
        assert total == 2


class TestExpiryAndCommission:
    async def test_expire_due_agreements(self, service, actor, vendor_id, detail_id):
        await service.create_agreement(
            _create_input(
                vendor_id,
                detail_id,
                from_date=date(2023, 1, 1),
                to_date=date(2023, 12, 31),
            ),
            actor,
        )
        expired = await service.expire_due_agreements(date(2024, 6, 1))
        assert expired == 1

    async def test_expire_leaves_future_agreements_active(
        self, service, actor, vendor_id, detail_id
    ):
        agreement = await service.create_agreement(
            _create_input(
                vendor_id,
                detail_id,
                from_date=date(2024, 1, 1),
                to_date=date(2099, 12, 31),
            ),
            actor,
        )
        expired = await service.expire_due_agreements(date(2024, 6, 1))
        assert expired == 0
        assert (
            await service.get_agreement(agreement.id)
        ).status == AgreementStatus.Active

    async def test_compute_applicable_commission_no_delay(
        self, service, actor, vendor_id, detail_id
    ):
        agreement = await service.create_agreement(
            _create_input(vendor_id, detail_id), actor
        )
        # Payment cleared on the due date -> full max commission (Req 12.1).
        result = service.compute_applicable_commission(
            agreement, date(2024, 3, 1), date(2024, 3, 1)
        )
        assert result == Decimal("10")

    async def test_compute_applicable_commission_with_delay(
        self, service, actor, vendor_id, detail_id
    ):
        agreement = await service.create_agreement(
            _create_input(vendor_id, detail_id), actor
        )
        # 31 days delay, slab 30 -> ceil(31/30)=2 buckets, 10 - 2*5 = 0,
        # floored at min 2 (Req 12.2).
        result = service.compute_applicable_commission(
            agreement, date(2024, 3, 1), date(2024, 4, 1)
        )
        assert result == Decimal("2")
