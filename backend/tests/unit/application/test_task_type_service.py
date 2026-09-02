"""
Task type service tests.

TaskType is the simplest master — independent of the jurisdiction hierarchy, no
parent to validate, no dependent-record delete guard. These tests exist mainly
so the uniqueness and partial-update rules every master shares are pinned down
for this one too, rather than assumed by analogy with Country/State.
"""

import pytest
from master_fakes import FakeTaskTypeRepository

from src.api.v1.schemas.task_type_schema import TaskTypeCreate, TaskTypeUpdate
from src.application.services.task_type_service import TaskTypeService
from src.domain.entities.user import User
from src.domain.exceptions.domain_exceptions import (
    DuplicateEntityError,
    EntityNotFoundError,
)


@pytest.fixture
def repo() -> FakeTaskTypeRepository:
    return FakeTaskTypeRepository()


@pytest.fixture
def service(repo: FakeTaskTypeRepository) -> TaskTypeService:
    return TaskTypeService(repo)


@pytest.fixture
def actor() -> User:
    return User(id=1, username="alice")


class TestCreate:
    async def test_creates_a_task_type(self, service: TaskTypeService, actor: User) -> None:
        response = await service.create_task_type(
            TaskTypeCreate(code="RETURN_FILING", name="Return Filing"), actor
        )

        assert response.code == "RETURN_FILING"
        assert response.is_active is True

    async def test_duplicate_code_is_rejected(
        self, service: TaskTypeService, actor: User
    ) -> None:
        await service.create_task_type(
            TaskTypeCreate(code="RETURN_FILING", name="Return Filing"), actor
        )

        with pytest.raises(DuplicateEntityError) as exc:
            await service.create_task_type(
                TaskTypeCreate(code="RETURN_FILING", name="Different"), actor
            )
        assert exc.value.field == "code"

    async def test_duplicate_name_is_rejected(
        self, service: TaskTypeService, actor: User
    ) -> None:
        await service.create_task_type(
            TaskTypeCreate(code="RF", name="Return Filing"), actor
        )

        with pytest.raises(DuplicateEntityError) as exc:
            await service.create_task_type(
                TaskTypeCreate(code="RF2", name="Return Filing"), actor
            )
        assert exc.value.field == "name"


class TestUpdate:
    async def test_deactivating_leaves_other_fields_untouched(
        self, service: TaskTypeService, actor: User
    ) -> None:
        created = await service.create_task_type(
            TaskTypeCreate(code="RETURN_FILING", name="Return Filing"), actor
        )

        updated = await service.update_task_type(
            created.id, TaskTypeUpdate(is_active=False), actor
        )

        assert updated.is_active is False
        assert updated.code == "RETURN_FILING"

    async def test_update_missing_task_type_raises_not_found(
        self, service: TaskTypeService, actor: User
    ) -> None:
        with pytest.raises(EntityNotFoundError):
            await service.update_task_type(999_999, TaskTypeUpdate(name="X"), actor)


class TestDelete:
    async def test_delete_removes_the_row(
        self, service: TaskTypeService, actor: User, repo: FakeTaskTypeRepository
    ) -> None:
        created = await service.create_task_type(
            TaskTypeCreate(code="RETURN_FILING", name="Return Filing"), actor
        )

        await service.delete_task_type(created.id)

        assert await repo.get_by_id(created.id) is None

    async def test_delete_missing_task_type_raises_not_found(
        self, service: TaskTypeService
    ) -> None:
        with pytest.raises(EntityNotFoundError):
            await service.delete_task_type(999_999)
