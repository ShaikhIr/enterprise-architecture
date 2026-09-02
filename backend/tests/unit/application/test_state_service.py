"""
State service tests.

Beyond the generic uniqueness/delete rules every master enforces, State adds one
thing worth its own tests: the parent country must exist, and name uniqueness is
scoped to that country rather than global.
"""


import pytest
from master_fakes import FakeCountryRepository, FakeStateRepository

from src.api.v1.schemas.state_schema import StateCreate, StateUpdate
from src.application.services.state_service import StateService
from src.domain.entities.country import Country
from src.domain.entities.user import User
from src.domain.exceptions.domain_exceptions import (
    BusinessRuleViolationError,
    DuplicateEntityError,
    EntityNotFoundError,
)


@pytest.fixture
def country_repo() -> FakeCountryRepository:
    return FakeCountryRepository()


@pytest.fixture
def repo() -> FakeStateRepository:
    return FakeStateRepository()


@pytest.fixture
def service(repo: FakeStateRepository, country_repo: FakeCountryRepository) -> StateService:
    return StateService(repo, country_repo)


@pytest.fixture
def actor() -> User:
    return User(id=1, username="alice")


@pytest.fixture
async def country(country_repo: FakeCountryRepository) -> Country:
    country = Country(code="IN", name="India")
    return await country_repo.create(country)


class TestCreate:
    async def test_creates_under_an_existing_country(
        self, service: StateService, actor: User, country: Country
    ) -> None:
        response = await service.create_state(
            StateCreate(code="IN-MH", name="Maharashtra", country_id=country.id), actor
        )

        assert response.country_id == country.id

    async def test_unknown_country_raises_not_found(
        self, service: StateService, actor: User
    ) -> None:
        with pytest.raises(EntityNotFoundError):
            await service.create_state(
                StateCreate(code="IN-MH", name="Maharashtra", country_id=999_999), actor
            )

    async def test_duplicate_code_is_rejected_globally(
        self, service: StateService, actor: User, country: Country
    ) -> None:
        await service.create_state(
            StateCreate(code="IN-MH", name="Maharashtra", country_id=country.id), actor
        )

        with pytest.raises(DuplicateEntityError) as exc:
            await service.create_state(
                StateCreate(code="IN-MH", name="Different", country_id=country.id), actor
            )
        assert exc.value.field == "code"

    async def test_duplicate_name_within_same_country_is_rejected(
        self, service: StateService, actor: User, country: Country
    ) -> None:
        await service.create_state(
            StateCreate(code="IN-MH", name="Maharashtra", country_id=country.id), actor
        )

        with pytest.raises(DuplicateEntityError) as exc:
            await service.create_state(
                StateCreate(code="IN-MZ", name="Maharashtra", country_id=country.id), actor
            )
        assert exc.value.field == "name"

    async def test_same_name_in_a_different_country_is_allowed(
        self,
        service: StateService,
        actor: User,
        country: Country,
        country_repo: FakeCountryRepository,
    ) -> None:
        """Name uniqueness is scoped to the owning country, not global."""
        other_country = await country_repo.create(Country(code="ZZ", name="Testland"))
        await service.create_state(
            StateCreate(code="IN-MH", name="Central", country_id=country.id), actor
        )

        response = await service.create_state(
            StateCreate(code="ZZ-CE", name="Central", country_id=other_country.id), actor
        )

        assert response.name == "Central"


class TestUpdate:
    async def test_moving_to_a_new_country_validates_it_exists(
        self, service: StateService, actor: User, country: Country
    ) -> None:
        created = await service.create_state(
            StateCreate(code="IN-MH", name="Maharashtra", country_id=country.id), actor
        )

        with pytest.raises(EntityNotFoundError):
            await service.update_state(created.id, StateUpdate(country_id=999_999), actor)

    async def test_moving_to_a_new_country_re_scopes_name_uniqueness(
        self,
        service: StateService,
        actor: User,
        country: Country,
        country_repo: FakeCountryRepository,
    ) -> None:
        other_country = await country_repo.create(Country(code="ZZ", name="Testland"))
        await service.create_state(
            StateCreate(code="ZZ-CE", name="Central", country_id=other_country.id), actor
        )
        created = await service.create_state(
            StateCreate(code="IN-CE", name="Central", country_id=country.id), actor
        )

        with pytest.raises(DuplicateEntityError):
            await service.update_state(
                created.id, StateUpdate(country_id=other_country.id), actor
            )

    async def test_update_missing_state_raises_not_found(
        self, service: StateService, actor: User
    ) -> None:
        with pytest.raises(EntityNotFoundError):
            await service.update_state(999_999, StateUpdate(name="X"), actor)


class TestDelete:
    async def test_delete_blocked_while_dependents_exist(
        self,
        service: StateService,
        actor: User,
        country: Country,
        repo: FakeStateRepository,
    ) -> None:
        created = await service.create_state(
            StateCreate(code="IN-MH", name="Maharashtra", country_id=country.id), actor
        )
        repo.dependents.add(created.id)

        with pytest.raises(BusinessRuleViolationError):
            await service.delete_state(created.id)


class TestList:
    async def test_list_can_be_narrowed_to_one_country(
        self,
        service: StateService,
        actor: User,
        country: Country,
        country_repo: FakeCountryRepository,
    ) -> None:
        other_country = await country_repo.create(Country(code="ZZ", name="Testland"))
        await service.create_state(
            StateCreate(code="IN-MH", name="Maharashtra", country_id=country.id), actor
        )
        await service.create_state(
            StateCreate(code="ZZ-CE", name="Central", country_id=other_country.id), actor
        )

        page = await service.list_states(country_id=country.id)

        assert page.total == 1
        assert page.states[0].country_id == country.id
