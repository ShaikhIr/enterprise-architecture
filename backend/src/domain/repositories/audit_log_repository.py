"""
Audit log repository interface (Port).
Audit entries are append-only: they are never updated or deleted.
"""

from abc import ABC, abstractmethod
from datetime import datetime

from src.domain.entities.audit_log import AuditLog


class IAuditLogRepository(ABC):
    """Abstract repository for audit trail persistence and querying."""

    @abstractmethod
    async def add(self, entry: AuditLog) -> None:
        """Append a single audit entry."""
        ...

    @abstractmethod
    async def query(
        self,
        *,
        action: str | None = None,
        actor_id: int | None = None,
        actor_username: str | None = None,
        resource_type: str | None = None,
        skip: int = 0,
        limit: int = 50,
    ) -> list[AuditLog]:
        """Read audit entries newest first, with optional filters."""
        ...

    @abstractmethod
    async def count(
        self,
        *,
        action: str | None = None,
        actor_id: int | None = None,
        actor_username: str | None = None,
        resource_type: str | None = None,
    ) -> int:
        """Count audit entries matching the same filters as `query`."""
        ...

    @abstractmethod
    async def latest_timestamp_by_actor(
        self, action: str, actor_ids: list[int]
    ) -> dict[int, datetime]:
        """
        Most recent occurrence of `action` per actor.

        One grouped query rather than one per actor — used for "last login"
        columns on a page of users.
        """
        ...
