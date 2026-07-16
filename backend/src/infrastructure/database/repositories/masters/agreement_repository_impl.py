"""
Agreement repository implementation (Adapter).

Implements :class:`IAgreementRepository` using SQLAlchemy async, including the
inclusive overlap-detection query used to enforce the
no-overlapping-active-agreements rule and the due-for-expiry query used by the
daily expiry job.
"""

from datetime import date
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.domain.entities.masters.agreement import AgreementEntity
from src.domain.enums.masters import AgreementStatus, AgreementType
from src.domain.repositories.masters.agreement_repository import IAgreementRepository
from src.infrastructure.database.models.masters.agreement_model import AgreementModel


class AgreementRepositoryImpl(IAgreementRepository):
    """Concrete implementation of agreement persistence using SQLAlchemy."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get_by_id(self, agreement_id: UUID) -> AgreementEntity | None:
        stmt = select(AgreementModel).where(AgreementModel.id == agreement_id)
        result = await self._session.execute(stmt)
        model = result.scalar_one_or_none()
        return self._to_entity(model) if model else None

    async def create(self, agreement: AgreementEntity) -> AgreementEntity:
        model = AgreementModel(
            id=agreement.id,
            vendor_id=agreement.vendor_id,
            product_master_id=agreement.product_master_id,
            from_date=agreement.from_date,
            to_date=agreement.to_date,
            slab_in_days=agreement.slab_in_days,
            reduction_percent=agreement.reduction_percent,
            max_commission_percent=agreement.max_commission_percent,
            min_commission_percent=agreement.min_commission_percent,
            credit_days=agreement.credit_days,
            agreement_type=str(agreement.agreement_type),
            prior_agreement_id=agreement.prior_agreement_id,
            agreement_document_ref=agreement.agreement_document_ref,
            status=str(agreement.status),
            created_by=agreement.created_by,
            modified_by=agreement.modified_by,
        )
        self._session.add(model)
        await self._session.flush()
        return self._to_entity(model)

    async def update(self, agreement: AgreementEntity) -> AgreementEntity:
        stmt = select(AgreementModel).where(AgreementModel.id == agreement.id)
        result = await self._session.execute(stmt)
        model = result.scalar_one_or_none()
        if model is None:
            raise ValueError(f"Agreement with id {agreement.id} not found")

        model.vendor_id = agreement.vendor_id
        model.product_master_id = agreement.product_master_id
        model.from_date = agreement.from_date
        model.to_date = agreement.to_date
        model.slab_in_days = agreement.slab_in_days
        model.reduction_percent = agreement.reduction_percent
        model.max_commission_percent = agreement.max_commission_percent
        model.min_commission_percent = agreement.min_commission_percent
        model.credit_days = agreement.credit_days
        model.agreement_type = str(agreement.agreement_type)
        model.prior_agreement_id = agreement.prior_agreement_id
        model.agreement_document_ref = agreement.agreement_document_ref
        model.status = str(agreement.status)
        model.modified_by = agreement.modified_by
        model.modified_date = agreement.modified_date

        await self._session.flush()
        return self._to_entity(model)

    async def delete(self, agreement_id: UUID) -> None:
        stmt = select(AgreementModel).where(AgreementModel.id == agreement_id)
        result = await self._session.execute(stmt)
        model = result.scalar_one_or_none()
        if model:
            await self._session.delete(model)
            await self._session.flush()

    async def list_all(
        self, skip: int = 0, limit: int = 20, vendor_id: UUID | None = None
    ) -> list[AgreementEntity]:
        stmt = select(AgreementModel)
        if vendor_id is not None:
            stmt = stmt.where(AgreementModel.vendor_id == vendor_id)
        stmt = (
            stmt.order_by(AgreementModel.created_date, AgreementModel.id)
            .offset(skip)
            .limit(limit)
        )
        result = await self._session.execute(stmt)
        models = result.scalars().all()
        return [self._to_entity(m) for m in models]

    async def list_with_names(
        self, skip: int = 0, limit: int = 20, vendor_id: UUID | None = None
    ) -> list[tuple[AgreementEntity, str | None, str | None, str | None]]:
        """Return agreements with denormalized vendor_name, product child_code, and product name.

        Each tuple is ``(entity, vendor_name, child_code, product_name)``.
        """
        from src.infrastructure.database.models.masters.vendor_model import VendorModel
        from src.infrastructure.database.models.masters.product_model import ProductMasterModel

        stmt = (
            select(
                AgreementModel,
                VendorModel.vendor_name.label("vendor_name"),
                ProductMasterModel.child_code.label("child_code"),
                ProductMasterModel.product_name.label("product_name"),
            )
            .outerjoin(VendorModel, AgreementModel.vendor_id == VendorModel.id)
            .outerjoin(ProductMasterModel, AgreementModel.product_master_id == ProductMasterModel.id)
        )
        if vendor_id is not None:
            stmt = stmt.where(AgreementModel.vendor_id == vendor_id)
        stmt = stmt.order_by(AgreementModel.created_date, AgreementModel.id).offset(skip).limit(limit)
        result = await self._session.execute(stmt)
        rows = result.all()
        return [(self._to_entity(row[0]), row[1], row[2], row[3]) for row in rows]

    async def count_all(self, vendor_id: UUID | None = None) -> int:
        stmt = select(func.count()).select_from(AgreementModel)
        if vendor_id is not None:
            stmt = stmt.where(AgreementModel.vendor_id == vendor_id)
        result = await self._session.execute(stmt)
        return int(result.scalar_one())

    async def find_overlapping_active(
        self,
        vendor_id: UUID,
        product_master_id: UUID,
        from_date: date,
        to_date: date,
        exclude_id: UUID | None = None,
    ) -> list[AgreementEntity]:
        # Two periods [a.from, a.to] and [b.from, b.to] overlap (inclusive of
        # both endpoints) when a.from_date <= b.to_date AND b.from_date <= a.to_date.
        stmt = select(AgreementModel).where(
            AgreementModel.vendor_id == vendor_id,
            AgreementModel.product_master_id == product_master_id,
            AgreementModel.status == AgreementStatus.Active.value,
            AgreementModel.from_date <= to_date,
            from_date <= AgreementModel.to_date,
        )
        if exclude_id is not None:
            stmt = stmt.where(AgreementModel.id != exclude_id)
        result = await self._session.execute(stmt)
        models = result.scalars().all()
        return [self._to_entity(m) for m in models]

    async def list_due_for_expiry(self, today: date) -> list[AgreementEntity]:
        stmt = select(AgreementModel).where(
            AgreementModel.status == AgreementStatus.Active.value,
            AgreementModel.to_date < today,
        )
        result = await self._session.execute(stmt)
        models = result.scalars().all()
        return [self._to_entity(m) for m in models]

    async def exists_expired_for_vendor_and_detail(
        self, vendor_id: UUID, product_master_id: UUID, on_date: date
    ) -> bool:
        # Any agreement (regardless of status) for the vendor + product detail
        # whose To Date is strictly before ``on_date`` indicates the invoice
        # date falls after an agreement's validity (Req 13.5 — expired).
        stmt = (
            select(func.count())
            .select_from(AgreementModel)
            .where(
                AgreementModel.vendor_id == vendor_id,
                AgreementModel.product_master_id == product_master_id,
                AgreementModel.to_date < on_date,
            )
        )
        result = await self._session.execute(stmt)
        return int(result.scalar_one()) > 0

    @staticmethod
    def _to_entity(model: AgreementModel) -> AgreementEntity:
        """Map ORM model to domain entity."""
        return AgreementEntity(
            id=model.id,
            vendor_id=model.vendor_id,
            product_master_id=model.product_master_id,
            from_date=model.from_date,
            to_date=model.to_date,
            slab_in_days=model.slab_in_days,
            reduction_percent=model.reduction_percent,
            max_commission_percent=model.max_commission_percent,
            min_commission_percent=model.min_commission_percent,
            credit_days=model.credit_days,
            agreement_type=AgreementType(model.agreement_type),
            prior_agreement_id=model.prior_agreement_id,
            agreement_document_ref=model.agreement_document_ref,
            status=AgreementStatus(model.status),
            created_by=model.created_by,
            created_date=model.created_date,
            modified_by=model.modified_by,
            modified_date=model.modified_date,
        )
