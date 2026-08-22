"""
Task type repository interface (Port).
Defines the contract for task type master persistence.
"""

from abc import abstractmethod
from uuid import UUID

from src.domain.entities.task_type import TaskType
from src.domain.repositories.base_repository import IRepository


class ITaskTypeRepository(IRepository[TaskType]):
    """Abstract repository for the TaskType master."""

    @abstractmethod
    async def exists_by_name(self, name: str, exclude_id: UUID | None = None) -> bool:
        """Check whether a task type name is already taken."""
        ...
