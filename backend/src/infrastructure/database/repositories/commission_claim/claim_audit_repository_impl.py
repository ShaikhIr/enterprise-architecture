"""
ClaimAuditRepositoryImpl — append-only persistence for ClaimAuditEntry.

Intentionally exposes ONLY ``create`` and ``list_by_claim``.  There are no
``update`` or ``delete`` methods; immutability of the audit trail is enforced
at both the interface level (``IClaimAuditRepository``) and here in the
concrete implementation (Requirement 14.3).

Requirements: 14.1, 14.2, 14.3
"""

from __future__ import annotations

from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.domain.entities.claim_audit_entry import ClaimAuditEntry
from src.domain.repositories.commission_claim.claim_audit_repository import (
    IClaimAuditRepository,
)
from src.infrastructure.database.models.commission_claim.commission_claim_model import (
    ClaimAuditLogModel,
)


class ClaimAuditRepositoryImpl(IClaimAuditRepository):
    """
    Concrete, append-only implementation of ``IClaimAuditRepository``.

    Every audit event produces a single INSERT; rows are never mutated or
    removed.  ``update()`` and ``delete()`` methods are deliberately absent —
    the interface does not declare them and this class does not add them.

    Parameters
    ----------
    session:
        Active ``AsyncSession`` injected by the application service.
        The caller is responsible for committing the surrounding transaction.

    Requirements: 14.1, 14.2, 14.3
    """

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def create(self, entry: ClaimAuditEntry) -> ClaimAuditEntry:
        """
        Persist a new audit entry and return the stored entity.

        Inserts a single row into ``claim_audit_logs`` and flushes within the
        caller's transaction.  The returned entity reflects the values written
        to the database.

        Parameters
        ----------
        entry:
            The ``ClaimAuditEntry`` domain entity to persist.  ``id``,
            ``created_by``, and ``created_date`` must already be set by the
            service layer before calling this method.

        Returns
        -------
        ClaimAuditEntry
            The persisted entity (identical to the input after flush).

        Requirements: 14.1, 14.2
        """
        model = ClaimAuditLogModel(
            id=entry.id,
            claim_header_id=entry.claim_header_id,
            action=entry.action,
            actor_username=entry.actor_username,
            actor_user_id=entry.actor_user_id,
            timestamp_utc=entry.timestamp_utc,
            from_status=entry.from_status,
            to_status=entry.to_status,
            workflow_step_name=entry.workflow_step_name,
            remarks=entry.remarks,
            field_changes=entry.field_changes,
            created_by=entry.created_by,
            modified_by=entry.modified_by,
        )
        self._session.add(model)
        await self._session.flush()
        return self._to_entity(model)

    async def list_by_claim(self, claim_id: UUID) -> list[ClaimAuditEntry]:
        """
        Return all audit entries for ``claim_id`` in ascending timestamp order.

        The full audit trail is returned without pagination — callers that need
        to page results should do so at the service or API layer.

        Parameters
        ----------
        claim_id:
            UUID of the ``ClaimHeader`` whose audit trail is requested.

        Returns
        -------
        list[ClaimAuditEntry]
            Entries ordered by ``timestamp_utc ASC`` (oldest first).

        Requirements: 14.2, 14.4
        """
        stmt = (
            select(ClaimAuditLogModel)
            .where(ClaimAuditLogModel.claim_header_id == claim_id)
            .order_by(ClaimAuditLogModel.timestamp_utc.asc())
        )
        result = await self._session.execute(stmt)
        models = result.scalars().all()
        return [self._to_entity(m) for m in models]

    # ── Mapper ──────────────────────────────────────────────────────────────

    @staticmethod
    def _to_entity(model: ClaimAuditLogModel) -> ClaimAuditEntry:
        """Map a ``ClaimAuditLogModel`` ORM row to a ``ClaimAuditEntry`` entity."""
        return ClaimAuditEntry(
            id=model.id,
            claim_header_id=model.claim_header_id,
            action=model.action,
            actor_username=model.actor_username,
            actor_user_id=model.actor_user_id,
            timestamp_utc=model.timestamp_utc,
            from_status=model.from_status,
            to_status=model.to_status,
            workflow_step_name=model.workflow_step_name,
            remarks=model.remarks,
            field_changes=model.field_changes,
            created_by=model.created_by,
            created_date=model.created_date,
            modified_by=model.modified_by,
            modified_date=model.modified_date,
        )
