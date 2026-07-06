"""
Product Master repository implementation (Adapter).

Implements :class:`IProductRepository` using SQLAlchemy async. The former
two-level hierarchy (product_masters + product_details) has been collapsed into
a single ``product_master`` table represented by :class:`ProductMasterModel`.
"""

from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.domain.entities.masters.product import ProductMasterEntity
from src.domain.enums.masters import ProductStatus
from src.domain.repositories.masters.product_repository import IProductRepository
from src.infrastructure.database.models.masters.product_model import ProductMasterModel


class ProductRepositoryImpl(IProductRepository):
    """Concrete implementation of product persistence using SQLAlchemy."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    # ─── CRUD ────────────────────────────────────────────────────────────

    async def create(self, product: ProductMasterEntity) -> ProductMasterEntity:
        model = ProductMasterModel(
            id=product.id,
            basic_material_code=product.basic_material_code,
            product_name=product.product_name,
            child_code=product.child_code,
            variant_description=product.variant_description,
            hsn_code=product.hsn_code,
            pack_size=product.pack_size,
            unit_of_measure=product.unit_of_measure,
            mrp=product.mrp,
            rate=product.rate,
            gst_percent=product.gst_percent,
            status=str(product.status),
            created_by=product.created_by,
            modified_by=product.modified_by,
        )
        self._session.add(model)
        await self._session.flush()
        return self._to_entity(model)

    async def update(self, product: ProductMasterEntity) -> ProductMasterEntity:
        stmt = select(ProductMasterModel).where(ProductMasterModel.id == product.id)
        result = await self._session.execute(stmt)
        model = result.scalar_one_or_none()
        if model is None:
            raise ValueError(f"Product Master with id {product.id} not found")

        model.basic_material_code = product.basic_material_code
        model.product_name = product.product_name
        model.child_code = product.child_code
        model.variant_description = product.variant_description
        model.hsn_code = product.hsn_code
        model.pack_size = product.pack_size
        model.unit_of_measure = product.unit_of_measure
        model.mrp = product.mrp
        model.rate = product.rate
        model.gst_percent = product.gst_percent
        model.status = str(product.status)
        model.modified_by = product.modified_by
        model.modified_date = product.modified_date

        await self._session.flush()
        return self._to_entity(model)

    async def get_by_id(self, product_id: UUID) -> ProductMasterEntity | None:
        stmt = select(ProductMasterModel).where(ProductMasterModel.id == product_id)
        result = await self._session.execute(stmt)
        model = result.scalar_one_or_none()
        return self._to_entity(model) if model else None

    async def delete(self, product_id: UUID) -> None:
        stmt = select(ProductMasterModel).where(ProductMasterModel.id == product_id)
        result = await self._session.execute(stmt)
        model = result.scalar_one_or_none()
        if model:
            await self._session.delete(model)
            await self._session.flush()

    async def list(
        self, skip: int = 0, limit: int = 20
    ) -> list[ProductMasterEntity]:
        stmt = (
            select(ProductMasterModel)
            .order_by(ProductMasterModel.created_date, ProductMasterModel.id)
            .offset(skip)
            .limit(limit)
        )
        result = await self._session.execute(stmt)
        models = result.scalars().all()
        return [self._to_entity(m) for m in models]

    async def count(self) -> int:
        stmt = select(func.count()).select_from(ProductMasterModel)
        result = await self._session.execute(stmt)
        return int(result.scalar_one())

    async def exists_by_child_code(
        self, child_code: str, exclude_id: UUID | None = None
    ) -> bool:
        stmt = select(ProductMasterModel.id).where(
            ProductMasterModel.child_code == child_code
        )
        if exclude_id is not None:
            stmt = stmt.where(ProductMasterModel.id != exclude_id)
        result = await self._session.execute(stmt)
        return result.scalar_one_or_none() is not None

    async def get_by_child_code(
        self, child_code: str
    ) -> ProductMasterEntity | None:
        stmt = select(ProductMasterModel).where(
            ProductMasterModel.child_code == child_code
        )
        result = await self._session.execute(stmt)
        model = result.scalar_one_or_none()
        return self._to_entity(model) if model else None

    async def get_by_basic_material_code(
        self, basic_material_code: str
    ) -> ProductMasterEntity | None:
        stmt = select(ProductMasterModel).where(
            ProductMasterModel.basic_material_code == basic_material_code
        )
        result = await self._session.execute(stmt)
        model = result.scalar_one_or_none()
        return self._to_entity(model) if model else None

    # ─── Mapper ──────────────────────────────────────────────────────────

    @staticmethod
    def _to_entity(model: ProductMasterModel) -> ProductMasterEntity:
        return ProductMasterEntity(
            id=model.id,
            basic_material_code=model.basic_material_code,
            product_name=model.product_name,
            child_code=model.child_code,
            variant_description=model.variant_description,
            hsn_code=model.hsn_code,
            pack_size=model.pack_size,
            unit_of_measure=model.unit_of_measure,
            mrp=model.mrp,
            rate=model.rate,
            gst_percent=model.gst_percent,
            status=ProductStatus(model.status),
            created_by=model.created_by,
            created_date=model.created_date,
            modified_by=model.modified_by,
            modified_date=model.modified_date,
        )
