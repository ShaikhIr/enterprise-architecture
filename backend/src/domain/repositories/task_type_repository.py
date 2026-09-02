"""
Task type repository interface (Port).
Defines the contract for task type master persistence.
"""

from abc import abstractmethod

from src.domain.entities.task_type import TaskType
from src.domain.repositories.base_repository import IRepository


class ITaskTypeRepository(IRepository[TaskType]):
    """Abstract repository for the TaskType master."""

    @abstractmethod
    async def exists_by_name(self, name: str, exclude_id: int | None = None) -> bool:
        """Check whether a task type name is already taken."""
        ...
