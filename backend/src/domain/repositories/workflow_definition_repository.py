"""
Workflow definition repository port.

Covers the three configuration tables that make up a state machine — the
definition itself, its statuses and its transitions. They share one port because
they are never useful apart: a status without its definition is meaningless, and
the state machine reads all three together on every action.
"""

from abc import abstractmethod
from uuid import UUID

from src.domain.entities.workflow import (
    WorkflowDefinition,
    WorkflowStatus,
    WorkflowTransition,
)
from src.domain.repositories.base_repository import IRepository


class IWorkflowDefinitionRepository(IRepository[WorkflowDefinition]):
    """Persistence contract for workflow definitions, statuses and transitions."""

    # ─── Definitions ───

    @abstractmethod
    async def list_all(
        self,
        skip: int = 0,
        limit: int = 100,
        search: str | None = None,
        is_active: bool | None = None,
        entity_type: str | None = None,
    ) -> list[WorkflowDefinition]:
        """List definitions, optionally narrowed to one business entity type."""
        ...

    @abstractmethod
    async def count(
        self,
        search: str | None = None,
        is_active: bool | None = None,
        entity_type: str | None = None,
    ) -> int:
        """Count definitions matching the same criteria as `list_all`."""
        ...

    @abstractmethod
    async def exists_by_name(self, name: str, exclude_id: UUID | None = None) -> bool:
        """Check whether a definition name is taken, optionally ignoring one row."""
        ...

    @abstractmethod
    async def get_definitions_by_ids(
        self, definition_ids: list[UUID]
    ) -> list[WorkflowDefinition]:
        """
        Batch-load definitions by primary key.

        Lets a page of instances resolve its definition names in one query instead
        of one per row.
        """
        ...

    # ─── Statuses ───

    @abstractmethod
    async def list_statuses(self, definition_id: UUID) -> list[WorkflowStatus]:
        """All statuses of a definition, ordered by sequence."""
        ...

    @abstractmethod
    async def get_status(self, status_id: UUID) -> WorkflowStatus | None:
        """Load one status by primary key."""
        ...

    @abstractmethod
    async def get_statuses_by_ids(self, status_ids: list[UUID]) -> list[WorkflowStatus]:
        """Batch-load statuses by primary key, for the same reason as definitions."""
        ...

    @abstractmethod
    async def get_initial_status(self, definition_id: UUID) -> WorkflowStatus | None:
        """The status new instances start in, or None when none is flagged."""
        ...

    @abstractmethod
    async def exists_status_code(
        self, definition_id: UUID, code: str, exclude_id: UUID | None = None
    ) -> bool:
        """Check whether a status code is already used within one definition."""
        ...

    @abstractmethod
    async def create_status(self, status: WorkflowStatus) -> WorkflowStatus:
        """Persist a new status."""
        ...

    @abstractmethod
    async def update_status(self, status: WorkflowStatus) -> WorkflowStatus:
        """Update an existing status."""
        ...

    @abstractmethod
    async def delete_status(self, status_id: UUID) -> None:
        """Delete a status by primary key."""
        ...

    @abstractmethod
    async def count_transitions_touching_status(self, status_id: UUID) -> int:
        """
        How many transitions reference a status as source or target.

        Used to reject deleting a status that is still wired into the machine,
        rather than relying on a foreign key error surfacing as a 500.
        """
        ...

    @abstractmethod
    async def count_instances_in_status(self, status_id: UUID) -> int:
        """How many live instances currently sit in a status."""
        ...

    # ─── Transitions ───

    @abstractmethod
    async def list_transitions(self, definition_id: UUID) -> list[WorkflowTransition]:
        """All transitions of a definition, ordered by priority."""
        ...

    @abstractmethod
    async def list_transitions_from(
        self, definition_id: UUID, from_status_id: UUID
    ) -> list[WorkflowTransition]:
        """Transitions leaving one status, ordered by priority."""
        ...

    @abstractmethod
    async def get_transition(self, transition_id: UUID) -> WorkflowTransition | None:
        """Load one transition by primary key."""
        ...

    @abstractmethod
    async def find_transition(
        self, definition_id: UUID, from_status_id: UUID, action_code: str
    ) -> WorkflowTransition | None:
        """The transition an action triggers from a state, or None if disallowed."""
        ...

    @abstractmethod
    async def exists_transition(
        self, definition_id: UUID, from_status_id: UUID, action_code: str
    ) -> bool:
        """Check whether an action is already wired up from a state."""
        ...

    @abstractmethod
    async def create_transition(
        self, transition: WorkflowTransition
    ) -> WorkflowTransition:
        """Persist a new transition."""
        ...

    @abstractmethod
    async def delete_transition(self, transition_id: UUID) -> None:
        """Delete a transition by primary key."""
        ...
