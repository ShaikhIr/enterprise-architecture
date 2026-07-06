"""
Vendor repository implementation (Adapter).
Implements the IVendorRepository using SQLAlchemy async.
"""

from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.domain.entities.masters.vendor import VendorEntity
from src.domain.enums.masters import VendorStatus
from src.domain.repositories.masters.vendor_repository import IVendorRepository
from src.infrastructure.database.models.masters.vendor_model import VendorModel


class VendorRepositoryImpl(IVendorRepository):
    """Concrete implementation of vendor persistence using SQLAlchemy."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get_by_id(self, vendor_id: UUID) -> VendorEntity | None:
        stmt = select(VendorModel).where(VendorModel.id == vendor_id)
        result = await self._session.execute(stmt)
        model = result.scalar_one_or_none()
        return self._to_entity(model) if model else None

    async def get_by_code(self, vendor_code: str) -> VendorEntity | None:
        stmt = select(VendorModel).where(
            func.lower(VendorModel.vendor_code) == vendor_code.strip().lower()
        )
        result = await self._session.execute(stmt)
        model = result.scalar_one_or_none()
        return self._to_entity(model) if model else None

    async def get_by_email(self, vendor_email: str) -> VendorEntity | None:
        stmt = select(VendorModel).where(
            func.lower(VendorModel.vendor_email) == vendor_email.strip().lower()
        )
        result = await self._session.execute(stmt)
        model = result.scalar_one_or_none()
        return self._to_entity(model) if model else None

    async def create(self, vendor: VendorEntity) -> VendorEntity:
        model = VendorModel(
            id=vendor.id,
            vendor_code=vendor.vendor_code,
            vendor_name=vendor.vendor_name,
            vendor_email=vendor.vendor_email,
            vendor_contact=vendor.vendor_contact,
            vendor_address=vendor.vendor_address,
            city=vendor.city,
            gstn_number=vendor.gstn_number,
            pan_number=vendor.pan_number,
            bank_account_no=vendor.bank_account_no,
            bank_ifsc=vendor.bank_ifsc,
            bank_name=vendor.bank_name,
            portal_user_id=vendor.portal_user_id,
            status=vendor.status.value,
            created_by=vendor.created_by,
            modified_by=vendor.modified_by,
        )
        self._session.add(model)
        await self._session.flush()
        return self._to_entity(model)

    async def update(self, vendor: VendorEntity) -> VendorEntity:
        stmt = select(VendorModel).where(VendorModel.id == vendor.id)
        result = await self._session.execute(stmt)
        model = result.scalar_one_or_none()
        if model is None:
            raise ValueError(f"Vendor with id {vendor.id} not found")

        model.vendor_code = vendor.vendor_code
        model.vendor_name = vendor.vendor_name
        model.vendor_email = vendor.vendor_email
        model.vendor_contact = vendor.vendor_contact
        model.vendor_address = vendor.vendor_address
        model.city = vendor.city
        model.gstn_number = vendor.gstn_number
        model.pan_number = vendor.pan_number
        model.bank_account_no = vendor.bank_account_no
        model.bank_ifsc = vendor.bank_ifsc
        model.bank_name = vendor.bank_name
        model.portal_user_id = vendor.portal_user_id
        model.status = vendor.status.value
        model.modified_by = vendor.modified_by
        model.modified_date = vendor.modified_date

        await self._session.flush()
        return self._to_entity(model)

    async def delete(self, vendor_id: UUID) -> None:
        stmt = select(VendorModel).where(VendorModel.id == vendor_id)
        result = await self._session.execute(stmt)
        model = result.scalar_one_or_none()
        if model:
            await self._session.delete(model)
            await self._session.flush()

    async def list_all(
        self,
        skip: int = 0,
        limit: int = 20,
        vendor_code: str | None = None,
        vendor_name: str | None = None,
        vendor_email: str | None = None,
        city: str | None = None,
        status: str | None = None,
    ) -> list[VendorEntity]:
        stmt = select(VendorModel)
        if vendor_code:
            stmt = stmt.where(
                VendorModel.vendor_code.ilike(f"%{vendor_code}%")
            )
        if vendor_name:
            stmt = stmt.where(
                VendorModel.vendor_name.ilike(f"%{vendor_name}%")
            )
        if vendor_email:
            stmt = stmt.where(
                VendorModel.vendor_email.ilike(f"%{vendor_email}%")
            )
        if city:
            stmt = stmt.where(VendorModel.city.ilike(f"%{city}%"))
        if status:
            stmt = stmt.where(
                func.lower(VendorModel.status) == status.lower()
            )
        stmt = stmt.order_by(VendorModel.vendor_name).offset(skip).limit(limit)
        result = await self._session.execute(stmt)
        models = result.scalars().all()
        return [self._to_entity(m) for m in models]

    async def count_all(
        self,
        vendor_code: str | None = None,
        vendor_name: str | None = None,
        vendor_email: str | None = None,
        city: str | None = None,
        status: str | None = None,
    ) -> int:
        stmt = select(func.count()).select_from(VendorModel)
        if vendor_code:
            stmt = stmt.where(VendorModel.vendor_code.ilike(f"%{vendor_code}%"))
        if vendor_name:
            stmt = stmt.where(VendorModel.vendor_name.ilike(f"%{vendor_name}%"))
        if vendor_email:
            stmt = stmt.where(VendorModel.vendor_email.ilike(f"%{vendor_email}%"))
        if city:
            stmt = stmt.where(VendorModel.city.ilike(f"%{city}%"))
        if status:
            stmt = stmt.where(func.lower(VendorModel.status) == status.lower())
        result = await self._session.execute(stmt)
        return int(result.scalar_one())

    async def exists_by_code(self, vendor_code: str) -> bool:
        stmt = select(VendorModel.id).where(
            func.lower(VendorModel.vendor_code) == vendor_code.strip().lower()
        )
        result = await self._session.execute(stmt)
        return result.scalar_one_or_none() is not None

    async def exists_by_email(self, vendor_email: str) -> bool:
        stmt = select(VendorModel.id).where(
            func.lower(VendorModel.vendor_email) == vendor_email.strip().lower()
        )
        result = await self._session.execute(stmt)
        return result.scalar_one_or_none() is not None

    @staticmethod
    def _to_entity(model: VendorModel) -> VendorEntity:
        """Map ORM model to domain entity."""
        return VendorEntity(
            id=model.id,
            vendor_code=model.vendor_code,
            vendor_name=model.vendor_name,
            vendor_email=model.vendor_email,
            vendor_contact=model.vendor_contact,
            vendor_address=model.vendor_address,
            city=model.city,
            gstn_number=model.gstn_number,
            pan_number=model.pan_number,
            bank_account_no=model.bank_account_no,
            bank_ifsc=model.bank_ifsc,
            bank_name=model.bank_name,
            portal_user_id=model.portal_user_id,
            status=VendorStatus(model.status),
            created_by=model.created_by,
            created_date=model.created_date,
            modified_by=model.modified_by,
            modified_date=model.modified_date,
        )
