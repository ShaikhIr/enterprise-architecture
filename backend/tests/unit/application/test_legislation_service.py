"""
Legislation service tests.

Legislation is where the jurisdiction chain first has to be validated all the
way up: country and category must exist, and a supplied state must actually
belong to the supplied country. `test_masters_api.py` proves this at the HTTP
boundary with one scenario; these tests exercise every branch of
`_require_state_in_country` and the update-time "country changed but state
wasn't supplied" re-validation directly.
"""


import pytest
from master_fakes import (
    FakeCategoryOfLawRepository,
    FakeCountryRepository,
    FakeLegislationRepository,
    FakeStateRepository,
)

from src.api.v1.schemas.legislation_schema import LegislationCreate, LegislationUpdate
from src.application.services.legislation_service import LegislationService
from src.domain.entities.category_of_law import CategoryOfLaw
from src.domain.entities.country import Country
from src.domain.entities.state import State
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
def state_repo() -> FakeStateRepository:
    return FakeStateRepository()


@pytest.fixture
def category_repo() -> FakeCategoryOfLawRepository:
    return FakeCategoryOfLawRepository()


@pytest.fixture
def repo() -> FakeLegislationRepository:
    return FakeLegislationRepository()


@pytest.fixture
def service(
    repo: FakeLegislationRepository,
    category_repo: FakeCategoryOfLawRepository,
    state_repo: FakeStateRepository,
    country_repo: FakeCountryRepository,
) -> LegislationService:
    return LegislationService(repo, category_repo, state_repo, country_repo)


@pytest.fixture
def actor() -> User:
    return User(id=1, username="alice")


@pytest.fixture
async def country(country_repo: FakeCountryRepository) -> Country:
    return await country_repo.create(Country(code="IN", name="India"))


@pytest.fixture
async def other_country(country_repo: FakeCountryRepository) -> Country:
    return await country_repo.create(Country(code="ZZ", name="Testland"))


@pytest.fixture
async def state(state_repo: FakeStateRepository, country: Country) -> State:
    return await state_repo.create(
        State(code="IN-MH", name="Maharashtra", country_id=country.id)
    )


@pytest.fixture
async def category(category_repo: FakeCategoryOfLawRepository) -> CategoryOfLaw:
    return await category_repo.create(CategoryOfLaw(code="LABOUR", name="Labour Law"))


def _payload(
    country: Country, category: CategoryOfLaw, state: State | None = None
) -> LegislationCreate:
    return LegislationCreate(
        code="IN-FACT-1948",
        name="The Factories Act, 1948",
        category_of_law_id=category.id,
        country_id=country.id,
        state_id=state.id if state else None,
    )


class TestCreate:
    async def test_central_legislation_needs_no_state(
        self,
        service: LegislationService,
        actor: User,
        country: Country,
        category: CategoryOfLaw,
    ) -> None:
        response = await service.create_legislation(_payload(country, category), actor)

        assert response.state_id is None
        assert response.country_id == country.id

    async def test_unknown_country_raises_not_found(
        self, service: LegislationService, actor: User, category: CategoryOfLaw
    ) -> None:
        bogus = Country(id=999_999, code="XX", name="Nowhere")

        with pytest.raises(EntityNotFoundError):
            await service.create_legislation(_payload(bogus, category), actor)

    async def test_unknown_category_raises_not_found(
        self, service: LegislationService, actor: User, country: Country
    ) -> None:
        bogus = CategoryOfLaw(id=999_998, code="XX", name="Nothing")

        with pytest.raises(EntityNotFoundError):
            await service.create_legislation(_payload(country, bogus), actor)

    async def test_state_from_a_different_country_is_rejected(
        self,
        service: LegislationService,
        actor: User,
        other_country: Country,
        state: State,
        category: CategoryOfLaw,
    ) -> None:
        """`state` belongs to `country`, not `other_country`."""
        with pytest.raises(BusinessRuleViolationError) as exc:
            await service.create_legislation(
                _payload(other_country, category, state), actor
            )
        assert "does not belong" in exc.value.message

    async def test_state_matching_its_own_country_is_accepted(
        self,
        service: LegislationService,
        actor: User,
        country: Country,
        state: State,
        category: CategoryOfLaw,
    ) -> None:
        response = await service.create_legislation(
            _payload(country, category, state), actor
        )

        assert response.state_id == state.id

    async def test_unknown_state_id_raises_not_found(
        self,
        service: LegislationService,
        actor: User,
        country: Country,
        category: CategoryOfLaw,
    ) -> None:
        bogus_state = State(id=999_997, code="XX", name="Nowhere", country_id=country.id)

        with pytest.raises(EntityNotFoundError):
            await service.create_legislation(_payload(country, category, bogus_state), actor)

    async def test_duplicate_code_is_rejected(
        self,
        service: LegislationService,
        actor: User,
        country: Country,
        category: CategoryOfLaw,
    ) -> None:
        await service.create_legislation(_payload(country, category), actor)

        with pytest.raises(DuplicateEntityError):
            await service.create_legislation(_payload(country, category), actor)


class TestUpdate:
    async def test_changing_country_without_supplying_state_revalidates_existing_state(
        self,
        service: LegislationService,
        actor: User,
        country: Country,
        other_country: Country,
        state: State,
        category: CategoryOfLaw,
    ) -> None:
        """
        The service must not let a country change silently orphan the existing
        state — this is the branch covered by neither the create path (state is
        always supplied there) nor the HTTP integration suite.
        """
        created = await service.create_legislation(
            _payload(country, category, state), actor
        )

        with pytest.raises(BusinessRuleViolationError):
            await service.update_legislation(
                created.id, LegislationUpdate(country_id=other_country.id), actor
            )

    async def test_changing_country_and_state_together_is_accepted(
        self,
        service: LegislationService,
        actor: User,
        country: Country,
        other_country: Country,
        state: State,
        state_repo: FakeStateRepository,
        category: CategoryOfLaw,
    ) -> None:
        other_state = await state_repo.create(
            State(code="ZZ-CE", name="Central", country_id=other_country.id)
        )
        created = await service.create_legislation(
            _payload(country, category, state), actor
        )

        updated = await service.update_legislation(
            created.id,
            LegislationUpdate(country_id=other_country.id, state_id=other_state.id),
            actor,
        )

        assert updated.country_id == other_country.id
        assert updated.state_id == other_state.id

    async def test_clearing_the_state_makes_it_central(
        self,
        service: LegislationService,
        actor: User,
        country: Country,
        state: State,
        category: CategoryOfLaw,
    ) -> None:
        created = await service.create_legislation(
            _payload(country, category, state), actor
        )

        updated = await service.update_legislation(
            created.id, LegislationUpdate(state_id=None), actor
        )

        assert updated.state_id is None


class TestDelete:
    async def test_delete_blocked_while_rules_reference_it(
        self,
        service: LegislationService,
        actor: User,
        country: Country,
        category: CategoryOfLaw,
        repo: FakeLegislationRepository,
    ) -> None:
        created = await service.create_legislation(_payload(country, category), actor)
        repo.dependents.add(created.id)

        with pytest.raises(BusinessRuleViolationError):
            await service.delete_legislation(created.id)
