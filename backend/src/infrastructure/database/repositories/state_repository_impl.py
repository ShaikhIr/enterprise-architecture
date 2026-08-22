"""
State repository implementation (Adapter).
Implements IStateRepository using SQLAlchemy async.

Primary-key lookup, code lookup, existence check and delete come from
SqlAlchemyRepository; everything below is State-specific.
"""

from typing import Any
from uuid import UUID

from sqlalchemy import ColumnElement, Select, func, or_, select

from src.domain.entities.state import State
from src.domain.repositories.state_repository import IStateRepository
from src.infrastructure.database.models.category_of_law_model import CategoryOfLawModel
from src.infrastructure.database.models.legislation_model import LegislationModel
from src.infrastructure.database.models.rule_model import RuleModel
from src.infrastructure.database.models.state_model import StateModel
from src.infrastructure.database.repositories.base_repository_impl import (
    SqlAlchemyRepository,
)


class StateRepositoryImpl(SqlAlchemyRepository[State, StateModel], IStateRepository):
    """Concrete implementation of state persistence using SQLAlchemy."""

    _model = StateModel

    @staticmethod
    def _code_equals(code: str) -> ColumnElement[bool]:
        return StateModel.code == code

    # ─── Writes ───

    async def create(self, state: State) -> State:
        model = StateModel(
            id=state.id,
            code=state.code,
            name=state.name,
            country_id=state.country_id,
            is_union_territory=state.is_union_territory,
            is_active=state.is_active,
            created_by=state.created_by,
            modified_by=state.modified_by,
        )
        self._session.add(model)
        await self._session.flush()
        return self._to_entity(model)

    async def update(self, state: State) -> State:
        model = await self._require_model(state.id)

        model.code = state.code
        model.name = state.name
        model.country_id = state.country_id
        model.is_union_territory = state.is_union_territory
        model.is_active = state.is_active
        model.modified_by = state.modified_by
        model.modified_date = state.modified_date

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
    ) -> list[State]:
        stmt = self._apply_filters(select(StateModel), search, is_active, country_id)
        stmt = stmt.order_by(StateModel.name).offset(skip).limit(limit)
        result = await self._session.execute(stmt)
        return [self._to_entity(m) for m in result.scalars().all()]

    async def count(
        self,
        search: str | None = None,
        is_active: bool | None = None,
        country_id: UUID | None = None,
    ) -> int:
        stmt = self._apply_filters(
            select(func.count()).select_from(StateModel), search, is_active, country_id
        )
        result = await self._session.execute(stmt)
        return int(result.scalar_one())

    async def exists_by_name(
        self, name: str, country_id: UUID, exclude_id: UUID | None = None
    ) -> bool:
        stmt = select(StateModel.id).where(
            func.lower(StateModel.name) == name.lower(),
            StateModel.country_id == country_id,
        )
        if exclude_id is not None:
            stmt = stmt.where(StateModel.id != exclude_id)
        result = await self._session.execute(stmt)
        return result.scalar_one_or_none() is not None

    async def has_dependents(self, state_id: UUID) -> bool:
        """True if any category, legislation or rule still references this state."""
        for model in (CategoryOfLawModel, LegislationModel, RuleModel):
            stmt = select(model.id).where(model.state_id == state_id).limit(1)
            result = await self._session.execute(stmt)
            if result.scalar_one_or_none() is not None:
                return True
        return False

    # ─── Internals ───

    @staticmethod
    def _apply_filters(
        stmt: Select[Any],
        search: str | None,
        is_active: bool | None,
        country_id: UUID | None,
    ) -> Select[Any]:
        if search:
            pattern = f"%{search.strip()}%"
            stmt = stmt.where(
                or_(StateModel.code.ilike(pattern), StateModel.name.ilike(pattern))
            )
        if is_active is not None:
            stmt = stmt.where(StateModel.is_active.is_(is_active))
        if country_id is not None:
            stmt = stmt.where(StateModel.country_id == country_id)
        return stmt

    @staticmethod
    def _to_entity(model: StateModel) -> State:
        """Map ORM model to domain entity."""
        return State(
            id=model.id,
            code=model.code,
            name=model.name,
            country_id=model.country_id,
            is_union_territory=model.is_union_territory,
            is_active=model.is_active,
            created_by=model.created_by,
            created_date=model.created_date,
            modified_by=model.modified_by,
            modified_date=model.modified_date,
        )
