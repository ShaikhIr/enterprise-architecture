"""
Audit log repository implementation (Adapter).
Implements IAuditLogRepository using SQLAlchemy async.
"""

import logging
from datetime import datetime
from uuid import UUID

from sqlalchemy import Select, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.domain.entities.audit_log import AuditLog
from src.domain.repositories.audit_log_repository import IAuditLogRepository
from src.infrastructure.database.models.audit_log_model import AuditLogModel

logger = logging.getLogger(__name__)


class AuditLogRepositoryImpl(IAuditLogRepository):
    """Concrete implementation of audit trail persistence using SQLAlchemy."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def add(self, entry: AuditLog) -> None:
        """
        Append an audit entry.

        Failures are logged and swallowed, preserving the behaviour of the
        previous AuditService so an audit problem cannot break the business
        operation that triggered it.

        NOTE: for a compliance system, silently dropping audit entries is
        arguably the wrong trade-off. Kept as-is here so this refactor does not
        change behaviour; worth revisiting deliberately.
        """
        try:
            self._session.add(
                AuditLogModel(
                    id=entry.id,
                    actor_id=entry.actor_id,
                    actor_username=entry.actor_username,
                    action=entry.action,
                    resource_type=entry.resource_type,
                    resource_id=entry.resource_id,
                    tenant_id=entry.tenant_id,
                    old_value=entry.old_value,
                    new_value=entry.new_value,
                    ip_address=entry.ip_address,
                    user_agent=entry.user_agent,
                    extra_data=entry.extra_data,
                    created_at=entry.created_at,
                )
            )
            await self._session.flush()
        except Exception as exc:  # pragma: no cover - defensive
            logger.error("Failed to write audit log: %s", exc, exc_info=True)

    async def query(
        self,
        *,
        action: str | None = None,
        actor_id: UUID | None = None,
        actor_username: str | None = None,
        resource_type: str | None = None,
        skip: int = 0,
        limit: int = 50,
    ) -> list[AuditLog]:
        stmt = self._apply_filters(
            select(AuditLogModel), action, actor_id, actor_username, resource_type
        )
        stmt = stmt.order_by(AuditLogModel.created_at.desc()).offset(skip).limit(limit)
        result = await self._session.execute(stmt)
        return [self._to_entity(m) for m in result.scalars().all()]

    async def count(
        self,
        *,
        action: str | None = None,
        actor_id: UUID | None = None,
        actor_username: str | None = None,
        resource_type: str | None = None,
    ) -> int:
        stmt = self._apply_filters(
            select(func.count()).select_from(AuditLogModel),
            action,
            actor_id,
            actor_username,
            resource_type,
        )
        result = await self._session.execute(stmt)
        return int(result.scalar() or 0)

    async def latest_timestamp_by_actor(
        self, action: str, actor_ids: list[UUID]
    ) -> dict[UUID, datetime]:
        if not actor_ids:
            return {}
        stmt = (
            select(
                AuditLogModel.actor_id,
                func.max(AuditLogModel.created_at).label("latest"),
            )
            .where(
                AuditLogModel.action == action,
                AuditLogModel.actor_id.in_(actor_ids),
            )
            .group_by(AuditLogModel.actor_id)
        )
        result = await self._session.execute(stmt)
        return {row[0]: row[1] for row in result.all() if row[0] is not None}

    # ─── Internals ───

    @staticmethod
    def _apply_filters(
        stmt: "Select[tuple[AuditLogModel]] | Select[tuple[int]]",
        action: str | None,
        actor_id: UUID | None,
        actor_username: str | None,
        resource_type: str | None,
    ) -> "Select[tuple[AuditLogModel]] | Select[tuple[int]]":
        if action:
            stmt = stmt.where(AuditLogModel.action == action)
        if actor_id:
            stmt = stmt.where(AuditLogModel.actor_id == actor_id)
        if actor_username:
            stmt = stmt.where(AuditLogModel.actor_username == actor_username)
        if resource_type:
            stmt = stmt.where(AuditLogModel.resource_type == resource_type)
        return stmt

    @staticmethod
    def _to_entity(model: AuditLogModel) -> AuditLog:
        """Map ORM model to domain entity."""
        return AuditLog(
            id=model.id,
            actor_id=model.actor_id,
            actor_username=model.actor_username,
            action=model.action,
            resource_type=model.resource_type,
            resource_id=model.resource_id,
            tenant_id=model.tenant_id,
            old_value=model.old_value,
            new_value=model.new_value,
            ip_address=model.ip_address,
            user_agent=model.user_agent,
            extra_data=model.extra_data,
            created_at=model.created_at,
        )
