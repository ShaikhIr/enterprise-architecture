"""
StateRepositoryImpl tests, against a real database session.

Country's repository test (`test_country_repository_impl.py`) establishes the
pattern and covers the mechanics `SqlAlchemyRepository` shares across every
master (get_by_id, get_by_code, exists_by_code, delete). This file only adds
what is genuinely State-specific: the `country_id` filter, name uniqueness
scoped to a country rather than global, and the three-table `has_dependents`
check.
"""

import secrets

from sqlalchemy.ext.asyncio import AsyncSession

from src.domain.entities.state import State
from src.infrastructure.database.models.category_of_law_model import CategoryOfLawModel
from src.infrastructure.database.models.country_model import CountryModel
from src.infrastructure.database.repositories.state_repository_impl import (
    StateRepositoryImpl,
)


async def _make_country(session: AsyncSession) -> CountryModel:
    country = CountryModel(
        code=f"C{secrets.token_hex(3).upper()}",
        name=f"Country {secrets.token_hex(3)}",
        created_by="test",
        modified_by="test",
    )
    session.add(country)
    await session.flush()
    return country


def _state(country_id: object, **overrides: object) -> State:
    defaults: dict[str, object] = {
        "code": f"S{secrets.token_hex(3).upper()}",
        "name": f"State {secrets.token_hex(3)}",
        "country_id": country_id,
        "created_by": "test",
        "modified_by": "test",
    }
    defaults.update(overrides)
    return State(**defaults)  # type: ignore[arg-type]


class TestCreateGetUpdateDelete:
    async def test_create_then_get_round_trips_country_id_and_is_union_territory(
        self, db_session: AsyncSession
    ) -> None:
        repo = StateRepositoryImpl(db_session)
        country = await _make_country(db_session)

        created = await repo.create(
            _state(country.id, code="IN-DL", name="Delhi", is_union_territory=True)
        )
        fetched = await repo.get_by_id(created.id)

        assert fetched is not None
        assert fetched.country_id == country.id
        assert fetched.is_union_territory is True

    async def test_update_can_move_a_state_to_another_country(
        self, db_session: AsyncSession
    ) -> None:
        repo = StateRepositoryImpl(db_session)
        origin = await _make_country(db_session)
        destination = await _make_country(db_session)
        created = await repo.create(_state(origin.id))

        created.country_id = destination.id
        updated = await repo.update(created)

        assert updated.country_id == destination.id

    async def test_delete_removes_the_row(self, db_session: AsyncSession) -> None:
        repo = StateRepositoryImpl(db_session)
        country = await _make_country(db_session)
        created = await repo.create(_state(country.id))

        await repo.delete(created.id)

        assert await repo.get_by_id(created.id) is None


class TestNameUniquenessIsScopedToCountry:
    async def test_same_name_in_different_countries_does_not_collide(
        self, db_session: AsyncSession
    ) -> None:
        repo = StateRepositoryImpl(db_session)
        country_a = await _make_country(db_session)
        country_b = await _make_country(db_session)
        await repo.create(_state(country_a.id, name="Central"))

        assert await repo.exists_by_name("Central", country_a.id) is True
        assert await repo.exists_by_name("Central", country_b.id) is False

    async def test_exists_by_name_excludes_its_own_row(
        self, db_session: AsyncSession
    ) -> None:
        repo = StateRepositoryImpl(db_session)
        country = await _make_country(db_session)
        created = await repo.create(_state(country.id, name="Central"))

        assert (
            await repo.exists_by_name("Central", country.id, exclude_id=created.id) is False
        )


class TestListFilteredByCountry:
    async def test_list_all_narrows_to_one_country(self, db_session: AsyncSession) -> None:
        repo = StateRepositoryImpl(db_session)
        country_a = await _make_country(db_session)
        country_b = await _make_country(db_session)
        await repo.create(_state(country_a.id, code="A-1", name="A One"))
        await repo.create(_state(country_b.id, code="B-1", name="B One"))

        rows = await repo.list_all(country_id=country_a.id)

        assert len(rows) == 1
        assert rows[0].country_id == country_a.id

    async def test_count_narrows_the_same_way(self, db_session: AsyncSession) -> None:
        repo = StateRepositoryImpl(db_session)
        country_a = await _make_country(db_session)
        country_b = await _make_country(db_session)
        await repo.create(_state(country_a.id, code="A-1", name="A One"))
        await repo.create(_state(country_b.id, code="B-1", name="B One"))

        assert await repo.count(country_id=country_a.id) == 1


class TestHasDependents:
    async def test_false_with_no_children(self, db_session: AsyncSession) -> None:
        repo = StateRepositoryImpl(db_session)
        country = await _make_country(db_session)
        created = await repo.create(_state(country.id))

        assert await repo.has_dependents(created.id) is False

    async def test_true_when_a_category_of_law_references_it(
        self, db_session: AsyncSession
    ) -> None:
        repo = StateRepositoryImpl(db_session)
        country = await _make_country(db_session)
        created = await repo.create(_state(country.id))
        db_session.add(
            CategoryOfLawModel(
                code=f"CAT{secrets.token_hex(3).upper()}",
                name=f"Category {secrets.token_hex(3)}",
                state_id=created.id,
                created_by="test",
                modified_by="test",
            )
        )
        await db_session.flush()

        assert await repo.has_dependents(created.id) is True
