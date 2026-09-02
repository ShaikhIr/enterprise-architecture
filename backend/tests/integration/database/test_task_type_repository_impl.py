"""
TaskTypeRepositoryImpl tests, against a real database session.

TaskType is the simplest master: no parent, no `has_dependents`. This file
covers the same generic mechanics as the other five repository tests, so it
serves mainly as the counter-example — proving a repository with no jurisdiction
filters still round-trips and enforces uniqueness correctly, without inheriting
any hidden coupling from the hierarchy the other five sit in.
"""

import secrets

from sqlalchemy.ext.asyncio import AsyncSession

from src.domain.entities.task_type import TaskType
from src.infrastructure.database.repositories.task_type_repository_impl import (
    TaskTypeRepositoryImpl,
)


def _task_type(**overrides: object) -> TaskType:
    defaults: dict[str, object] = {
        "code": f"T{secrets.token_hex(4).upper()}",
        "name": f"Task Type {secrets.token_hex(3)}",
        "created_by": "test",
        "modified_by": "test",
    }
    defaults.update(overrides)
    return TaskType(**defaults)  # type: ignore[arg-type]


class TestCrud:
    async def test_create_then_get_round_trips_description(
        self, db_session: AsyncSession
    ) -> None:
        repo = TaskTypeRepositoryImpl(db_session)

        created = await repo.create(
            _task_type(code="RETURN_FILING", name="Return Filing", description="Periodic filing")
        )
        fetched = await repo.get_by_id(created.id)

        assert fetched is not None
        assert fetched.description == "Periodic filing"

    async def test_update_persists_deactivation(self, db_session: AsyncSession) -> None:
        repo = TaskTypeRepositoryImpl(db_session)
        created = await repo.create(_task_type())

        created.deactivate()
        updated = await repo.update(created)

        assert updated.is_active is False

    async def test_delete_removes_the_row(self, db_session: AsyncSession) -> None:
        repo = TaskTypeRepositoryImpl(db_session)
        created = await repo.create(_task_type())

        await repo.delete(created.id)

        assert await repo.get_by_id(created.id) is None


class TestUniqueness:
    async def test_exists_by_code(self, db_session: AsyncSession) -> None:
        repo = TaskTypeRepositoryImpl(db_session)
        await repo.create(_task_type(code="RETURN_FILING"))

        assert await repo.exists_by_code("RETURN_FILING") is True
        assert await repo.exists_by_code("SOMETHING_ELSE") is False

    async def test_exists_by_name_is_case_insensitive_and_excludes_its_own_row(
        self, db_session: AsyncSession
    ) -> None:
        repo = TaskTypeRepositoryImpl(db_session)
        created = await repo.create(_task_type(name="Return Filing"))

        assert await repo.exists_by_name("RETURN FILING") is True
        assert await repo.exists_by_name("Return Filing", exclude_id=created.id) is False


class TestListAndCount:
    async def test_search_matches_code_or_name(self, db_session: AsyncSession) -> None:
        repo = TaskTypeRepositoryImpl(db_session)
        await repo.create(_task_type(code="RETURN_FILING", name="Return Filing"))
        await repo.create(_task_type(code="AUDIT", name="Audit"))

        rows = await repo.list_all(search="filing")

        assert [r.code for r in rows] == ["RETURN_FILING"]

    async def test_is_active_filter(self, db_session: AsyncSession) -> None:
        repo = TaskTypeRepositoryImpl(db_session)
        active = await repo.create(_task_type(code="ACTIVE_ONE"))
        inactive = await repo.create(_task_type(code="INACTIVE_ONE", is_active=False))

        active_rows = await repo.list_all(is_active=True)
        inactive_rows = await repo.list_all(is_active=False)

        assert any(r.id == active.id for r in active_rows)
        assert not any(r.id == inactive.id for r in active_rows)
        assert any(r.id == inactive.id for r in inactive_rows)
