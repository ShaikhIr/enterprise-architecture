"""
CountryRepositoryImpl tests, against a real database session.

The service unit tests (`tests/unit/application/test_country_service.py`) pin
down the business rules against a fake repository; these tests pin down the
repository itself — the SQL filters, the uniqueness queries, and the entity/model
mapping — none of which a fake, or the HTTP-level `test_masters_api.py` suite,
actually exercises directly.
"""

from uuid import uuid4

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from src.domain.entities.country import Country
from src.infrastructure.database.models.category_of_law_model import CategoryOfLawModel
from src.infrastructure.database.models.legislation_model import LegislationModel
from src.infrastructure.database.models.state_model import StateModel
from src.infrastructure.database.repositories.country_repository_impl import (
    CountryRepositoryImpl,
)


def _country(**overrides: object) -> Country:
    defaults: dict[str, object] = {
        "code": f"C{uuid4().hex[:6].upper()}",
        "name": f"Country {uuid4().hex[:6]}",
        "created_by": "test",
        "modified_by": "test",
    }
    defaults.update(overrides)
    return Country(**defaults)  # type: ignore[arg-type]


class TestCreateAndGet:
    async def test_create_then_get_by_id_round_trips_every_field(
        self, db_session: AsyncSession
    ) -> None:
        repo = CountryRepositoryImpl(db_session)
        country = _country(
            code="IN", name="India", iso3_code="IND", dial_code="+91", currency_code="INR"
        )

        created = await repo.create(country)
        fetched = await repo.get_by_id(created.id)

        assert fetched is not None
        assert fetched.code == "IN"
        assert fetched.iso3_code == "IND"
        assert fetched.dial_code == "+91"
        assert fetched.currency_code == "INR"

    async def test_get_by_code(self, db_session: AsyncSession) -> None:
        repo = CountryRepositoryImpl(db_session)
        await repo.create(_country(code="IN", name="India"))

        fetched = await repo.get_by_code("IN")

        assert fetched is not None
        assert fetched.name == "India"

    async def test_get_by_id_missing_returns_none(self, db_session: AsyncSession) -> None:
        repo = CountryRepositoryImpl(db_session)

        assert await repo.get_by_id(uuid4()) is None


class TestUpdate:
    async def test_update_persists_changed_fields(self, db_session: AsyncSession) -> None:
        repo = CountryRepositoryImpl(db_session)
        created = await repo.create(_country(code="IN", name="India"))

        created.name = "Bharat"
        created.mark_modified("bob")
        updated = await repo.update(created)

        assert updated.name == "Bharat"
        assert updated.modified_by == "bob"

        refetched = await repo.get_by_id(created.id)
        assert refetched is not None
        assert refetched.name == "Bharat"

    async def test_update_missing_row_raises(self, db_session: AsyncSession) -> None:
        repo = CountryRepositoryImpl(db_session)
        ghost = _country(id=uuid4(), code="ZZ", name="Ghost")

        with pytest.raises(ValueError, match="not found"):
            await repo.update(ghost)


class TestDelete:
    async def test_delete_removes_the_row(self, db_session: AsyncSession) -> None:
        repo = CountryRepositoryImpl(db_session)
        created = await repo.create(_country(code="IN", name="India"))

        await repo.delete(created.id)

        assert await repo.get_by_id(created.id) is None

    async def test_delete_of_missing_row_is_silent(self, db_session: AsyncSession) -> None:
        repo = CountryRepositoryImpl(db_session)

        await repo.delete(uuid4())  # must not raise


class TestExists:
    async def test_exists_by_code_true_and_false(self, db_session: AsyncSession) -> None:
        repo = CountryRepositoryImpl(db_session)
        await repo.create(_country(code="IN", name="India"))

        assert await repo.exists_by_code("IN") is True
        assert await repo.exists_by_code("ZZ") is False

    async def test_exists_by_code_excludes_its_own_row(self, db_session: AsyncSession) -> None:
        repo = CountryRepositoryImpl(db_session)
        created = await repo.create(_country(code="IN", name="India"))

        assert await repo.exists_by_code("IN", exclude_id=created.id) is False

    async def test_exists_by_name_is_case_insensitive(self, db_session: AsyncSession) -> None:
        repo = CountryRepositoryImpl(db_session)
        await repo.create(_country(code="IN", name="India"))

        assert await repo.exists_by_name("INDIA") is True
        assert await repo.exists_by_name("india") is True


