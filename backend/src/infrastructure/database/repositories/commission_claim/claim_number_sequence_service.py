"""
ClaimNumberSequenceService — generates unique, sequential claim numbers.

Uses a SELECT … FOR UPDATE row-level lock on ``claim_number_sequences`` so
concurrent submissions in the same Indian financial year cannot produce
duplicate or out-of-order numbers.

Claim number format:  ``CL/YYYY-YY/NNN``
  - ``YYYY-YY`` — Indian financial year (April 1 – March 31)
      e.g.  April 2025 → "2025-26",  February 2025 → "2024-25"
  - ``NNN``  — zero-padded to at least 3 digits; extends naturally for ≥ 1000
      e.g.  1 → "001",  999 → "999",  1000 → "1000"

Requirements: 6.2, 6.3, 13.1, 13.2, 13.4
"""

from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.infrastructure.database.models.commission_claim.commission_claim_model import (
    ClaimNumberSequenceModel,
)


class ClaimNumberSequenceService:
    """
    Stateless service that allocates the next claim number for the current
    Indian financial year inside the caller's database transaction.

    The caller is responsible for committing or rolling back the surrounding
    transaction — this service only performs the row-lock and sequence
    increment via ``session.flush()``.

    Requirements: 13.1, 13.2, 13.4
    """

    @staticmethod
    def _current_financial_year() -> str:
        """
        Compute the Indian financial year string for today's UTC date.

        The Indian financial year runs from April 1 to March 31.

        Examples
        --------
        - 2025-04-15 → "2025-26"  (April–December: FY starts this year)
        - 2025-01-20 → "2024-25"  (January–March: FY started last year)
        """
        now = datetime.now(timezone.utc)
        year = now.year
        month = now.month

        if month >= 4:
            # April or later — the financial year started this calendar year
            fy_start = year
        else:
            # January–March — the financial year started the previous calendar year
            fy_start = year - 1

        fy_end_short = (fy_start + 1) % 100  # last two digits of the ending year
        return f"{fy_start}-{fy_end_short:02d}"

    async def next_claim_number(self, session: AsyncSession) -> str:
        """
        Allocate and return the next sequential claim number for the current
        Indian financial year.

        Behaviour
        ---------
        1. Compute the current financial year string (e.g. ``"2025-26"``).
        2. SELECT the ``claim_number_sequences`` row for that year WITH a
           row-level FOR UPDATE lock to prevent concurrent allocations.
        3. If no row exists yet, INSERT a new row with ``last_sequence = 1``.
           Otherwise increment ``last_sequence`` by 1 in-place.
        4. Flush to the DB (does not commit — caller owns the transaction).
        5. Return the formatted claim number: ``CL/{fy}/{seq:03d}``.

        Parameters
        ----------
        session:
            Active ``AsyncSession`` that is part of the caller's unit of work.

        Returns
        -------
        str
            Claim number in the format ``CL/YYYY-YY/NNN``, e.g.
            ``"CL/2025-26/001"`` or ``"CL/2025-26/1000"``.

        Requirements: 6.2, 6.3, 13.1, 13.2, 13.4
        """
        fy = self._current_financial_year()

        # Row-level lock: prevents two concurrent transactions from reading the
        # same last_sequence value and generating a duplicate claim number.
        stmt = (
            select(ClaimNumberSequenceModel)
            .where(ClaimNumberSequenceModel.financial_year == fy)
            .with_for_update()
        )
        result = await session.execute(stmt)
        row = result.scalar_one_or_none()

        if row is None:
            # First claim for this financial year — create the sequence row.
            row = ClaimNumberSequenceModel(
                financial_year=fy,
                last_sequence=1,
                # AuditMixin fields: populated by application-level defaults;
                # use a sentinel value so the DB constraint is satisfied even
                # when called outside a full request context.
                created_by="system",
                modified_by="system",
            )
            session.add(row)
            seq = 1
        else:
            # Subsequent claim — increment in place under the row lock.
            row.last_sequence += 1
            seq = row.last_sequence

        # Flush to persist the sequence row within the current transaction
        # (the caller commits or rolls back the outer UoW).
        await session.flush()

        # Format: zero-pad to 3 digits; Python's :03d extends naturally to 4+
        # digits for seq ≥ 1000 (e.g. 1000 → "1000", not truncated).
        return f"CL/{fy}/{seq:03d}"
