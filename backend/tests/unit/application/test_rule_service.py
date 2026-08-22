"""
Rule service tests.

A rule's jurisdiction must match its parent legislation exactly: same country
always, and the same state whenever the legislation is not central. This is the
one validation `_assert_matches_legislation` performs that has no equivalent
anywhere else in the master hierarchy, so it gets tests of its own on both the
create and update paths.
"""

from uuid import uuid4

import pytest
from master_fakes import (
    FakeCountryRepository,
    FakeLegislationRepository,
    FakeRuleRepository,
    FakeStateRepository,
)

from src.api.v1.schemas.rule_schema import RuleCreate, RuleUpdate
from src.application.services.rule_service import RuleService
from src.domain.entities.country import Country
from src.domain.entities.legislation import Legislation
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
def legislation_repo() -> FakeLegislationRepository:
    return FakeLegislationRepository()


@pytest.fixture
def repo() -> FakeRuleRepository:
    return FakeRuleRepository()


@pytest.fixture
def service(
    repo: FakeRuleRepository,
    legislation_repo: FakeLegislationRepository,
    state_repo: FakeStateRepository,
    country_repo: FakeCountryRepository,
) -> RuleService:
    return RuleService(repo, legislation_repo, state_repo, country_repo)


@pytest.fixture
def actor() -> User:
    return User(id=uuid4(), username="alice")


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
async def central_legislation(
    legislation_repo: FakeLegislationRepository, country: Country
) -> Legislation:
    """A legislation with no state: any rule under it must also have no state."""
    return await legislation_repo.create(
        Legislation(
            code="IN-CENTRAL",
            name="A Central Act",
            category_of_law_id=uuid4(),
            country_id=country.id,
        )
    )


@pytest.fixture
async def state_legislation(
    legislation_repo: FakeLegislationRepository, country: Country, state: State
) -> Legislation:
    """A legislation scoped to one state."""
    return await legislation_repo.create(
        Legislation(
            code="IN-MH-ACT",
            name="A Maharashtra Act",
            category_of_law_id=uuid4(),
            country_id=country.id,
            state_id=state.id,
        )
    )


def _payload(
    legislation: Legislation, country: Country, state: State | None = None
) -> RuleCreate:
    return RuleCreate(
        code="IN-FACT-1948-R5",
        name="Maintenance of health register",
        legislation_id=legislation.id,
        country_id=country.id,
        state_id=state.id if state else None,
    )


class TestCreate:
    async def test_rule_under_central_legislation_needs_no_state(
        self, service: RuleService, actor: User, central_legislation: Legislation, country: Country
    ) -> None:
        response = await service.create_rule(_payload(central_legislation, country), actor)

        assert response.state_id is None

    async def test_rule_country_must_match_legislation_country(
        self,
        service: RuleService,
        actor: User,
        central_legislation: Legislation,
        other_country: Country,
    ) -> None:
        with pytest.raises(BusinessRuleViolationError) as exc:
            await service.create_rule(_payload(central_legislation, other_country), actor)
        assert "country must match" in exc.value.message

    async def test_rule_under_state_legislation_requires_the_same_state(
        self,
        service: RuleService,
        actor: User,
        state_legislation: Legislation,
        country: Country,
    ) -> None:
        """No state supplied at all, while the legislation demands one."""
        with pytest.raises(BusinessRuleViolationError) as exc:
            await service.create_rule(_payload(state_legislation, country), actor)
        assert "state must match" in exc.value.message

    async def test_rule_matching_the_legislation_state_is_accepted(
        self,
        service: RuleService,
        actor: User,
        state_legislation: Legislation,
        country: Country,
        state: State,
    ) -> None:
        response = await service.create_rule(
            _payload(state_legislation, country, state), actor
        )

        assert response.state_id == state.id

    async def test_unknown_legislation_raises_not_found(
        self, service: RuleService, actor: User, country: Country
    ) -> None:
        bogus = Legislation(
            id=uuid4(),
            code="XX",
            name="Nowhere",
            category_of_law_id=uuid4(),
            country_id=country.id,
        )

        with pytest.raises(EntityNotFoundError):
            await service.create_rule(_payload(bogus, country), actor)

    async def test_duplicate_code_is_rejected(
        self,
        service: RuleService,
        actor: User,
        central_legislation: Legislation,
        country: Country,
    ) -> None:
        await service.create_rule(_payload(central_legislation, country), actor)

        with pytest.raises(DuplicateEntityError):
            await service.create_rule(_payload(central_legislation, country), actor)


class TestUpdate:
    async def test_reassigning_legislation_revalidates_the_jurisdiction_match(
        self,
        service: RuleService,
        actor: User,
        central_legislation: Legislation,
        state_legislation: Legislation,
        country: Country,
    ) -> None:
        """
        Moving a central rule under a state-scoped legislation without also
        supplying the matching state must fail the same way create would.
        """
        created = await service.create_rule(_payload(central_legislation, country), actor)

        with pytest.raises(BusinessRuleViolationError):
            await service.update_rule(
                created.id, RuleUpdate(legislation_id=state_legislation.id), actor
            )

    async def test_update_missing_rule_raises_not_found(
        self, service: RuleService, actor: User
    ) -> None:
        with pytest.raises(EntityNotFoundError):
            await service.update_rule(uuid4(), RuleUpdate(name="X"), actor)


class TestDelete:
    async def test_delete_succeeds_with_no_dependent_guard(
        self,
        service: RuleService,
        actor: User,
        central_legislation: Legislation,
        country: Country,
        repo: FakeRuleRepository,
    ) -> None:
        """Rule is the leaf of the hierarchy: nothing references it, so delete is unconditional."""
        created = await service.create_rule(_payload(central_legislation, country), actor)

        await service.delete_rule(created.id)

        assert await repo.get_by_id(created.id) is None
