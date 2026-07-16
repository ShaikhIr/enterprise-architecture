"""
ClaimLineRepositoryImpl — SQLAlchemy async implementation of IClaimLineRepository.

Maps between ClaimLineModel (ORM) and ClaimLine (domain entity).
The ``sum_totals`` method uses SQL aggregate functions (SUM) rather than
Python-side aggregation so the DB does the heavy lifting in one round-trip.

Requirements: 4.1, 4.2, 12.1, 12.2
"""

from __future__ import annotations

from decimal import Decimal
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.domain.entities.commission_claim import ClaimLine
from src.domain.repositories.commission_claim.claim_line_repository import (
    ClaimTotals,
    IClaimLineRepository,
)
from src.infrastructure.database.models.commission_claim.commission_claim_model import (
    ClaimLineModel,
)


class ClaimLineRepositoryImpl(IClaimLineRepository):
    """
    Concrete SQLAlchemy async implementation of IClaimLineRepository.

    Accepts an AsyncSession injected at construction time (per the Unit of
    Work pattern used throughout this project).
    """

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    # ──────────────────────────────────────────────────────────────────────────
    # Read operations
    # ──────────────────────────────────────────────────────────────────────────

    async def get_by_id(self, line_id: UUID) -> ClaimLine | None:
        """Retrieve a single ClaimLine by PK. Returns None when not found."""
        stmt = select(ClaimLineModel).where(ClaimLineModel.id == line_id)
        result = await self._session.execute(stmt)
        model = result.scalar_one_or_none()
        return self._to_entity(model) if model else None

    async def list_by_claim(self, claim_id: UUID) -> list[ClaimLine]:
        """Return all ClaimLines for a given ClaimHeader, ordered by creation date."""
        stmt = (
            select(ClaimLineModel)
            .where(ClaimLineModel.claim_header_id == claim_id)
            .order_by(ClaimLineModel.created_date.asc(), ClaimLineModel.id)
        )
        result = await self._session.execute(stmt)
        models = result.scalars().all()
        return [self._to_entity(m) for m in models]

    async def sum_totals(self, claim_id: UUID) -> ClaimTotals:
        """
        Compute aggregate totals for all lines of a claim using SQL SUM functions.

        Returns a ``ClaimTotals`` value object with six aggregate fields.
        When no lines exist, all totals are Decimal("0").

        Used by the service layer to update ClaimHeader totals in the same
        DB transaction as any line change (Requirement 4.2).
        """
        stmt = select(
            func.coalesce(
                func.sum(ClaimLineModel.final_line_claim_amount), Decimal("0")
            ).label("total_claim_amount"),
            func.coalesce(
                func.sum(ClaimLineModel.commission_amount), Decimal("0")
            ).label("total_commission_amount"),
            func.coalesce(
                func.sum(ClaimLineModel.gst_on_commission), Decimal("0")
            ).label("total_gst_amount"),
            func.coalesce(
                func.sum(ClaimLineModel.tds_value), Decimal("0")
            ).label("total_tds_amount"),
            func.coalesce(
                func.sum(ClaimLineModel.ld_charges), Decimal("0")
            ).label("total_ld_amount"),
            func.coalesce(
                func.sum(ClaimLineModel.retention_amount), Decimal("0")
            ).label("total_retention_amount"),
        ).where(ClaimLineModel.claim_header_id == claim_id)

        result = await self._session.execute(stmt)
        row = result.one()

        return ClaimTotals(
            total_claim_amount=Decimal(str(row.total_claim_amount)),
            total_commission_amount=Decimal(str(row.total_commission_amount)),
            total_gst_amount=Decimal(str(row.total_gst_amount)),
            total_tds_amount=Decimal(str(row.total_tds_amount)),
            total_ld_amount=Decimal(str(row.total_ld_amount)),
            total_retention_amount=Decimal(str(row.total_retention_amount)),
        )

    # ──────────────────────────────────────────────────────────────────────────
    # Write operations
    # ──────────────────────────────────────────────────────────────────────────

    async def create(self, line: ClaimLine) -> ClaimLine:
        """Persist a new ClaimLine and return the stored entity."""
        model = ClaimLineModel(
            id=line.id,
            claim_header_id=line.claim_header_id,
            invoice_header_id=line.invoice_header_id,
            product_master_id=line.product_master_id,
            customer_id=line.customer_id,
            bill_amount_excl_gst=line.bill_amount_excl_gst,
            amount_deducted=line.amount_deducted,
            tds_value=line.tds_value,
            ld_charges=line.ld_charges,
            retention_amount=line.retention_amount,
            net_amount=line.net_amount,
            commission_payable_base=line.commission_payable_base,
            due_date=line.due_date,
            payment_clearing_date=line.payment_clearing_date,
            delay_days=line.delay_days,
            applicable_commission_percent=line.applicable_commission_percent,
            commission_amount=line.commission_amount,
            gst_on_commission=line.gst_on_commission,
            final_line_claim_amount=line.final_line_claim_amount,
            pod_document_id=line.pod_document_id,
            remarks=line.remarks,
            created_by=line.created_by,
            modified_by=line.modified_by,
        )
        self._session.add(model)
        await self._session.flush()
        return self._to_entity(model)

    async def update(self, line: ClaimLine) -> ClaimLine:
        """Update all mutable fields on an existing ClaimLine."""
        stmt = select(ClaimLineModel).where(ClaimLineModel.id == line.id)
        result = await self._session.execute(stmt)
        model = result.scalar_one_or_none()
        if model is None:
            raise ValueError(f"ClaimLine with id {line.id} not found")

        model.bill_amount_excl_gst = line.bill_amount_excl_gst
        model.amount_deducted = line.amount_deducted
        model.tds_value = line.tds_value
        model.ld_charges = line.ld_charges
        model.retention_amount = line.retention_amount
        model.net_amount = line.net_amount
        model.commission_payable_base = line.commission_payable_base
        model.due_date = line.due_date
        model.payment_clearing_date = line.payment_clearing_date
        model.delay_days = line.delay_days
        model.applicable_commission_percent = line.applicable_commission_percent
        model.commission_amount = line.commission_amount
        model.gst_on_commission = line.gst_on_commission
        model.final_line_claim_amount = line.final_line_claim_amount
        model.pod_document_id = line.pod_document_id
        model.remarks = line.remarks
        model.modified_by = line.modified_by
        model.modified_date = line.modified_date

        await self._session.flush()
        return self._to_entity(model)

    async def delete(self, line_id: UUID) -> None:
        """Delete a ClaimLine by PK. No-op if the line does not exist."""
        stmt = select(ClaimLineModel).where(ClaimLineModel.id == line_id)
        result = await self._session.execute(stmt)
        model = result.scalar_one_or_none()
        if model:
            await self._session.delete(model)
            await self._session.flush()

    # ──────────────────────────────────────────────────────────────────────────
    # ORM → Domain mapper
    # ──────────────────────────────────────────────────────────────────────────

    @staticmethod
    def _to_entity(model: ClaimLineModel) -> ClaimLine:
        """Map a ClaimLineModel ORM row to a ClaimLine domain entity."""
        return ClaimLine(
            id=model.id,
            claim_header_id=model.claim_header_id,
            invoice_header_id=model.invoice_header_id,
            product_master_id=model.product_master_id,
            customer_id=model.customer_id,
            bill_amount_excl_gst=model.bill_amount_excl_gst,
            amount_deducted=model.amount_deducted,
            tds_value=model.tds_value,
            ld_charges=model.ld_charges,
            retention_amount=model.retention_amount,
            net_amount=model.net_amount,
            commission_payable_base=model.commission_payable_base,
            due_date=model.due_date,
            payment_clearing_date=model.payment_clearing_date,
            delay_days=model.delay_days,
            applicable_commission_percent=model.applicable_commission_percent,
            commission_amount=model.commission_amount,
            gst_on_commission=model.gst_on_commission,
            final_line_claim_amount=model.final_line_claim_amount,
            pod_document_id=model.pod_document_id,
            remarks=model.remarks,
            created_by=model.created_by,
            created_date=model.created_date,
            modified_by=model.modified_by,
            modified_date=model.modified_date,
        )
