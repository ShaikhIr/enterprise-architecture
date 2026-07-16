"""
Entity repository implementation (Adapter).
Implements ``IEntityRepository`` using SQLAlchemy async.

Uniqueness and search use trimmed, case-insensitive comparisons
(``func.lower(func.trim(col))``) as required by the design.
"""

from __future__ import annotations

from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.domain.entities.masters.entity import EntityEntity
from src.domain.repositories.masters.entity_repository import IEntityRepository
from src.infrastructure.database.models.masters.entity_model import EntityModel


class EntityRepositoryImpl(IEntityRepository):
    """Concrete implementation of Entity persistence using SQLAlchemy."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get_by_id(self, entity_id: UUID) -> EntityEntity | None:
        stmt = select(EntityModel).where(EntityModel.id == entity_id)
        result = await self._session.execute(stmt)
        model = result.scalar_one_or_none()
        return self._to_entity(model) if model else None

    async def create(self, entity: EntityEntity) -> EntityEntity:
        model = EntityModel(
            id=entity.id,
            entity_name=entity.entity_name,
            short_code=entity.short_code,
            company_code=entity.company_code,
            is_active=entity.is_active,
            workflow_definition_id=entity.workflow_definition_id,
            created_by=entity.created_by,
            modified_by=entity.modified_by,
        )
        self._session.add(model)
        await self._session.flush()
        return self._to_entity(model)

    async def update(self, entity: EntityEntity) -> EntityEntity:
        stmt = select(EntityModel).where(EntityModel.id == entity.id)
        result = await self._session.execute(stmt)
        model = result.scalar_one_or_none()
        if model is None:
            raise ValueError(f"Entity with id {entity.id} not found")

        model.entity_name = entity.entity_name
        model.short_code = entity.short_code
        model.company_code = entity.company_code
        model.is_active = entity.is_active
        model.workflow_definition_id = entity.workflow_definition_id
        model.modified_by = entity.modified_by
        model.modified_date = entity.modified_date

        await self._session.flush()
        return self._to_entity(model)

    async def delete(self, entity_id: UUID) -> None:
        stmt = select(EntityModel).where(EntityModel.id == entity_id)
        result = await self._session.execute(stmt)
        model = result.scalar_one_or_none()
        if model:
            await self._session.delete(model)
            await self._session.flush()

    async def list(
        self,
        skip: int = 0,
        limit: int = 20,
        search: str | None = None,
        is_active: bool | None = None,
    ) -> tuple[list[EntityEntity], int]:
        conditions = []

        if search is not None and search.strip():
            term = f"%{search.strip().lower()}%"
            conditions.append(
                func.lower(func.trim(EntityModel.entity_name)).like(term)
                | func.lower(func.trim(EntityModel.short_code)).like(term)
                | func.lower(func.trim(EntityModel.company_code)).like(term)
            )

        if is_active is not None:
            conditions.append(EntityModel.is_active == is_active)

        count_stmt = select(func.count()).select_from(EntityModel)
        page_stmt = select(EntityModel)
        for condition in conditions:
            count_stmt = count_stmt.where(condition)
            page_stmt = page_stmt.where(condition)

        total = (await self._session.execute(count_stmt)).scalar_one()

        page_stmt = (
            page_stmt.order_by(EntityModel.entity_name, EntityModel.id)
            .offset(skip)
            .limit(limit)
        )
        models = (await self._session.execute(page_stmt)).scalars().all()

        return [self._to_entity(m) for m in models], total

    async def list_active(self) -> list[EntityEntity]:
        stmt = (
            select(EntityModel)
            .where(EntityModel.is_active.is_(True))
            .order_by(EntityModel.entity_name, EntityModel.id)
        )
        models = (await self._session.execute(stmt)).scalars().all()
        return [self._to_entity(m) for m in models]

    async def get_by_name(self, entity_name: str) -> EntityEntity | None:
        stmt = select(EntityModel).where(
            func.lower(func.trim(EntityModel.entity_name))
            == entity_name.strip().lower()
        )
        result = await self._session.execute(stmt)
        model = result.scalar_one_or_none()
        return self._to_entity(model) if model else None

    async def get_by_company_code(self, company_code: str) -> EntityEntity | None:
        stmt = select(EntityModel).where(
            func.lower(func.trim(EntityModel.company_code))
            == company_code.strip().lower()
        )
        result = await self._session.execute(stmt)
        model = result.scalar_one_or_none()
        return self._to_entity(model) if model else None

    async def exists_by_name(
        self, entity_name: str, exclude_id: UUID | None = None
    ) -> bool:
        stmt = select(EntityModel.id).where(
            func.lower(func.trim(EntityModel.entity_name))
            == entity_name.strip().lower()
        )
        if exclude_id is not None:
            stmt = stmt.where(EntityModel.id != exclude_id)
        result = await self._session.execute(stmt)
        return result.first() is not None

    async def exists_by_company_code(
        self, company_code: str, exclude_id: UUID | None = None
    ) -> bool:
        stmt = select(EntityModel.id).where(
            func.lower(func.trim(EntityModel.company_code))
            == company_code.strip().lower()
        )
        if exclude_id is not None:
            stmt = stmt.where(EntityModel.id != exclude_id)
        result = await self._session.execute(stmt)
        return result.first() is not None

    @staticmethod
    def _to_entity(model: EntityModel) -> EntityEntity:
        """Map ORM model to domain entity."""
        return EntityEntity(
            id=model.id,
            entity_name=model.entity_name,
            short_code=model.short_code,
            company_code=model.company_code,
            is_active=model.is_active,
            workflow_definition_id=model.workflow_definition_id,
            created_by=model.created_by,
            created_date=model.created_date,
            modified_by=model.modified_by,
            modified_date=model.modified_date,
        )
