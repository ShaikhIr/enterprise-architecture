"""
Rule repository implementation (Adapter).
Implements IRuleRepository using SQLAlchemy async.

Primary-key lookup, code lookup, existence check and delete come from
SqlAlchemyRepository; everything below is Rule-specific.
"""

from typing import Any
from uuid import UUID

from sqlalchemy import ColumnElement, Select, func, or_, select

from src.domain.entities.rule import Rule
from src.domain.repositories.rule_repository import IRuleRepository
from src.infrastructure.database.models.rule_model import RuleModel
from src.infrastructure.database.repositories.base_repository_impl import (
    SqlAlchemyRepository,
)


class RuleRepositoryImpl(SqlAlchemyRepository[Rule, RuleModel], IRuleRepository):
    """Concrete implementation of rule persistence using SQLAlchemy."""

    _model = RuleModel

    @staticmethod
    def _code_equals(code: str) -> ColumnElement[bool]:
        return RuleModel.code == code

    # ─── Writes ───

    async def create(self, rule: Rule) -> Rule:
        model = RuleModel(
            id=rule.id,
            code=rule.code,
            name=rule.name,
            description=rule.description,
            legislation_id=rule.legislation_id,
            state_id=rule.state_id,
            country_id=rule.country_id,
            rule_number=rule.rule_number,
            effective_date=rule.effective_date,
            is_active=rule.is_active,
            created_by=rule.created_by,
            modified_by=rule.modified_by,
        )
        self._session.add(model)
        await self._session.flush()
        return self._to_entity(model)

    async def update(self, rule: Rule) -> Rule:
        model = await self._require_model(rule.id)

        model.code = rule.code
        model.name = rule.name
        model.description = rule.description
        model.legislation_id = rule.legislation_id
        model.state_id = rule.state_id
        model.country_id = rule.country_id
        model.rule_number = rule.rule_number
        model.effective_date = rule.effective_date
        model.is_active = rule.is_active
        model.modified_by = rule.modified_by
        model.modified_date = rule.modified_date

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
        legislation_id: UUID | None = None,
    ) -> list[Rule]:
        stmt = self._apply_filters(
            select(RuleModel), search, is_active, country_id, state_id, legislation_id
        )
        stmt = stmt.order_by(RuleModel.name).offset(skip).limit(limit)
        result = await self._session.execute(stmt)
        return [self._to_entity(m) for m in result.scalars().all()]

    async def count(
        self,
        search: str | None = None,
        is_active: bool | None = None,
        country_id: UUID | None = None,
        state_id: UUID | None = None,
        legislation_id: UUID | None = None,
    ) -> int:
        stmt = self._apply_filters(
            select(func.count()).select_from(RuleModel),
            search,
            is_active,
            country_id,
            state_id,
            legislation_id,
        )
        result = await self._session.execute(stmt)
        return int(result.scalar_one())

    # ─── Internals ───

    @staticmethod
    def _apply_filters(
        stmt: Select[Any],
        search: str | None,
        is_active: bool | None,
        country_id: UUID | None,
        state_id: UUID | None,
        legislation_id: UUID | None,
    ) -> Select[Any]:
        if search:
            pattern = f"%{search.strip()}%"
            stmt = stmt.where(
                or_(
                    RuleModel.code.ilike(pattern),
                    RuleModel.name.ilike(pattern),
                    RuleModel.rule_number.ilike(pattern),
                )
            )
        if is_active is not None:
            stmt = stmt.where(RuleModel.is_active.is_(is_active))
        if country_id is not None:
            stmt = stmt.where(RuleModel.country_id == country_id)
        if state_id is not None:
            stmt = stmt.where(RuleModel.state_id == state_id)
        if legislation_id is not None:
            stmt = stmt.where(RuleModel.legislation_id == legislation_id)
        return stmt

    @staticmethod
    def _to_entity(model: RuleModel) -> Rule:
        """Map ORM model to domain entity."""
        return Rule(
            id=model.id,
            code=model.code,
            name=model.name,
            description=model.description,
            legislation_id=model.legislation_id,
            state_id=model.state_id,
            country_id=model.country_id,
            rule_number=model.rule_number,
            effective_date=model.effective_date,
            is_active=model.is_active,
            created_by=model.created_by,
            created_date=model.created_date,
            modified_by=model.modified_by,
            modified_date=model.modified_date,
        )
