"""
Category of law service tests.

The distinguishing rule here is the optional state scope: a category may be
country-wide (`state_id=None`) or state-specific, and name uniqueness is scoped
to whichever it is — two categories can share a name if one is central and the
other belongs to a state, but not two centrals or two in the same state.
"""

from uuid import uuid4

import pytest
from master_fakes import FakeCategoryOfLawRepository, FakeStateRepository

from src.api.v1.schemas.category_of_law_schema import (
    CategoryOfLawCreate,
    CategoryOfLawUpdate,
)
from src.application.services.category_of_law_service import CategoryOfLawService
from src.domain.entities.state import State
from src.domain.entities.user import User
from src.domain.exceptions.domain_exceptions import (
    BusinessRuleViolationError,
    DuplicateEntityError,
    EntityNotFoundError,
)


@pytest.fixture
def state_repo() -> FakeStateRepository:
    return FakeStateRepository()


@pytest.fixture
def repo() -> FakeCategoryOfLawRepository:
    return FakeCategoryOfLawRepository()


@pytest.fixture
def service(
    repo: FakeCategoryOfLawRepository, state_repo: FakeStateRepository
) -> CategoryOfLawService:
    return CategoryOfLawService(repo, state_repo)


@pytest.fixture
def actor() -> User:
    return User(id=uuid4(), username="alice")


@pytest.fixture
async def state(state_repo: FakeStateRepository) -> State:
    return await state_repo.create(State(code="IN-MH", name="Maharashtra", country_id=uuid4()))


class TestCreate:
    async def test_country_wide_category_needs_no_state(
        self, service: CategoryOfLawService, actor: User
    ) -> None:
        response = await service.create_category(
            CategoryOfLawCreate(code="LABOUR", name="Labour Law"), actor
        )

        assert response.state_id is None

    async def test_state_specific_category_validates_the_state(
        self, service: CategoryOfLawService, actor: User
    ) -> None:
        with pytest.raises(EntityNotFoundError):
            await service.create_category(
                CategoryOfLawCreate(code="LABOUR", name="Labour Law", state_id=uuid4()),
                actor,
            )

    async def test_state_specific_category_with_existing_state(
        self, service: CategoryOfLawService, actor: User, state: State
    ) -> None:
        response = await service.create_category(
            CategoryOfLawCreate(code="LABOUR", name="Labour Law", state_id=state.id), actor
        )

        assert response.state_id == state.id

    async def test_same_name_central_and_state_specific_can_coexist(
        self, service: CategoryOfLawService, actor: User, state: State
    ) -> None:
        await service.create_category(
            CategoryOfLawCreate(code="LABOUR-C", name="Labour Law"), actor
        )

        response = await service.create_category(
            CategoryOfLawCreate(code="LABOUR-S", name="Labour Law", state_id=state.id),
            actor,
        )

        assert response.name == "Labour Law"

    async def test_duplicate_name_within_the_same_state_is_rejected(
        self, service: CategoryOfLawService, actor: User, state: State
    ) -> None:
        await service.create_category(
            CategoryOfLawCreate(code="LABOUR-1", name="Labour Law", state_id=state.id), actor
        )

        with pytest.raises(DuplicateEntityError):
            await service.create_category(
                CategoryOfLawCreate(code="LABOUR-2", name="Labour Law", state_id=state.id),
                actor,
            )

    async def test_duplicate_name_when_both_central_is_rejected(
        self, service: CategoryOfLawService, actor: User
    ) -> None:
        await service.create_category(
            CategoryOfLawCreate(code="LABOUR-1", name="Labour Law"), actor
        )

        with pytest.raises(DuplicateEntityError):
            await service.create_category(
                CategoryOfLawCreate(code="LABOUR-2", name="Labour Law"), actor
            )


class TestUpdate:
    async def test_moving_from_state_specific_to_central(
        self, service: CategoryOfLawService, actor: User, state: State
    ) -> None:
        created = await service.create_category(
            CategoryOfLawCreate(code="LABOUR", name="Labour Law", state_id=state.id), actor
        )

        updated = await service.update_category(
            created.id, CategoryOfLawUpdate(state_id=None), actor
        )

        assert updated.state_id is None

    async def test_moving_to_an_unknown_state_raises_not_found(
        self, service: CategoryOfLawService, actor: User
    ) -> None:
        created = await service.create_category(
            CategoryOfLawCreate(code="LABOUR", name="Labour Law"), actor
        )

        with pytest.raises(EntityNotFoundError):
            await service.update_category(
                created.id, CategoryOfLawUpdate(state_id=uuid4()), actor
            )

    async def test_description_only_update_leaves_scope_untouched(
        self, service: CategoryOfLawService, actor: User, state: State
    ) -> None:
        created = await service.create_category(
            CategoryOfLawCreate(code="LABOUR", name="Labour Law", state_id=state.id), actor
        )

        updated = await service.update_category(
            created.id, CategoryOfLawUpdate(description="Employment law"), actor
        )

        assert updated.state_id == state.id
        assert updated.description == "Employment law"


class TestDelete:
    async def test_delete_blocked_while_legislations_reference_it(
        self,
        service: CategoryOfLawService,
        actor: User,
        repo: FakeCategoryOfLawRepository,
    ) -> None:
        created = await service.create_category(
            CategoryOfLawCreate(code="LABOUR", name="Labour Law"), actor
        )
        repo.dependents.add(created.id)

        with pytest.raises(BusinessRuleViolationError):
            await service.delete_category(created.id)
