"""
Vendor-Customer Mapping repository implementation (Adapter).
Implements ``IMappingRepository`` using SQLAlchemy async.
"""

from datetime import date
from uuid import UUID

from sqlalchemy import Select, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.domain.entities.masters.mapping import MappingEntity
from src.domain.enums.masters import MappingStatus
from src.domain.repositories.masters.mapping_repository import IMappingRepository
from src.infrastructure.database.models.masters.mapping_model import MappingModel


class MappingRepositoryImpl(IMappingRepository):
    """Concrete implementation of mapping persistence using SQLAlchemy."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get_by_id(self, mapping_id: UUID) -> MappingEntity | None:
        stmt = select(MappingModel).where(MappingModel.id == mapping_id)
        result = await self._session.execute(stmt)
        model = result.scalar_one_or_none()
        return self._to_entity(model) if model else None

    async def create(self, mapping: MappingEntity) -> MappingEntity:
        model = MappingModel(
            id=mapping.id,
            vendor_id=mapping.vendor_id,
            customer_id=mapping.customer_id,
            validity_from=mapping.validity_from,
            validity_to=mapping.validity_to,
            status=mapping.status.value,
            created_by=mapping.created_by,
            modified_by=mapping.modified_by,
        )
        self._session.add(model)
        await self._session.flush()
        return self._to_entity(model)

    async def update(self, mapping: MappingEntity) -> MappingEntity:
        stmt = select(MappingModel).where(MappingModel.id == mapping.id)
        result = await self._session.execute(stmt)
        model = result.scalar_one_or_none()
        if model is None:
            raise ValueError(f"Mapping with id {mapping.id} not found")

        model.vendor_id = mapping.vendor_id
        model.customer_id = mapping.customer_id
        model.validity_from = mapping.validity_from
        model.validity_to = mapping.validity_to
        model.status = mapping.status.value
        model.modified_by = mapping.modified_by
        model.modified_date = mapping.modified_date

        await self._session.flush()
        return self._to_entity(model)

    async def delete(self, mapping_id: UUID) -> None:
        stmt = select(MappingModel).where(MappingModel.id == mapping_id)
        result = await self._session.execute(stmt)
        model = result.scalar_one_or_none()
        if model:
            await self._session.delete(model)
            await self._session.flush()

    async def list_mappings(
        self,
        skip: int = 0,
        limit: int = 20,
        vendor_id: UUID | None = None,
        customer_id: UUID | None = None,
    ) -> list[MappingEntity]:
        stmt = self._apply_filters(
            select(MappingModel), vendor_id, customer_id
        )
        stmt = stmt.order_by(MappingModel.created_date).offset(skip).limit(limit)
        result = await self._session.execute(stmt)
        models = result.scalars().all()
        return [self._to_entity(m) for m in models]

    async def list_mappings_with_names(
        self,
        skip: int = 0,
        limit: int = 20,
        vendor_id: UUID | None = None,
        customer_id: UUID | None = None,
    ) -> list[tuple[MappingEntity, str | None, str | None]]:
        """Return mappings with denormalized vendor_name and customer_name.

        Each tuple is ``(entity, vendor_name, customer_name)``.
        """
        from src.infrastructure.database.models.masters.vendor_model import VendorModel
        from src.infrastructure.database.models.masters.customer_model import CustomerModel

        stmt = (
            select(
                MappingModel,
                VendorModel.vendor_name.label("vendor_name"),
                CustomerModel.customer_name.label("customer_name"),
            )
            .outerjoin(VendorModel, MappingModel.vendor_id == VendorModel.id)
            .outerjoin(CustomerModel, MappingModel.customer_id == CustomerModel.id)
        )
        if vendor_id is not None:
            stmt = stmt.where(MappingModel.vendor_id == vendor_id)
        if customer_id is not None:
            stmt = stmt.where(MappingModel.customer_id == customer_id)
        stmt = stmt.order_by(MappingModel.created_date).offset(skip).limit(limit)
        result = await self._session.execute(stmt)
        rows = result.all()
        return [(self._to_entity(row[0]), row[1], row[2]) for row in rows]

    async def count(
        self,
        vendor_id: UUID | None = None,
        customer_id: UUID | None = None,
    ) -> int:
        stmt = self._apply_filters(
            select(func.count()).select_from(MappingModel),
            vendor_id,
            customer_id,
        )
        result = await self._session.execute(stmt)
        return int(result.scalar_one())

    async def find_overlapping_active(
        self,
        vendor_id: UUID,
        customer_id: UUID,
        validity_from: date,
        validity_to: date,
        exclude_id: UUID | None = None,
    ) -> list[MappingEntity]:
        stmt = select(MappingModel).where(
            MappingModel.vendor_id == vendor_id,
            MappingModel.customer_id == customer_id,
            MappingModel.status == MappingStatus.Active.value,
            MappingModel.validity_from <= validity_to,
            validity_from <= MappingModel.validity_to,
        )
        if exclude_id is not None:
            stmt = stmt.where(MappingModel.id != exclude_id)
        result = await self._session.execute(stmt)
        models = result.scalars().all()
        return [self._to_entity(m) for m in models]

    async def list_active_due_for_expiry(
        self, today: date
    ) -> list[MappingEntity]:
        stmt = select(MappingModel).where(
            MappingModel.status == MappingStatus.Active.value,
            MappingModel.validity_to < today,
        )
        result = await self._session.execute(stmt)
        models = result.scalars().all()
        return [self._to_entity(m) for m in models]

    @staticmethod
    def _apply_filters(
        stmt: Select,
        vendor_id: UUID | None,
        customer_id: UUID | None,
    ) -> Select:
        """Apply the optional vendor/customer combined filter to a statement."""
        if vendor_id is not None:
            stmt = stmt.where(MappingModel.vendor_id == vendor_id)
        if customer_id is not None:
            stmt = stmt.where(MappingModel.customer_id == customer_id)
        return stmt

    @staticmethod
    def _to_entity(model: MappingModel) -> MappingEntity:
        """Map ORM model to domain entity."""
        return MappingEntity(
            id=model.id,
            vendor_id=model.vendor_id,
            customer_id=model.customer_id,
            validity_from=model.validity_from,
            validity_to=model.validity_to,
            status=MappingStatus(model.status),
            created_by=model.created_by,
            created_date=model.created_date,
            modified_by=model.modified_by,
            modified_date=model.modified_date,
        )
