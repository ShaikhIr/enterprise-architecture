"""
Country repository implementation (Adapter).
Implements ICountryRepository using SQLAlchemy async.

Primary-key lookup, code lookup, existence check and delete come from
SqlAlchemyRepository; everything below is Country-specific.
"""

from typing import Any

from sqlalchemy import ColumnElement, Select, func, or_, select

from src.domain.entities.country import Country
from src.domain.repositories.country_repository import ICountryRepository
from src.infrastructure.database.models.country_model import CountryModel
from src.infrastructure.database.models.legislation_model import LegislationModel
from src.infrastructure.database.models.rule_model import RuleModel
from src.infrastructure.database.models.state_model import StateModel
from src.infrastructure.database.repositories.base_repository_impl import (
    SqlAlchemyRepository,
)


class CountryRepositoryImpl(
    SqlAlchemyRepository[Country, CountryModel], ICountryRepository
):
    """Concrete implementation of country persistence using SQLAlchemy."""

    _model = CountryModel

    @staticmethod
    def _code_equals(code: str) -> ColumnElement[bool]:
        return CountryModel.code == code

    # ─── Writes ───

    async def create(self, country: Country) -> Country:
        model = CountryModel(
            code=country.code,
            name=country.name,
            iso3_code=country.iso3_code,
            dial_code=country.dial_code,
            currency_code=country.currency_code,
            is_active=country.is_active,
            created_by=country.created_by,
            modified_by=country.modified_by,
        )
        self._session.add(model)
        await self._session.flush()
        return self._to_entity(model)

    async def update(self, country: Country) -> Country:
        model = await self._require_model(country.id)

        model.code = country.code
        model.name = country.name
        model.iso3_code = country.iso3_code
        model.dial_code = country.dial_code
        model.currency_code = country.currency_code
        model.is_active = country.is_active
        model.modified_by = country.modified_by
        model.modified_date = country.modified_date

        await self._session.flush()
        return self._to_entity(model)

    # ─── Queries ───

    async def list_all(
        self,
        skip: int = 0,
        limit: int = 100,
        search: str | None = None,
        is_active: bool | None = None,
    ) -> list[Country]:
        stmt = self._apply_filters(select(CountryModel), search, is_active)
        stmt = stmt.order_by(CountryModel.name).offset(skip).limit(limit)
        result = await self._session.execute(stmt)
        return [self._to_entity(m) for m in result.scalars().all()]

    async def count(
        self,
        search: str | None = None,
        is_active: bool | None = None,
    ) -> int:
        stmt = self._apply_filters(
            select(func.count()).select_from(CountryModel), search, is_active
        )
        result = await self._session.execute(stmt)
        return int(result.scalar_one())

    async def exists_by_name(self, name: str, exclude_id: int | None = None) -> bool:
        stmt = select(CountryModel.id).where(
            func.lower(CountryModel.name) == name.lower()
        )
        if exclude_id is not None:
            stmt = stmt.where(CountryModel.id != exclude_id)
        result = await self._session.execute(stmt)
        return result.scalar_one_or_none() is not None

    async def has_dependents(self, country_id: int) -> bool:
        """True if any state, legislation or rule still references this country."""
        for model in (StateModel, LegislationModel, RuleModel):
            stmt = select(model.id).where(model.country_id == country_id).limit(1)
            result = await self._session.execute(stmt)
            if result.scalar_one_or_none() is not None:
                return True
        return False

    # ─── Internals ───

    @staticmethod
    def _apply_filters(
        stmt: Select[Any], search: str | None, is_active: bool | None
    ) -> Select[Any]:
        if search:
            pattern = f"%{search.strip()}%"
            stmt = stmt.where(
                or_(
                    CountryModel.code.ilike(pattern),
                    CountryModel.name.ilike(pattern),
                    CountryModel.iso3_code.ilike(pattern),
                )
            )
        if is_active is not None:
            stmt = stmt.where(CountryModel.is_active.is_(is_active))
        return stmt

    @staticmethod
    def _to_entity(model: CountryModel) -> Country:
        """Map ORM model to domain entity."""
        return Country(
            id=model.id,
            code=model.code,
            name=model.name,
            iso3_code=model.iso3_code,
            dial_code=model.dial_code,
            currency_code=model.currency_code,
            is_active=model.is_active,
            created_by=model.created_by,
            created_date=model.created_date,
            modified_by=model.modified_by,
            modified_date=model.modified_date,
        )
