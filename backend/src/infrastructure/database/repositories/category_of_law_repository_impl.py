"""
Category of law repository implementation (Adapter).
Implements ICategoryOfLawRepository using SQLAlchemy async.

Primary-key lookup, code lookup, existence check and delete come from
SqlAlchemyRepository; everything below is CategoryOfLaw-specific.
"""

from typing import Any
from uuid import UUID

from sqlalchemy import ColumnElement, Select, func, or_, select

from src.domain.entities.category_of_law import CategoryOfLaw
from src.domain.repositories.category_of_law_repository import ICategoryOfLawRepository
from src.infrastructure.database.models.category_of_law_model import CategoryOfLawModel
from src.infrastructure.database.models.legislation_model import LegislationModel
from src.infrastructure.database.repositories.base_repository_impl import (
    SqlAlchemyRepository,
)


class CategoryOfLawRepositoryImpl(
    SqlAlchemyRepository[CategoryOfLaw, CategoryOfLawModel], ICategoryOfLawRepository
):
    """Concrete implementation of category of law persistence using SQLAlchemy."""

    _model = CategoryOfLawModel

    @staticmethod
    def _code_equals(code: str) -> ColumnElement[bool]:
        return CategoryOfLawModel.code == code

    # ─── Writes ───

    async def create(self, category: CategoryOfLaw) -> CategoryOfLaw:
        model = CategoryOfLawModel(
            id=category.id,
            code=category.code,
            name=category.name,
            description=category.description,
            state_id=category.state_id,
            is_active=category.is_active,
            created_by=category.created_by,
            modified_by=category.modified_by,
        )
        self._session.add(model)
        await self._session.flush()
        return self._to_entity(model)

    async def update(self, category: CategoryOfLaw) -> CategoryOfLaw:
        model = await self._require_model(category.id)

        model.code = category.code
        model.name = category.name
        model.description = category.description
        model.state_id = category.state_id
        model.is_active = category.is_active
        model.modified_by = category.modified_by
        model.modified_date = category.modified_date

        await self._session.flush()
        return self._to_entity(model)

    # ─── Queries ───

    async def list_all(
        self,
        skip: int = 0,
        limit: int = 100,
        search: str | None = None,
        is_active: bool | None = None,
        state_id: UUID | None = None,
    ) -> list[CategoryOfLaw]:
        stmt = self._apply_filters(
            select(CategoryOfLawModel), search, is_active, state_id
        )
        stmt = stmt.order_by(CategoryOfLawModel.name).offset(skip).limit(limit)
        result = await self._session.execute(stmt)
        return [self._to_entity(m) for m in result.scalars().all()]

    async def count(
        self,
        search: str | None = None,
        is_active: bool | None = None,
        state_id: UUID | None = None,
    ) -> int:
        stmt = self._apply_filters(
            select(func.count()).select_from(CategoryOfLawModel),
            search,
            is_active,
            state_id,
        )
        result = await self._session.execute(stmt)
        return int(result.scalar_one())

    async def exists_by_name(
        self, name: str, state_id: UUID | None, exclude_id: UUID | None = None
    ) -> bool:
        stmt = select(CategoryOfLawModel.id).where(
            func.lower(CategoryOfLawModel.name) == name.lower()
        )
        if state_id is None:
            stmt = stmt.where(CategoryOfLawModel.state_id.is_(None))
        else:
            stmt = stmt.where(CategoryOfLawModel.state_id == state_id)
        if exclude_id is not None:
            stmt = stmt.where(CategoryOfLawModel.id != exclude_id)
        result = await self._session.execute(stmt)
        return result.scalar_one_or_none() is not None

    async def has_dependents(self, category_of_law_id: UUID) -> bool:
        """True if any legislation still references this category."""
        stmt = (
            select(LegislationModel.id)
            .where(LegislationModel.category_of_law_id == category_of_law_id)
            .limit(1)
        )
        result = await self._session.execute(stmt)
        return result.scalar_one_or_none() is not None

    # ─── Internals ───

    @staticmethod
    def _apply_filters(
        stmt: Select[Any],
        search: str | None,
        is_active: bool | None,
        state_id: UUID | None,
    ) -> Select[Any]:
        if search:
            pattern = f"%{search.strip()}%"
            stmt = stmt.where(
                or_(
                    CategoryOfLawModel.code.ilike(pattern),
                    CategoryOfLawModel.name.ilike(pattern),
                )
            )
        if is_active is not None:
            stmt = stmt.where(CategoryOfLawModel.is_active.is_(is_active))
        if state_id is not None:
            stmt = stmt.where(CategoryOfLawModel.state_id == state_id)
        return stmt

    @staticmethod
    def _to_entity(model: CategoryOfLawModel) -> CategoryOfLaw:
        """Map ORM model to domain entity."""
        return CategoryOfLaw(
            id=model.id,
            code=model.code,
            name=model.name,
            description=model.description,
            state_id=model.state_id,
            is_active=model.is_active,
            created_by=model.created_by,
            created_date=model.created_date,
            modified_by=model.modified_by,
            modified_date=model.modified_date,
        )
