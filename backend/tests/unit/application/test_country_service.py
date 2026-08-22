"""
Country service tests.

The service is the only layer that enforces code/name uniqueness and the
dependent-record delete guard — the repository just executes queries, and the
API integration tests only prove the wiring end to end. These tests pin the
business rules down directly against a fake repository, in-process.
"""

from uuid import uuid4

import pytest
from master_fakes import FakeCountryRepository

from src.api.v1.schemas.country_schema import CountryCreate, CountryUpdate
from src.application.services.country_service import CountryService
from src.domain.entities.country import Country
from src.domain.entities.user import User
from src.domain.exceptions.domain_exceptions import (
    BusinessRuleViolationError,
    DuplicateEntityError,
    EntityNotFoundError,
)


@pytest.fixture
def repo() -> FakeCountryRepository:
    return FakeCountryRepository()


@pytest.fixture
def service(repo: FakeCountryRepository) -> CountryService:
    return CountryService(repo)


@pytest.fixture
def actor() -> User:
    return User(id=uuid4(), username="alice")


class TestCreate:
    async def test_creates_with_actor_as_audit_fields(
        self, service: CountryService, actor: User
    ) -> None:
        response = await service.create_country(
            CountryCreate(code="IN", name="India"), actor
        )

        assert response.code == "IN"
        assert response.created_by == "alice"
        assert response.modified_by == "alice"

    async def test_duplicate_code_is_rejected(
        self, service: CountryService, actor: User
    ) -> None:
        await service.create_country(CountryCreate(code="IN", name="India"), actor)

        with pytest.raises(DuplicateEntityError) as exc:
            await service.create_country(
                CountryCreate(code="IN", name="Different Name"), actor
            )
        assert exc.value.field == "code"

    async def test_duplicate_name_is_rejected(
        self, service: CountryService, actor: User
    ) -> None:
        await service.create_country(CountryCreate(code="IN", name="India"), actor)

        with pytest.raises(DuplicateEntityError) as exc:
            await service.create_country(CountryCreate(code="ZZ", name="India"), actor)
        assert exc.value.field == "name"

    async def test_code_is_checked_before_name(
        self, service: CountryService, actor: User, repo: FakeCountryRepository
    ) -> None:
        """When both would collide, the code check raises first."""
        await service.create_country(CountryCreate(code="IN", name="India"), actor)

        with pytest.raises(DuplicateEntityError) as exc:
            await service.create_country(CountryCreate(code="IN", name="India"), actor)
        assert exc.value.field == "code"


class TestGet:
    async def test_get_missing_raises_not_found(self, service: CountryService) -> None:
        with pytest.raises(EntityNotFoundError):
            await service.get_country(uuid4())


class TestUpdate:
    async def test_partial_update_leaves_other_fields_untouched(
        self, service: CountryService, actor: User
    ) -> None:
        created = await service.create_country(
            CountryCreate(code="IN", name="India", iso3_code="IND"), actor
        )

        updated = await service.update_country(
            created.id, CountryUpdate(name="Bharat"), actor
        )

        assert updated.name == "Bharat"
        assert updated.code == "IN"
        assert updated.iso3_code == "IND"

    async def test_update_stamps_modifier_and_timestamp(
        self, service: CountryService, actor: User
    ) -> None:
        created = await service.create_country(CountryCreate(code="IN", name="India"), actor)
        before = created.modified_date
        other = User(id=uuid4(), username="bob")

        updated = await service.update_country(created.id, CountryUpdate(name="Bharat"), other)

        assert updated.modified_by == "bob"
        assert updated.modified_date >= before

    async def test_changing_code_to_one_already_taken_is_rejected(
        self, service: CountryService, actor: User
    ) -> None:
        await service.create_country(CountryCreate(code="IN", name="India"), actor)
        other = await service.create_country(CountryCreate(code="ZZ", name="Testland"), actor)

        with pytest.raises(DuplicateEntityError):
            await service.update_country(other.id, CountryUpdate(code="IN"), actor)

    async def test_changing_code_to_its_own_current_value_is_not_a_duplicate(
        self, service: CountryService, actor: User
    ) -> None:
        """Excluding the row's own id from the uniqueness check matters here."""
        created = await service.create_country(CountryCreate(code="IN", name="India"), actor)

        updated = await service.update_country(created.id, CountryUpdate(code="IN"), actor)

        assert updated.code == "IN"

    async def test_update_missing_country_raises_not_found(
        self, service: CountryService, actor: User
    ) -> None:
        with pytest.raises(EntityNotFoundError):
            await service.update_country(uuid4(), CountryUpdate(name="X"), actor)


class TestDelete:
    async def test_delete_removes_the_row(
        self, service: CountryService, actor: User, repo: FakeCountryRepository
    ) -> None:
        created = await service.create_country(CountryCreate(code="IN", name="India"), actor)

        await service.delete_country(created.id)

        assert await repo.get_by_id(created.id) is None

    async def test_delete_blocked_while_dependents_exist(
        self, service: CountryService, actor: User, repo: FakeCountryRepository
    ) -> None:
        created = await service.create_country(CountryCreate(code="IN", name="India"), actor)
        repo.dependents.add(created.id)

        with pytest.raises(BusinessRuleViolationError):
            await service.delete_country(created.id)

        # Refused, not silently skipped: the row is still there afterwards.
        assert await repo.get_by_id(created.id) is not None

    async def test_delete_missing_country_raises_not_found(
        self, service: CountryService
    ) -> None:
        with pytest.raises(EntityNotFoundError):
            await service.delete_country(uuid4())


class TestList:
    async def test_list_reports_total_independent_of_page_size(
        self, service: CountryService, actor: User
    ) -> None:
        for code in ("IN", "US", "GB"):
            await service.create_country(CountryCreate(code=code, name=code), actor)

        page = await service.list_countries(skip=0, limit=1)

        assert len(page.countries) == 1
        assert page.total == 3


def test_country_entity_survives_the_response_round_trip() -> None:
    """CountryResponse.model_validate reads straight off the dataclass entity."""
    from src.api.v1.schemas.country_schema import CountryResponse

    country = Country(code="IN", name="India")
    response = CountryResponse.model_validate(country)
    assert response.code == "IN"
    assert response.id == country.id
