"""
LegislationRepositoryImpl tests, against a real database session.

Legislation is the first master with three simultaneous parent filters
(country, state, category) plus a `search` that spans a third column
(`legislation_number`) beyond the code/name every other master's search covers.
Both are untested anywhere else — the HTTP suite exercises one filter
combination, not each in isolation.
"""

from uuid import uuid4

from sqlalchemy.ext.asyncio import AsyncSession

from src.domain.entities.legislation import Legislation
from src.infrastructure.database.models.category_of_law_model import CategoryOfLawModel
from src.infrastructure.database.models.country_model import CountryModel
from src.infrastructure.database.models.rule_model import RuleModel
from src.infrastructure.database.models.state_model import StateModel
from src.infrastructure.database.repositories.legislation_repository_impl import (
    LegislationRepositoryImpl,
)


async def _make_country(session: AsyncSession) -> CountryModel:
    country = CountryModel(
        id=uuid4(), code=f"C{uuid4().hex[:6].upper()}", name=f"Country {uuid4().hex[:6]}",
        created_by="test", modified_by="test",
    )
    session.add(country)
    await session.flush()
    return country


async def _make_category(session: AsyncSession) -> CategoryOfLawModel:
    category = CategoryOfLawModel(
        id=uuid4(), code=f"CAT{uuid4().hex[:6].upper()}", name=f"Category {uuid4().hex[:6]}",
        created_by="test", modified_by="test",
    )
    session.add(category)
    await session.flush()
    return category


async def _make_state(session: AsyncSession, country_id: object) -> StateModel:
    state = StateModel(
        id=uuid4(), code=f"S{uuid4().hex[:6].upper()}", name=f"State {uuid4().hex[:6]}",
        country_id=country_id, created_by="test", modified_by="test",
    )
    session.add(state)
    await session.flush()
    return state


def _legislation(country_id: object, category_id: object, **overrides: object) -> Legislation:
    defaults: dict[str, object] = {
        "code": f"L{uuid4().hex[:8].upper()}",
        "name": f"Legislation {uuid4().hex[:6]}",
        "country_id": country_id,
        "category_of_law_id": category_id,
        "created_by": "test",
        "modified_by": "test",
    }
    defaults.update(overrides)
    return Legislation(**defaults)  # type: ignore[arg-type]


class TestCrud:
    async def test_create_then_get_round_trips_optional_fields(
        self, db_session: AsyncSession
    ) -> None:
        from datetime import date

        repo = LegislationRepositoryImpl(db_session)
        country = await _make_country(db_session)
        category = await _make_category(db_session)

        created = await repo.create(
            _legislation(
                country.id,
                category.id,
                legislation_number="Act No. 63 of 1948",
                effective_date=date(1948, 4, 1),
            )
        )
        fetched = await repo.get_by_id(created.id)

        assert fetched is not None
        assert fetched.legislation_number == "Act No. 63 of 1948"
        assert fetched.effective_date == date(1948, 4, 1)

    async def test_update_persists_a_new_state(self, db_session: AsyncSession) -> None:
        repo = LegislationRepositoryImpl(db_session)
        country = await _make_country(db_session)
        category = await _make_category(db_session)
        state = await _make_state(db_session, country.id)
        created = await repo.create(_legislation(country.id, category.id))

        created.state_id = state.id
        updated = await repo.update(created)

        assert updated.state_id == state.id


class TestFilters:
    async def test_search_matches_legislation_number(self, db_session: AsyncSession) -> None:
        repo = LegislationRepositoryImpl(db_session)
        country = await _make_country(db_session)
        category = await _make_category(db_session)
        await repo.create(
            _legislation(
                country.id, category.id, name="Some Act", legislation_number="Act No. 5"
            )
        )

        rows = await repo.list_all(search="Act No. 5")

        assert len(rows) == 1

    async def test_filters_combine_with_and(self, db_session: AsyncSession) -> None:
        """country_id + category_of_law_id together narrow further than either alone."""
        repo = LegislationRepositoryImpl(db_session)
        country_a = await _make_country(db_session)
        country_b = await _make_country(db_session)
        category = await _make_category(db_session)
        await repo.create(_legislation(country_a.id, category.id, name="Match"))
        await repo.create(_legislation(country_b.id, category.id, name="Wrong Country"))

        rows = await repo.list_all(country_id=country_a.id, category_of_law_id=category.id)

        assert [r.name for r in rows] == ["Match"]

    async def test_state_filter_narrows_within_a_country(self, db_session: AsyncSession) -> None:
        repo = LegislationRepositoryImpl(db_session)
        country = await _make_country(db_session)
        category = await _make_category(db_session)
        state = await _make_state(db_session, country.id)
        await repo.create(
            _legislation(country.id, category.id, name="Central", state_id=None)
        )
        await repo.create(
            _legislation(country.id, category.id, name="State-scoped", state_id=state.id)
        )

        rows = await repo.list_all(country_id=country.id, state_id=state.id)

        assert [r.name for r in rows] == ["State-scoped"]


class TestHasDependents:
    async def test_true_when_a_rule_references_it(self, db_session: AsyncSession) -> None:
        repo = LegislationRepositoryImpl(db_session)
        country = await _make_country(db_session)
        category = await _make_category(db_session)
        created = await repo.create(_legislation(country.id, category.id))
        db_session.add(
            RuleModel(
                id=uuid4(), code="R1", name="A Rule",
                legislation_id=created.id, country_id=country.id,
                created_by="test", modified_by="test",
            )
        )
        await db_session.flush()

        assert await repo.has_dependents(created.id) is True

    async def test_false_with_no_rules(self, db_session: AsyncSession) -> None:
        repo = LegislationRepositoryImpl(db_session)
        country = await _make_country(db_session)
        category = await _make_category(db_session)
        created = await repo.create(_legislation(country.id, category.id))

        assert await repo.has_dependents(created.id) is False
