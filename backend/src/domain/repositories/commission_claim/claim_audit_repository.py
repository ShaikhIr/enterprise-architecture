"""
IClaimAuditRepository — abstract repository interface for ClaimAuditEntry persistence.

Intentionally exposes ONLY ``create`` and ``list_by_claim`` — no ``update`` or
``delete`` methods exist, enforcing immutability of the audit trail at the
interface level (Requirement 14.3).

Requirements: 14.1, 14.2, 14.3
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from uuid import UUID

from src.domain.entities.claim_audit_entry import ClaimAuditEntry


class IClaimAuditRepository(ABC):
    """
    Abstract (append-only) repository for ClaimAuditEntry persistence.

    The domain layer owns this interface; infrastructure implements it.

    Note: ``update()`` and ``delete()`` methods are deliberately absent.
    Immutability is enforced at this interface level so no implementation
    can accidentally expose a mutation path (Requirement 14.3).
    """

    @abstractmethod
    async def create(self, entry: ClaimAuditEntry) -> ClaimAuditEntry:
        """Append a new audit entry and return the persisted entity.

        Implementations MUST NOT expose any mechanism to modify the stored row.
        """
        ...

    @abstractmethod
    async def list_by_claim(self, claim_id: UUID) -> list[ClaimAuditEntry]:
        """Return all audit entries for the given claim in ascending timestamp order.

        Used to render the claim's full audit trail (Requirement 14.4).
        """
        ...
