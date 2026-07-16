"""
IClaimHeaderRepository — abstract repository interface for ClaimHeader persistence.

Also defines the ClaimFilterParams value object used by list operations.

Requirements: 14.1, 14.2, 14.3, 12.1, 12.2, 15.2
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import date
from uuid import UUID

from src.domain.entities.commission_claim import ClaimHeader


@dataclass
class ClaimFilterParams:
    """
    Value object that carries optional filter criteria for claim list queries.

    All fields are optional — a ``None`` value means "no filter on this field".

    Attributes
    ----------
    vendor_id : UUID | None
        Restrict results to claims owned by this vendor.
    status : str | None
        Restrict results to claims with this exact status string.
    claim_number : str | None
        Partial text match against the claim_number column
        (implementation typically uses SQL ILIKE/LIKE).
    start_date : date | None
        Inclusive lower bound on ``claim_date``.
    end_date : date | None
        Inclusive upper bound on ``claim_date``.
    """

    vendor_id: UUID | None = None
    status: str | None = None
    status_exclude: str | None = None  # Exclude claims with this status (Admin: exclude Draft)
    claim_number: str | None = None   # partial text match
    start_date: date | None = None
    end_date: date | None = None


class IClaimHeaderRepository(ABC):
    """
    Abstract repository (Port) for ClaimHeader aggregate persistence.

    The domain layer owns this interface; infrastructure implements it.
    """

    @abstractmethod
    async def get_by_id(self, claim_id: UUID) -> ClaimHeader | None:
        """Retrieve a ClaimHeader by its unique identifier.

        Returns ``None`` when no matching record exists.
        """
        ...

    @abstractmethod
    async def create(self, header: ClaimHeader) -> ClaimHeader:
        """Persist a new ClaimHeader and return the stored entity."""
        ...

    @abstractmethod
    async def update(self, header: ClaimHeader) -> ClaimHeader:
        """Update an existing ClaimHeader and return the updated entity."""
        ...

    @abstractmethod
    async def list_by_vendor(
        self,
        vendor_id: UUID,
        skip: int,
        limit: int,
    ) -> tuple[list[ClaimHeader], int]:
        """Return a paginated list of claims for a specific vendor.

        Returns a tuple of ``(items, total_count)``.
        """
        ...

    @abstractmethod
    async def list_all(
        self,
        filters: ClaimFilterParams,
        skip: int,
        limit: int,
    ) -> tuple[list[ClaimHeader], int]:
        """Return a paginated, filtered list of all claims (admin/MIS view).

        Returns a tuple of ``(items, total_count)``.
        """
        ...

    @abstractmethod
    async def list_pending_for_user(self, user_id: UUID) -> list[ClaimHeader]:
        """Return all Pending claims for which ``user_id`` is the eligible approver.

        Used to populate the Approval Queue view (Requirement 17.1).
        """
        ...

    @abstractmethod
    async def list_by_workflow_instances(
        self,
        instance_ids: list[UUID],
        skip: int,
        limit: int,
    ) -> tuple[list[ClaimHeader], int]:
        """Return claims whose workflow_instance_id is in the given list.

        Used for approval-matrix-based filtering: returns only claims
        currently pending at the user's approval level.
        Returns a tuple of ``(items, total_count)``.
        """
        ...

    @abstractmethod
    async def get_next_sequence(self, financial_year: str) -> int:
        """Return the next sequence integer for a given financial year.

        MUST be implemented with a database-level lock (e.g. SELECT … FOR UPDATE)
        to guarantee uniqueness of claim numbers under concurrency
        (Requirements 6.2, 13.1–13.4).
        """
        ...
