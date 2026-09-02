"""
CategoryOfLawRepositoryImpl tests, against a real database session.

The one thing worth its own coverage here: `exists_by_name`'s NULL-vs-value
handling for `state_id`. `category.state_id == state_id` in SQL would silently
match nothing when `state_id` is NULL — SQL's `NULL = NULL` is not true — so the
repository has to special-case it with `.is_(None)`. That branch has no
equivalent in Country/State, and untested it would let two country-wide
categories share a name a business rule up in `CategoryOfLawService` believes
it has already rejected.
"""

import secrets

from sqlalchemy.ext.asyncio import AsyncSession

from src.domain.entities.category_of_law import CategoryOfLaw
from src.infrastructure.database.models.country_model import CountryModel
from src.infrastructure.database.models.legislation_model import LegislationModel
from src.infrastructure.database.models.state_model import StateModel
from src.infrastructure.database.repositories.category_of_law_repository_impl import (
    CategoryOfLawRepositoryImpl,
)


async def _make_state(session: AsyncSession) -> StateModel:
    country = CountryModel(
        code=f"C{secrets.token_hex(3).upper()}", name=f"Country {secrets.token_hex(3)}",
        created_by="test", modified_by="test",
    )
    session.add(country)
    await session.flush()
    state = StateModel(
        code=f"S{secrets.token_hex(3).upper()}", name=f"State {secrets.token_hex(3)}",
        country_id=country.id, created_by="test", modified_by="test",
    )
    session.add(state)
    await session.flush()
    return state


def _category(**overrides: object) -> CategoryOfLaw:
    defaults: dict[str, object] = {
        "code": f"CAT{secrets.token_hex(3).upper()}",
        "name": f"Category {secrets.token_hex(3)}",
        "created_by": "test",
        "modified_by": "test",
    }
    defaults.update(overrides)
    return CategoryOfLaw(**defaults)  # type: ignore[arg-type]


class TestCrud:
    async def test_create_then_get_round_trips_state_id(self, db_session: AsyncSession) -> None:
        repo = CategoryOfLawRepositoryImpl(db_session)
        state = await _make_state(db_session)

        created = await repo.create(_category(name="Labour Law", state_id=state.id))
        fetched = await repo.get_by_id(created.id)

        assert fetched is not None
        assert fetched.state_id == state.id

    async def test_country_wide_category_has_no_state(self, db_session: AsyncSession) -> None:
        repo = CategoryOfLawRepositoryImpl(db_session)

        created = await repo.create(_category(name="Labour Law"))

        assert created.state_id is None

    async def test_update_can_clear_the_state(self, db_session: AsyncSession) -> None:
        repo = CategoryOfLawRepositoryImpl(db_session)
        state = await _make_state(db_session)
        created = await repo.create(_category(state_id=state.id))

        created.state_id = None
        updated = await repo.update(created)

        assert updated.state_id is None


class TestNameUniquenessAcrossStateScope:
    async def test_two_country_wide_categories_cannot_share_a_name(
        self, db_session: AsyncSession
    ) -> None:
        repo = CategoryOfLawRepositoryImpl(db_session)
        await repo.create(_category(name="Labour Law"))

        assert await repo.exists_by_name("Labour Law", state_id=None) is True

    async def test_state_scoped_and_country_wide_names_do_not_collide(
        self, db_session: AsyncSession
    ) -> None:
        repo = CategoryOfLawRepositoryImpl(db_session)
        state = await _make_state(db_session)
        await repo.create(_category(name="Labour Law"))  # country-wide

        assert await repo.exists_by_name("Labour Law", state_id=state.id) is False

    async def test_two_categories_in_different_states_do_not_collide(
        self, db_session: AsyncSession
    ) -> None:
        repo = CategoryOfLawRepositoryImpl(db_session)
        state_a = await _make_state(db_session)
        state_b = await _make_state(db_session)
        await repo.create(_category(name="Labour Law", state_id=state_a.id))

        assert await repo.exists_by_name("Labour Law", state_id=state_b.id) is False
        assert await repo.exists_by_name("Labour Law", state_id=state_a.id) is True

    async def test_exists_by_name_excludes_its_own_row(self, db_session: AsyncSession) -> None:
        repo = CategoryOfLawRepositoryImpl(db_session)
        created = await repo.create(_category(name="Labour Law"))

        assert (
            await repo.exists_by_name("Labour Law", state_id=None, exclude_id=created.id)
            is False
        )


class TestListFilteredByState:
    async def test_list_all_narrows_to_one_state(self, db_session: AsyncSession) -> None:
        repo = CategoryOfLawRepositoryImpl(db_session)
        state = await _make_state(db_session)
        await repo.create(_category(name="State Scoped", state_id=state.id))
        await repo.create(_category(name="Country Wide"))

        rows = await repo.list_all(state_id=state.id)

        assert len(rows) == 1
        assert rows[0].name == "State Scoped"


class TestHasDependents:
    async def test_true_when_a_legislation_references_it(self, db_session: AsyncSession) -> None:
        repo = CategoryOfLawRepositoryImpl(db_session)
        category = await repo.create(_category())
        country = CountryModel(
            code=f"C{secrets.token_hex(3).upper()}", name=f"Country {secrets.token_hex(3)}",
            created_by="test", modified_by="test",
        )
        db_session.add(country)
        await db_session.flush()
        db_session.add(
            LegislationModel(
                code="IN-ACT", name="An Act",
                category_of_law_id=category.id, country_id=country.id,
                created_by="test", modified_by="test",
            )
        )
        await db_session.flush()

        assert await repo.has_dependents(category.id) is True

    async def test_false_with_no_legislation(self, db_session: AsyncSession) -> None:
        repo = CategoryOfLawRepositoryImpl(db_session)
        category = await repo.create(_category())

        assert await repo.has_dependents(category.id) is False
