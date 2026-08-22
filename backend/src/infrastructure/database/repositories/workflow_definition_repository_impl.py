"""
Workflow definition repository implementation (Adapter).

Implements IWorkflowDefinitionRepository using SQLAlchemy async. Primary-key
lookup, code lookup, existence check and delete of the definition itself come
from SqlAlchemyRepository; statuses and transitions are handled here.

Repositories flush but never commit — the request-scoped session owns the
transaction boundary.
"""

from typing import Any
from uuid import UUID

from sqlalchemy import ColumnElement, Select, func, or_, select

from src.domain.entities.workflow import (
    WorkflowDefinition,
    WorkflowStatus,
    WorkflowTransition,
)
from src.domain.enums.workflow_enums import WorkflowActionType
from src.domain.repositories.workflow_definition_repository import (
    IWorkflowDefinitionRepository,
)
from src.infrastructure.database.models.workflow_model import (
    WorkflowDefinitionModel,
    WorkflowInstanceModel,
    WorkflowStatusModel,
    WorkflowTransitionModel,
)
from src.infrastructure.database.repositories.base_repository_impl import (
    SqlAlchemyRepository,
)


class WorkflowDefinitionRepositoryImpl(
    SqlAlchemyRepository[WorkflowDefinition, WorkflowDefinitionModel],
    IWorkflowDefinitionRepository,
):
    """Concrete persistence for workflow definitions, statuses and transitions."""

    _model = WorkflowDefinitionModel

    @staticmethod
    def _code_equals(code: str) -> ColumnElement[bool]:
        return WorkflowDefinitionModel.code == code

    # ─── Definition writes ───

    async def create(self, entity: WorkflowDefinition) -> WorkflowDefinition:
        model = WorkflowDefinitionModel(
            id=entity.id,
            code=entity.code,
            name=entity.name,
            description=entity.description,
            entity_type=entity.entity_type,
            version=entity.version,
            is_active=entity.is_active,
            created_by=entity.created_by,
            modified_by=entity.modified_by,
        )
        self._session.add(model)
        await self._session.flush()
        return self._to_entity(model)

    async def update(self, entity: WorkflowDefinition) -> WorkflowDefinition:
        model = await self._require_model(entity.id)

        model.code = entity.code
        model.name = entity.name
        model.description = entity.description
        model.entity_type = entity.entity_type
        model.version = entity.version
        model.is_active = entity.is_active
        model.modified_by = entity.modified_by
        model.modified_date = entity.modified_date

        await self._session.flush()
        return self._to_entity(model)

    # ─── Definition queries ───

    async def list_all(
        self,
        skip: int = 0,
        limit: int = 100,
        search: str | None = None,
        is_active: bool | None = None,
        entity_type: str | None = None,
    ) -> list[WorkflowDefinition]:
        stmt = self._apply_filters(
            select(WorkflowDefinitionModel), search, is_active, entity_type
        )
        stmt = stmt.order_by(WorkflowDefinitionModel.code).offset(skip).limit(limit)
        result = await self._session.execute(stmt)
        return [self._to_entity(m) for m in result.scalars().all()]

    async def count(
        self,
        search: str | None = None,
        is_active: bool | None = None,
        entity_type: str | None = None,
    ) -> int:
        stmt = self._apply_filters(
            select(func.count()).select_from(WorkflowDefinitionModel),
            search,
            is_active,
            entity_type,
        )
        result = await self._session.execute(stmt)
        return int(result.scalar_one())

    async def exists_by_name(self, name: str, exclude_id: UUID | None = None) -> bool:
        stmt = select(WorkflowDefinitionModel.id).where(
            func.lower(WorkflowDefinitionModel.name) == name.lower()
        )
        if exclude_id is not None:
            stmt = stmt.where(WorkflowDefinitionModel.id != exclude_id)
        result = await self._session.execute(stmt)
        return result.scalar_one_or_none() is not None

    async def get_definitions_by_ids(
        self, definition_ids: list[UUID]
    ) -> list[WorkflowDefinition]:
        if not definition_ids:
            return []
        stmt = select(WorkflowDefinitionModel).where(
            WorkflowDefinitionModel.id.in_(set(definition_ids))
        )
        result = await self._session.execute(stmt)
        return [self._to_entity(m) for m in result.scalars().all()]

    # ─── Statuses ───

    async def list_statuses(self, definition_id: UUID) -> list[WorkflowStatus]:
        stmt = (
            select(WorkflowStatusModel)
            .where(WorkflowStatusModel.workflow_definition_id == definition_id)
            .order_by(WorkflowStatusModel.sequence, WorkflowStatusModel.code)
        )
        result = await self._session.execute(stmt)
        return [self._status_to_entity(m) for m in result.scalars().all()]

    async def get_status(self, status_id: UUID) -> WorkflowStatus | None:
        model = await self._get_status_model(status_id)
        return self._status_to_entity(model) if model else None

    async def get_statuses_by_ids(self, status_ids: list[UUID]) -> list[WorkflowStatus]:
        if not status_ids:
            return []
        stmt = select(WorkflowStatusModel).where(
            WorkflowStatusModel.id.in_(set(status_ids))
        )
        result = await self._session.execute(stmt)
        return [self._status_to_entity(m) for m in result.scalars().all()]

    async def get_initial_status(self, definition_id: UUID) -> WorkflowStatus | None:
        stmt = (
            select(WorkflowStatusModel)
            .where(
                WorkflowStatusModel.workflow_definition_id == definition_id,
                WorkflowStatusModel.is_initial.is_(True),
            )
            .order_by(WorkflowStatusModel.sequence)
            .limit(1)
        )
        result = await self._session.execute(stmt)
        model = result.scalar_one_or_none()
        return self._status_to_entity(model) if model else None

    async def exists_status_code(
        self, definition_id: UUID, code: str, exclude_id: UUID | None = None
    ) -> bool:
        stmt = select(WorkflowStatusModel.id).where(
            WorkflowStatusModel.workflow_definition_id == definition_id,
            WorkflowStatusModel.code == code,
        )
        if exclude_id is not None:
            stmt = stmt.where(WorkflowStatusModel.id != exclude_id)
        result = await self._session.execute(stmt)
        return result.scalar_one_or_none() is not None

    async def create_status(self, status: WorkflowStatus) -> WorkflowStatus:
        model = WorkflowStatusModel(
            id=status.id,
            workflow_definition_id=status.workflow_definition_id,
            code=status.code,
            name=status.name,
            is_initial=status.is_initial,
            is_terminal=status.is_terminal,
            sequence=status.sequence,
            created_by=status.created_by,
            modified_by=status.modified_by,
        )
        self._session.add(model)
        await self._session.flush()
        return self._status_to_entity(model)

    async def update_status(self, status: WorkflowStatus) -> WorkflowStatus:
        model = await self._get_status_model(status.id)
        if model is None:
            raise ValueError(f"WorkflowStatus with id {status.id} not found")

        model.code = status.code
        model.name = status.name
        model.is_initial = status.is_initial
        model.is_terminal = status.is_terminal
        model.sequence = status.sequence
        model.modified_by = status.modified_by
        model.modified_date = status.modified_date

        await self._session.flush()
        return self._status_to_entity(model)

    async def delete_status(self, status_id: UUID) -> None:
        model = await self._get_status_model(status_id)
        if model:
            await self._session.delete(model)
            await self._session.flush()

    async def count_transitions_touching_status(self, status_id: UUID) -> int:
        stmt = (
            select(func.count())
            .select_from(WorkflowTransitionModel)
            .where(
                or_(
                    WorkflowTransitionModel.from_status_id == status_id,
                    WorkflowTransitionModel.to_status_id == status_id,
                )
            )
        )
        result = await self._session.execute(stmt)
        return int(result.scalar_one())

    async def count_instances_in_status(self, status_id: UUID) -> int:
        stmt = (
            select(func.count())
            .select_from(WorkflowInstanceModel)
            .where(WorkflowInstanceModel.current_status_id == status_id)
        )
        result = await self._session.execute(stmt)
        return int(result.scalar_one())

    # ─── Transitions ───

    async def list_transitions(self, definition_id: UUID) -> list[WorkflowTransition]:
        stmt = (
            select(WorkflowTransitionModel)
            .where(WorkflowTransitionModel.workflow_definition_id == definition_id)
            .order_by(
                WorkflowTransitionModel.priority, WorkflowTransitionModel.action_code
            )
        )
        result = await self._session.execute(stmt)
        return [self._transition_to_entity(m) for m in result.scalars().all()]

    async def list_transitions_from(
        self, definition_id: UUID, from_status_id: UUID
    ) -> list[WorkflowTransition]:
        stmt = (
            select(WorkflowTransitionModel)
            .where(
                WorkflowTransitionModel.workflow_definition_id == definition_id,
                WorkflowTransitionModel.from_status_id == from_status_id,
            )
            .order_by(
                WorkflowTransitionModel.priority, WorkflowTransitionModel.action_code
            )
        )
        result = await self._session.execute(stmt)
        return [self._transition_to_entity(m) for m in result.scalars().all()]

    async def get_transition(self, transition_id: UUID) -> WorkflowTransition | None:
        model = await self._get_transition_model(transition_id)
        return self._transition_to_entity(model) if model else None

    async def find_transition(
        self, definition_id: UUID, from_status_id: UUID, action_code: str
    ) -> WorkflowTransition | None:
        stmt = (
            select(WorkflowTransitionModel)
            .where(
                WorkflowTransitionModel.workflow_definition_id == definition_id,
                WorkflowTransitionModel.from_status_id == from_status_id,
                WorkflowTransitionModel.action_code == action_code,
            )
            .order_by(WorkflowTransitionModel.priority)
            .limit(1)
        )
        result = await self._session.execute(stmt)
        model = result.scalar_one_or_none()
        return self._transition_to_entity(model) if model else None

    async def exists_transition(
        self, definition_id: UUID, from_status_id: UUID, action_code: str
    ) -> bool:
        stmt = select(WorkflowTransitionModel.id).where(
            WorkflowTransitionModel.workflow_definition_id == definition_id,
            WorkflowTransitionModel.from_status_id == from_status_id,
            WorkflowTransitionModel.action_code == action_code,
        )
        result = await self._session.execute(stmt)
        return result.scalar_one_or_none() is not None

    async def create_transition(
        self, transition: WorkflowTransition
    ) -> WorkflowTransition:
        model = WorkflowTransitionModel(
            id=transition.id,
            workflow_definition_id=transition.workflow_definition_id,
            from_status_id=transition.from_status_id,
            to_status_id=transition.to_status_id,
            action_code=transition.action_code,
            action_type=transition.action_type.value,
            guard_expression=transition.guard_expression,
            requires_comment=transition.requires_comment,
            auto_execute=transition.auto_execute,
            priority=transition.priority,
            created_by=transition.created_by,
            modified_by=transition.modified_by,
        )
        self._session.add(model)
        await self._session.flush()
        return self._transition_to_entity(model)

    async def delete_transition(self, transition_id: UUID) -> None:
        model = await self._get_transition_model(transition_id)
        if model:
            await self._session.delete(model)
            await self._session.flush()

    # ─── Internals ───

    async def _get_status_model(self, status_id: UUID) -> WorkflowStatusModel | None:
        stmt = select(WorkflowStatusModel).where(WorkflowStatusModel.id == status_id)
        result = await self._session.execute(stmt)
        return result.scalar_one_or_none()

    async def _get_transition_model(
        self, transition_id: UUID
    ) -> WorkflowTransitionModel | None:
        stmt = select(WorkflowTransitionModel).where(
            WorkflowTransitionModel.id == transition_id
        )
        result = await self._session.execute(stmt)
        return result.scalar_one_or_none()

    @staticmethod
    def _apply_filters(
        stmt: Select[Any],
        search: str | None,
        is_active: bool | None,
        entity_type: str | None,
    ) -> Select[Any]:
        if search:
            pattern = f"%{search.strip()}%"
            stmt = stmt.where(
                or_(
                    WorkflowDefinitionModel.code.ilike(pattern),
                    WorkflowDefinitionModel.name.ilike(pattern),
                    WorkflowDefinitionModel.entity_type.ilike(pattern),
                )
            )
        if is_active is not None:
            stmt = stmt.where(WorkflowDefinitionModel.is_active.is_(is_active))
        if entity_type:
            stmt = stmt.where(WorkflowDefinitionModel.entity_type == entity_type)
        return stmt

    @staticmethod
    def _to_entity(model: WorkflowDefinitionModel) -> WorkflowDefinition:
        """Map ORM model to domain entity."""
        return WorkflowDefinition(
            id=model.id,
            code=model.code,
            name=model.name,
            description=model.description,
            entity_type=model.entity_type,
            version=model.version,
            is_active=model.is_active,
            created_by=model.created_by,
            created_date=model.created_date,
            modified_by=model.modified_by,
            modified_date=model.modified_date,
        )

    @staticmethod
    def _status_to_entity(model: WorkflowStatusModel) -> WorkflowStatus:
        return WorkflowStatus(
            id=model.id,
            workflow_definition_id=model.workflow_definition_id,
            code=model.code,
            name=model.name,
            is_initial=model.is_initial,
            is_terminal=model.is_terminal,
            sequence=model.sequence,
            created_by=model.created_by,
            created_date=model.created_date,
            modified_by=model.modified_by,
            modified_date=model.modified_date,
        )

    @staticmethod
    def _transition_to_entity(model: WorkflowTransitionModel) -> WorkflowTransition:
        return WorkflowTransition(
            id=model.id,
            workflow_definition_id=model.workflow_definition_id,
            from_status_id=model.from_status_id,
            to_status_id=model.to_status_id,
            action_code=model.action_code,
            action_type=WorkflowActionType(model.action_type),
            guard_expression=model.guard_expression,
            requires_comment=model.requires_comment,
            auto_execute=model.auto_execute,
            priority=model.priority,
            created_by=model.created_by,
            created_date=model.created_date,
            modified_by=model.modified_by,
            modified_date=model.modified_date,
        )
