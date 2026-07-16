"""
IClaimLineRepository — abstract repository interface for ClaimLine persistence.

Also defines the ClaimTotals value object produced by the ``sum_totals`` method.

Requirements: 14.1, 4.1, 4.2
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from decimal import Decimal
from uuid import UUID

from src.domain.entities.commission_claim import ClaimLine


@dataclass
class ClaimTotals:
    """
    Value object that holds the aggregated totals for all lines of a claim.

    Returned by ``IClaimLineRepository.sum_totals`` and used by the service
    layer to recalculate ``ClaimHeader`` aggregate fields within the same
    database transaction as any line change (Requirement 4.2).

    Attributes
    ----------
    total_claim_amount : Decimal
        Sum of ``ClaimLine.final_line_claim_amount`` across all lines.
    total_commission_amount : Decimal
        Sum of ``ClaimLine.commission_amount`` across all lines.
    total_gst_amount : Decimal
        Sum of ``ClaimLine.gst_on_commission`` across all lines.
    total_tds_amount : Decimal
        Sum of ``ClaimLine.tds_value`` across all lines.
    total_ld_amount : Decimal
        Sum of ``ClaimLine.ld_charges`` across all lines.
    total_retention_amount : Decimal
        Sum of ``ClaimLine.retention_amount`` across all lines.
    """

    total_claim_amount: Decimal
    total_commission_amount: Decimal
    total_gst_amount: Decimal
    total_tds_amount: Decimal
    total_ld_amount: Decimal
    total_retention_amount: Decimal


class IClaimLineRepository(ABC):
    """
    Abstract repository (Port) for ClaimLine persistence.

    The domain layer owns this interface; infrastructure implements it.
    """

    @abstractmethod
    async def get_by_id(self, line_id: UUID) -> ClaimLine | None:
        """Retrieve a ClaimLine by its unique identifier.

        Returns ``None`` when no matching record exists.
        """
        ...

    @abstractmethod
    async def list_by_claim(self, claim_id: UUID) -> list[ClaimLine]:
        """Return all ClaimLines belonging to the given ClaimHeader."""
        ...

    @abstractmethod
    async def create(self, line: ClaimLine) -> ClaimLine:
        """Persist a new ClaimLine and return the stored entity."""
        ...

    @abstractmethod
    async def update(self, line: ClaimLine) -> ClaimLine:
        """Update an existing ClaimLine and return the updated entity."""
        ...

    @abstractmethod
    async def delete(self, line_id: UUID) -> None:
        """Delete a ClaimLine by its unique identifier."""
        ...

    @abstractmethod
    async def sum_totals(self, claim_id: UUID) -> ClaimTotals:
        """Compute and return aggregate totals for all lines of a claim.

        The result is used by the service layer to update the ClaimHeader
        within the same DB transaction (Requirement 4.2).
        """
        ...
