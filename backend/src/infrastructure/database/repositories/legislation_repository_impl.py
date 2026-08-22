"""
Legislation repository implementation (Adapter).
Implements ILegislationRepository using SQLAlchemy async.

Primary-key lookup, code lookup, existence check and delete come from
SqlAlchemyRepository; everything below is Legislation-specific.
"""

from typing import Any
from uuid import UUID

from sqlalchemy import ColumnElement, Select, func, or_, select

from src.domain.entities.legislation import Legislation
from src.domain.repositories.legislation_repository import ILegislationRepository
from src.infrastructure.database.models.legislation_model import LegislationModel
from src.infrastructure.database.models.rule_model import RuleModel
from src.infrastructure.database.repositories.base_repository_impl import (
    SqlAlchemyRepository,
)


class LegislationRepositoryImpl(
    SqlAlchemyRepository[Legislation, LegislationModel], ILegislationRepository
):
    """Concrete implementation of legislation persistence using SQLAlchemy."""

    _model = LegislationModel

    @staticmethod
    def _code_equals(code: str) -> ColumnElement[bool]:
        return LegislationModel.code == code

    # ─── Writes ───

    async def create(self, legislation: Legislation) -> Legislation:
        model = LegislationModel(
            id=legislation.id,
            code=legislation.code,
            name=legislation.name,
            description=legislation.description,
            category_of_law_id=legislation.category_of_law_id,
            state_id=legislation.state_id,
            country_id=legislation.country_id,
            legislation_number=legislation.legislation_number,
            effective_date=legislation.effective_date,
            is_active=legislation.is_active,
            created_by=legislation.created_by,
            modified_by=legislation.modified_by,
        )
        self._session.add(model)
        await self._session.flush()
        return self._to_entity(model)

    async def update(self, legislation: Legislation) -> Legislation:
        model = await self._require_model(legislation.id)

        model.code = legislation.code
        model.name = legislation.name
        model.description = legislation.description
        model.category_of_law_id = legislation.category_of_law_id
        model.state_id = legislation.state_id
        model.country_id = legislation.country_id
        model.legislation_number = legislation.legislation_number
        model.effective_date = legislation.effective_date
        model.is_active = legislation.is_active
        model.modified_by = legislation.modified_by
        model.modified_date = legislation.modified_date

        await self._session.flush()
        return self._to_entity(model)

    # ─── Queries ───

    async def list_all(
        self,
        skip: int = 0,
        limit: int = 100,
        search: str | None = None,
        is_active: bool | None = None,
        country_id: UUID | None = None,
        state_id: UUID | None = None,
        category_of_law_id: UUID | None = None,
    ) -> list[Legislation]:
        stmt = self._apply_filters(
            select(LegislationModel),
            search,
            is_active,
            country_id,
            state_id,
            category_of_law_id,
        )
        stmt = stmt.order_by(LegislationModel.name).offset(skip).limit(limit)
        result = await self._session.execute(stmt)
        return [self._to_entity(m) for m in result.scalars().all()]

    async def count(
        self,
        search: str | None = None,
        is_active: bool | None = None,
        country_id: UUID | None = None,
        state_id: UUID | None = None,
        category_of_law_id: UUID | None = None,
    ) -> int:
        stmt = self._apply_filters(
            select(func.count()).select_from(LegislationModel),
            search,
            is_active,
            country_id,
            state_id,
            category_of_law_id,
        )
        result = await self._session.execute(stmt)
        return int(result.scalar_one())

    async def has_dependents(self, legislation_id: UUID) -> bool:
        """True if any rule still references this legislation."""
        stmt = (
            select(RuleModel.id)
            .where(RuleModel.legislation_id == legislation_id)
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
        country_id: UUID | None,
        state_id: UUID | None,
        category_of_law_id: UUID | None,
    ) -> Select[Any]:
        if search:
            pattern = f"%{search.strip()}%"
            stmt = stmt.where(
                or_(
                    LegislationModel.code.ilike(pattern),
                    LegislationModel.name.ilike(pattern),
                    LegislationModel.legislation_number.ilike(pattern),
                )
            )
        if is_active is not None:
            stmt = stmt.where(LegislationModel.is_active.is_(is_active))
        if country_id is not None:
            stmt = stmt.where(LegislationModel.country_id == country_id)
        if state_id is not None:
            stmt = stmt.where(LegislationModel.state_id == state_id)
        if category_of_law_id is not None:
            stmt = stmt.where(LegislationModel.category_of_law_id == category_of_law_id)
        return stmt

    @staticmethod
    def _to_entity(model: LegislationModel) -> Legislation:
        """Map ORM model to domain entity."""
        return Legislation(
            id=model.id,
            code=model.code,
            name=model.name,
            description=model.description,
            category_of_law_id=model.category_of_law_id,
            state_id=model.state_id,
            country_id=model.country_id,
            legislation_number=model.legislation_number,
            effective_date=model.effective_date,
            is_active=model.is_active,
            created_by=model.created_by,
            created_date=model.created_date,
            modified_by=model.modified_by,
            modified_date=model.modified_date,
        )
