"""
Workflow instance repository port.

Runtime side of the engine: the instances themselves plus their append-only
history trail. History has no update or delete method by design — the audit
record of what happened must not be rewritable through the application.
"""

from abc import ABC, abstractmethod
from uuid import UUID

from src.domain.entities.workflow import WorkflowHistoryEntry, WorkflowInstance


class IWorkflowInstanceRepository(ABC):
    """Persistence contract for workflow instances and their history."""

    # ─── Instances ───

    @abstractmethod
    async def get_by_id(self, instance_id: UUID) -> WorkflowInstance | None:
        """Load one instance by primary key."""
        ...

    @abstractmethod
    async def create(self, instance: WorkflowInstance) -> WorkflowInstance:
        """Persist a new instance."""
        ...

    @abstractmethod
    async def update(self, instance: WorkflowInstance) -> WorkflowInstance:
        """Update an existing instance."""
        ...

    @abstractmethod
    async def list_all(
        self,
        skip: int = 0,
        limit: int = 100,
        entity_type: str | None = None,
        entity_id: UUID | None = None,
        definition_id: UUID | None = None,
        status_id: UUID | None = None,
        initiated_by: UUID | None = None,
        is_completed: bool | None = None,
    ) -> list[WorkflowInstance]:
        """List instances newest first, narrowed by any combination of filters."""
        ...

    @abstractmethod
    async def count(
        self,
        entity_type: str | None = None,
        entity_id: UUID | None = None,
        definition_id: UUID | None = None,
        status_id: UUID | None = None,
        initiated_by: UUID | None = None,
        is_completed: bool | None = None,
    ) -> int:
        """Count instances matching the same criteria as `list_all`."""
        ...

    @abstractmethod
    async def get_open_for_entity(
        self, entity_type: str, entity_id: UUID
    ) -> WorkflowInstance | None:
        """
        The still-running instance for a business record, if any.

        Lets callers refuse to start a second workflow over a record that is
        already in flight.
        """
        ...

    # ─── History ───

    @abstractmethod
    async def add_history(self, entry: WorkflowHistoryEntry) -> WorkflowHistoryEntry:
        """Append one immutable history record."""
        ...

    @abstractmethod
    async def list_history(self, instance_id: UUID) -> list[WorkflowHistoryEntry]:
        """History for an instance, newest first."""
        ...
