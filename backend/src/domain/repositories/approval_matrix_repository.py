"""
Approval matrix repository port.

`ApprovalMatrix` is handled as an aggregate: `create` and `update` persist the
matrix together with its rules and assignments, and `update` replaces both child
collections wholesale. That mirrors how the UI edits a matrix (one dialog, one
save) and removes any window where a matrix is readable with a partial rule set.
"""

from abc import abstractmethod
from uuid import UUID

from src.domain.entities.approval_matrix import ApprovalMatrix, ApprovalTask
from src.domain.repositories.base_repository import IRepository


class IApprovalMatrixRepository(IRepository[ApprovalMatrix]):
    """Persistence contract for approval matrices and approval tasks."""

    # ─── Matrices ───

    @abstractmethod
    async def list_all(
        self,
        skip: int = 0,
        limit: int = 100,
        search: str | None = None,
        is_active: bool | None = None,
        entity_type: str | None = None,
    ) -> list[ApprovalMatrix]:
        """List matrices with rules and assignments loaded, ordered by priority."""
        ...

    @abstractmethod
    async def count(
        self,
        search: str | None = None,
        is_active: bool | None = None,
        entity_type: str | None = None,
    ) -> int:
        """Count matrices matching the same criteria as `list_all`."""
        ...

    @abstractmethod
    async def exists_by_name(self, name: str, exclude_id: UUID | None = None) -> bool:
        """Check whether a matrix name is taken, optionally ignoring one row."""
        ...

    @abstractmethod
    async def list_active_for_entity_type(
        self, entity_type: str
    ) -> list[ApprovalMatrix]:
        """
        Active matrices for one entity type, ascending by priority.

        The resolver walks these in order and takes the first whose rules match,
        so priority is the tie-breaker between overlapping matrices.
        """
        ...

    # ─── Approval tasks ───

    @abstractmethod
    async def create_task(self, task: ApprovalTask) -> ApprovalTask:
        """Persist a new approval task."""
        ...

    @abstractmethod
    async def get_task(self, task_id: UUID) -> ApprovalTask | None:
        """Load one approval task by primary key."""
        ...

    @abstractmethod
    async def update_task(self, task: ApprovalTask) -> ApprovalTask:
        """Update an existing approval task."""
        ...

    @abstractmethod
    async def list_tasks_for_instance(self, instance_id: UUID) -> list[ApprovalTask]:
        """All tasks raised for one workflow instance, ordered by level."""
        ...

    @abstractmethod
    async def list_pending_tasks_for_user(self, user_id: UUID) -> list[ApprovalTask]:
        """Open tasks assigned to a user, oldest due date first."""
        ...

    @abstractmethod
    async def cancel_open_tasks_for_instance(self, instance_id: UUID) -> int:
        """
        Cancel every still-open task on an instance, returning how many changed.

        Called when an instance reaches a terminal state so stale approvals stop
        appearing in the approvers' task lists.
        """
        ...
