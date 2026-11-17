"""
Workflow instance repository implementation (Adapter).

Does not extend SqlAlchemyRepository: instances have no unique business code, so
the code-keyed mechanics that base class provides (get_by_code, exists_by_code)
do not apply.

Repositories flush but never commit — the request-scoped session owns the
transaction boundary.
"""

from typing import Any

from sqlalchemy import Select, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.domain.entities.workflow import WorkflowHistoryEntry, WorkflowInstance
from src.domain.repositories.workflow_instance_repository import (
    IWorkflowInstanceRepository,
)
from src.infrastructure.database.models.workflow_model import (
    WorkflowHistoryModel,
    WorkflowInstanceModel,
)


class WorkflowInstanceRepositoryImpl(IWorkflowInstanceRepository):
    """Concrete persistence for workflow instances and their history trail."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    # ─── Instances ───

    async def get_by_id(self, instance_id: int) -> WorkflowInstance | None:
        model = await self._get_model(instance_id)
        return self._to_entity(model) if model else None

    async def create(self, instance: WorkflowInstance) -> WorkflowInstance:
        model = WorkflowInstanceModel(
            workflow_definition_id=instance.workflow_definition_id,
            entity_type=instance.entity_type,
            entity_id=instance.entity_id,
            current_status_id=instance.current_status_id,
            initiated_by=instance.initiated_by,
            priority=instance.priority,
            due_date=instance.due_date,
            started_at=instance.started_at,
            completed_at=instance.completed_at,
            extra_data=instance.extra_data,
            approval_level=instance.approval_level,
            created_by=instance.created_by,
            modified_by=instance.modified_by,
        )
        self._session.add(model)
        await self._session.flush()
        return self._to_entity(model)

    async def update(self, instance: WorkflowInstance) -> WorkflowInstance:
        model = await self._get_model(instance.id)
        if model is None:
            raise ValueError(f"WorkflowInstance with id {instance.id} not found")

        model.current_status_id = instance.current_status_id
        model.priority = instance.priority
        model.due_date = instance.due_date
        model.completed_at = instance.completed_at
        model.extra_data = instance.extra_data
        model.approval_level = instance.approval_level
        model.modified_by = instance.modified_by
        model.modified_date = instance.modified_date

        await self._session.flush()
        return self._to_entity(model)

    async def list_all(
        self,
        skip: int = 0,
        limit: int = 100,
        entity_type: str | None = None,
        entity_id: int | None = None,
        definition_id: int | None = None,
        status_id: int | None = None,
        initiated_by: int | None = None,
        is_completed: bool | None = None,
    ) -> list[WorkflowInstance]:
        stmt = self._apply_filters(
            select(WorkflowInstanceModel),
            entity_type,
            entity_id,
            definition_id,
            status_id,
            initiated_by,
            is_completed,
        )
        stmt = (
            stmt.order_by(WorkflowInstanceModel.started_at.desc()).offset(skip).limit(limit)
        )
        result = await self._session.execute(stmt)
        return [self._to_entity(m) for m in result.scalars().all()]

    async def count(
        self,
        entity_type: str | None = None,
        entity_id: int | None = None,
        definition_id: int | None = None,
        status_id: int | None = None,
        initiated_by: int | None = None,
        is_completed: bool | None = None,
    ) -> int:
        stmt = self._apply_filters(
            select(func.count()).select_from(WorkflowInstanceModel),
            entity_type,
            entity_id,
            definition_id,
            status_id,
            initiated_by,
            is_completed,
        )
        result = await self._session.execute(stmt)
        return int(result.scalar_one())

    async def get_open_for_entity(
        self, entity_type: str, entity_id: int
    ) -> WorkflowInstance | None:
        stmt = (
            select(WorkflowInstanceModel)
            .where(
                WorkflowInstanceModel.entity_type == entity_type,
                WorkflowInstanceModel.entity_id == entity_id,
                WorkflowInstanceModel.completed_at.is_(None),
            )
            .order_by(WorkflowInstanceModel.started_at.desc())
            .limit(1)
        )
        result = await self._session.execute(stmt)
        model = result.scalar_one_or_none()
        return self._to_entity(model) if model else None

    # ─── History ───

    async def add_history(self, entry: WorkflowHistoryEntry) -> WorkflowHistoryEntry:
        model = WorkflowHistoryModel(
            instance_id=entry.instance_id,
            from_status_id=entry.from_status_id,
            to_status_id=entry.to_status_id,
            action_code=entry.action_code,
            actor_id=entry.actor_id,
            actor_username=entry.actor_username,
            comments=entry.comments,
            extra_data=entry.extra_data,
            ip_address=entry.ip_address,
            created_at=entry.created_at,
        )
        self._session.add(model)
        await self._session.flush()
        return self._history_to_entity(model)

    async def list_history(self, instance_id: int) -> list[WorkflowHistoryEntry]:
        stmt = (
            select(WorkflowHistoryModel)
            .where(WorkflowHistoryModel.instance_id == instance_id)
            .order_by(WorkflowHistoryModel.created_at.desc())
        )
        result = await self._session.execute(stmt)
        return [self._history_to_entity(m) for m in result.scalars().all()]

    # ─── Internals ───

    async def _get_model(self, instance_id: int) -> WorkflowInstanceModel | None:
        stmt = select(WorkflowInstanceModel).where(
            WorkflowInstanceModel.id == instance_id
        )
        result = await self._session.execute(stmt)
        return result.scalar_one_or_none()

    @staticmethod
    def _apply_filters(
        stmt: Select[Any],
        entity_type: str | None,
        entity_id: int | None,
        definition_id: int | None,
        status_id: int | None,
        initiated_by: int | None,
        is_completed: bool | None,
    ) -> Select[Any]:
        if entity_type:
            stmt = stmt.where(WorkflowInstanceModel.entity_type == entity_type)
        if entity_id is not None:
            stmt = stmt.where(WorkflowInstanceModel.entity_id == entity_id)
        if definition_id is not None:
            stmt = stmt.where(
                WorkflowInstanceModel.workflow_definition_id == definition_id
            )
        if status_id is not None:
            stmt = stmt.where(WorkflowInstanceModel.current_status_id == status_id)
        if initiated_by is not None:
            stmt = stmt.where(WorkflowInstanceModel.initiated_by == initiated_by)
        if is_completed is not None:
            # "Completed" is derived from the timestamp rather than stored twice,
            # so there is no flag that can drift out of step with it.
            stmt = stmt.where(
                WorkflowInstanceModel.completed_at.is_not(None)
                if is_completed
                else WorkflowInstanceModel.completed_at.is_(None)
            )
        return stmt

    @staticmethod
    def _to_entity(model: WorkflowInstanceModel) -> WorkflowInstance:
        """Map ORM model to domain entity."""
        return WorkflowInstance(
            id=model.id,
            workflow_definition_id=model.workflow_definition_id,
            entity_type=model.entity_type,
            entity_id=model.entity_id,
            current_status_id=model.current_status_id,
            initiated_by=model.initiated_by,
            priority=model.priority,
            due_date=model.due_date,
            started_at=model.started_at,
            completed_at=model.completed_at,
            extra_data=dict(model.extra_data or {}),
            approval_level=model.approval_level,
            created_by=model.created_by,
            created_date=model.created_date,
            modified_by=model.modified_by,
            modified_date=model.modified_date,
        )

    @staticmethod
    def _history_to_entity(model: WorkflowHistoryModel) -> WorkflowHistoryEntry:
        return WorkflowHistoryEntry(
            id=model.id,
            instance_id=model.instance_id,
            from_status_id=model.from_status_id,
            to_status_id=model.to_status_id,
            action_code=model.action_code,
            actor_id=model.actor_id,
            actor_username=model.actor_username,
            comments=model.comments,
            extra_data=dict(model.extra_data or {}),
            ip_address=model.ip_address,
            created_at=model.created_at,
        )
