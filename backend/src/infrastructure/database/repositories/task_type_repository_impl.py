"""
Task type repository implementation (Adapter).
Implements ITaskTypeRepository using SQLAlchemy async.

Primary-key lookup, code lookup, existence check and delete come from
SqlAlchemyRepository; everything below is TaskType-specific.
"""

from typing import Any
from uuid import UUID

from sqlalchemy import ColumnElement, Select, func, or_, select

from src.domain.entities.task_type import TaskType
from src.domain.repositories.task_type_repository import ITaskTypeRepository
from src.infrastructure.database.models.task_type_model import TaskTypeModel
from src.infrastructure.database.repositories.base_repository_impl import (
    SqlAlchemyRepository,
)


class TaskTypeRepositoryImpl(
    SqlAlchemyRepository[TaskType, TaskTypeModel], ITaskTypeRepository
):
    """Concrete implementation of task type persistence using SQLAlchemy."""

    _model = TaskTypeModel

    @staticmethod
    def _code_equals(code: str) -> ColumnElement[bool]:
        return TaskTypeModel.code == code

    # ─── Writes ───

    async def create(self, task_type: TaskType) -> TaskType:
        model = TaskTypeModel(
            id=task_type.id,
            code=task_type.code,
            name=task_type.name,
            description=task_type.description,
            is_active=task_type.is_active,
            created_by=task_type.created_by,
            modified_by=task_type.modified_by,
        )
        self._session.add(model)
        await self._session.flush()
        return self._to_entity(model)

    async def update(self, task_type: TaskType) -> TaskType:
        model = await self._require_model(task_type.id)

        model.code = task_type.code
        model.name = task_type.name
        model.description = task_type.description
        model.is_active = task_type.is_active
        model.modified_by = task_type.modified_by
        model.modified_date = task_type.modified_date

        await self._session.flush()
        return self._to_entity(model)

    # ─── Queries ───

    async def list_all(
        self,
        skip: int = 0,
        limit: int = 100,
        search: str | None = None,
        is_active: bool | None = None,
    ) -> list[TaskType]:
        stmt = self._apply_filters(select(TaskTypeModel), search, is_active)
        stmt = stmt.order_by(TaskTypeModel.name).offset(skip).limit(limit)
        result = await self._session.execute(stmt)
        return [self._to_entity(m) for m in result.scalars().all()]

    async def count(
        self,
        search: str | None = None,
        is_active: bool | None = None,
    ) -> int:
        stmt = self._apply_filters(
            select(func.count()).select_from(TaskTypeModel), search, is_active
        )
        result = await self._session.execute(stmt)
        return int(result.scalar_one())

    async def exists_by_name(self, name: str, exclude_id: UUID | None = None) -> bool:
        stmt = select(TaskTypeModel.id).where(
            func.lower(TaskTypeModel.name) == name.lower()
        )
        if exclude_id is not None:
            stmt = stmt.where(TaskTypeModel.id != exclude_id)
        result = await self._session.execute(stmt)
        return result.scalar_one_or_none() is not None

    # ─── Internals ───

    @staticmethod
    def _apply_filters(
        stmt: Select[Any], search: str | None, is_active: bool | None
    ) -> Select[Any]:
        if search:
            pattern = f"%{search.strip()}%"
            stmt = stmt.where(
                or_(
                    TaskTypeModel.code.ilike(pattern),
                    TaskTypeModel.name.ilike(pattern),
                )
            )
        if is_active is not None:
            stmt = stmt.where(TaskTypeModel.is_active.is_(is_active))
        return stmt

    @staticmethod
    def _to_entity(model: TaskTypeModel) -> TaskType:
        """Map ORM model to domain entity."""
        return TaskType(
            id=model.id,
            code=model.code,
            name=model.name,
            description=model.description,
            is_active=model.is_active,
            created_by=model.created_by,
            created_date=model.created_date,
            modified_by=model.modified_by,
            modified_date=model.modified_date,
        )