class TestListAndCount:
    async def test_search_matches_code_name_or_iso3(self, db_session: AsyncSession) -> None:
        repo = CountryRepositoryImpl(db_session)
        await repo.create(_country(code="IN", name="India", iso3_code="IND"))
        await repo.create(_country(code="US", name="United States", iso3_code="USA"))

        by_name = await repo.list_all(search="India")
        by_iso3 = await repo.list_all(search="USA")

        assert [c.code for c in by_name] == ["IN"]
        assert [c.code for c in by_iso3] == ["US"]

    async def test_is_active_filter(self, db_session: AsyncSession) -> None:
        repo = CountryRepositoryImpl(db_session)
        await repo.create(_country(code="IN", name="India", is_active=True))
        await repo.create(_country(code="ZZ", name="Retired", is_active=False))

        active = await repo.list_all(is_active=True)
        inactive = await repo.list_all(is_active=False)

        assert {c.code for c in active} >= {"IN"}
        assert all(c.is_active for c in active)
        assert {c.code for c in inactive} >= {"ZZ"}
        assert all(not c.is_active for c in inactive)

    async def test_pagination_skip_and_limit(self, db_session: AsyncSession) -> None:
        repo = CountryRepositoryImpl(db_session)
        for code in ("AA", "BB", "CC"):
            await repo.create(_country(code=code, name=code))

        page = await repo.list_all(skip=1, limit=1)

        assert len(page) == 1

    async def test_count_matches_list_all_criteria(self, db_session: AsyncSession) -> None:
        repo = CountryRepositoryImpl(db_session)
        await repo.create(_country(code="IN", name="India"))
        await repo.create(_country(code="US", name="United States"))

        total = await repo.count()
        filtered = await repo.count(search="India")

        assert total >= 2
        assert filtered == 1

    async def test_results_are_ordered_by_name(self, db_session: AsyncSession) -> None:
        repo = CountryRepositoryImpl(db_session)
        await repo.create(_country(code="ZZ", name="Zedland"))
        await repo.create(_country(code="AA", name="Aland"))

        rows = await repo.list_all(search="land")

        names = [c.name for c in rows]
        assert names == sorted(names)


class TestHasDependents:
    async def test_false_with_no_children(self, db_session: AsyncSession) -> None:
        repo = CountryRepositoryImpl(db_session)
        created = await repo.create(_country(code="IN", name="India"))

        assert await repo.has_dependents(created.id) is False

    async def test_true_when_a_state_references_it(self, db_session: AsyncSession) -> None:
        repo = CountryRepositoryImpl(db_session)
        country = await repo.create(_country(code="IN", name="India"))
        db_session.add(
            StateModel(
                id=uuid4(),
                code="IN-MH",
                name="Maharashtra",
                country_id=country.id,
                created_by="test",
                modified_by="test",
            )
        )
        await db_session.flush()

        assert await repo.has_dependents(country.id) is True

    async def test_true_when_a_legislation_references_it_directly(
        self, db_session: AsyncSession
    ) -> None:
        """Even with no state, a central legislation alone is enough to block delete."""
        repo = CountryRepositoryImpl(db_session)
        country = await repo.create(_country(code="IN", name="India"))
        category = CategoryOfLawModel(
            id=uuid4(),
            code=f"CAT{uuid4().hex[:6].upper()}",
            name=f"Category {uuid4().hex[:6]}",
            created_by="test",
            modified_by="test",
        )
        db_session.add(category)
        await db_session.flush()
        db_session.add(
            LegislationModel(
                id=uuid4(),
                code="IN-ACT",
                name="An Act",
                category_of_law_id=category.id,
                country_id=country.id,
                state_id=None,
                created_by="test",
                modified_by="test",
            )
        )
        await db_session.flush()

        assert await repo.has_dependents(country.id) is True
