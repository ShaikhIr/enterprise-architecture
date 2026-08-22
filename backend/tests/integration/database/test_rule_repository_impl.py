"""
RuleRepositoryImpl tests, against a real database session.

Rule is the leaf of the jurisdiction hierarchy: no `has_dependents`, no
`exists_by_name`. What is worth its own coverage is the same three-filter
combination Legislation has (country/state/legislation), plus the search
spanning `rule_number` in addition to code/name.
"""

from uuid import uuid4

from sqlalchemy.ext.asyncio import AsyncSession

from src.domain.entities.rule import Rule
from src.infrastructure.database.models.category_of_law_model import CategoryOfLawModel
from src.infrastructure.database.models.country_model import CountryModel
from src.infrastructure.database.models.legislation_model import LegislationModel
from src.infrastructure.database.models.state_model import StateModel
from src.infrastructure.database.repositories.rule_repository_impl import (
    RuleRepositoryImpl,
)


async def _make_country(session: AsyncSession) -> CountryModel:
    country = CountryModel(
        id=uuid4(), code=f"C{uuid4().hex[:6].upper()}", name=f"Country {uuid4().hex[:6]}",
        created_by="test", modified_by="test",
    )
    session.add(country)
    await session.flush()
    return country


async def _make_legislation(session: AsyncSession, country_id: object) -> LegislationModel:
    category = CategoryOfLawModel(
        id=uuid4(), code=f"CAT{uuid4().hex[:6].upper()}", name=f"Category {uuid4().hex[:6]}",
        created_by="test", modified_by="test",
    )
    session.add(category)
    await session.flush()
    legislation = LegislationModel(
        id=uuid4(), code=f"L{uuid4().hex[:8].upper()}", name=f"Legislation {uuid4().hex[:6]}",
        category_of_law_id=category.id, country_id=country_id,
        created_by="test", modified_by="test",
    )
    session.add(legislation)
    await session.flush()
    return legislation


async def _make_state(session: AsyncSession, country_id: object) -> StateModel:
    state = StateModel(
        id=uuid4(), code=f"S{uuid4().hex[:6].upper()}", name=f"State {uuid4().hex[:6]}",
        country_id=country_id, created_by="test", modified_by="test",
    )
    session.add(state)
    await session.flush()
    return state


def _rule(country_id: object, legislation_id: object, **overrides: object) -> Rule:
    defaults: dict[str, object] = {
        "code": f"R{uuid4().hex[:8].upper()}",
        "name": f"Rule {uuid4().hex[:6]}",
        "country_id": country_id,
        "legislation_id": legislation_id,
        "created_by": "test",
        "modified_by": "test",
    }
    defaults.update(overrides)
    return Rule(**defaults)  # type: ignore[arg-type]


class TestCrud:
    async def test_create_then_get_round_trips_rule_number(
        self, db_session: AsyncSession
    ) -> None:
        repo = RuleRepositoryImpl(db_session)
        country = await _make_country(db_session)
        legislation = await _make_legislation(db_session, country.id)

        created = await repo.create(
            _rule(country.id, legislation.id, rule_number="Rule 5(2)")
        )
        fetched = await repo.get_by_id(created.id)

        assert fetched is not None
        assert fetched.rule_number == "Rule 5(2)"

    async def test_update_can_reassign_to_another_legislation(
        self, db_session: AsyncSession
    ) -> None:
        repo = RuleRepositoryImpl(db_session)
        country = await _make_country(db_session)
        first = await _make_legislation(db_session, country.id)
        second = await _make_legislation(db_session, country.id)
        created = await repo.create(_rule(country.id, first.id))

        created.legislation_id = second.id
        updated = await repo.update(created)

        assert updated.legislation_id == second.id


class TestFilters:
    async def test_search_matches_rule_number(self, db_session: AsyncSession) -> None:
        repo = RuleRepositoryImpl(db_session)
        country = await _make_country(db_session)
        legislation = await _make_legislation(db_session, country.id)
        await repo.create(_rule(country.id, legislation.id, rule_number="Rule 5(2)"))

        rows = await repo.list_all(search="Rule 5")

        assert len(rows) == 1

    async def test_legislation_filter_narrows_across_multiple_legislations(
        self, db_session: AsyncSession
    ) -> None:
        repo = RuleRepositoryImpl(db_session)
        country = await _make_country(db_session)
        legislation_a = await _make_legislation(db_session, country.id)
        legislation_b = await _make_legislation(db_session, country.id)
        await repo.create(_rule(country.id, legislation_a.id, name="Under A"))
        await repo.create(_rule(country.id, legislation_b.id, name="Under B"))

        rows = await repo.list_all(legislation_id=legislation_a.id)

        assert [r.name for r in rows] == ["Under A"]

    async def test_state_filter_narrows_within_a_country(self, db_session: AsyncSession) -> None:
        repo = RuleRepositoryImpl(db_session)
        country = await _make_country(db_session)
        legislation = await _make_legislation(db_session, country.id)
        state = await _make_state(db_session, country.id)
        await repo.create(_rule(country.id, legislation.id, name="Central", state_id=None))
        await repo.create(
            _rule(country.id, legislation.id, name="State-scoped", state_id=state.id)
        )

        rows = await repo.list_all(state_id=state.id)

        assert [r.name for r in rows] == ["State-scoped"]

    async def test_count_matches_the_same_filters_as_list_all(
        self, db_session: AsyncSession
    ) -> None:
        repo = RuleRepositoryImpl(db_session)
        country = await _make_country(db_session)
        legislation = await _make_legislation(db_session, country.id)
        await repo.create(_rule(country.id, legislation.id))
        await repo.create(_rule(country.id, legislation.id))

        assert await repo.count(legislation_id=legislation.id) == 2
