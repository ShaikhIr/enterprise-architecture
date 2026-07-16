"""
ClaimHeaderRepositoryImpl — SQLAlchemy async implementation of IClaimHeaderRepository.

Maps between ClaimHeaderModel (ORM) and ClaimHeader (domain entity).

Requirements: 4.1, 4.2, 12.1, 12.2
"""

from __future__ import annotations

from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.domain.entities.commission_claim import ClaimHeader, ClaimStatus
from src.domain.repositories.commission_claim.claim_header_repository import (
    ClaimFilterParams,
    IClaimHeaderRepository,
)
from src.infrastructure.database.models.commission_claim.commission_claim_model import (
    ClaimHeaderModel,
    ClaimNumberSequenceModel,
)


class ClaimHeaderRepositoryImpl(IClaimHeaderRepository):
    """
    Concrete SQLAlchemy async implementation of IClaimHeaderRepository.

    Accepts an AsyncSession injected at construction time (per the Unit of
    Work pattern used throughout this project).
    """

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    # ──────────────────────────────────────────────────────────────────────────
    # Read operations
    # ──────────────────────────────────────────────────────────────────────────

    async def get_by_id(self, claim_id: UUID) -> ClaimHeader | None:
        """Retrieve a ClaimHeader by PK. Returns None when not found."""
        stmt = select(ClaimHeaderModel).where(ClaimHeaderModel.id == claim_id)
        result = await self._session.execute(stmt)
        model = result.scalar_one_or_none()
        return self._to_entity(model) if model else None

    async def list_by_vendor(
        self,
        vendor_id: UUID,
        skip: int,
        limit: int,
    ) -> tuple[list[ClaimHeader], int]:
        """
        Paginated list of claims owned by a specific vendor.

        Returns ``(items, total_count)``.  Used for the Liaisoning Agent view
        (Requirement 12.1).
        """
        base_stmt = select(ClaimHeaderModel).where(
            ClaimHeaderModel.vendor_id == vendor_id
        )

        # Count total before pagination
        count_stmt = select(func.count()).select_from(
            base_stmt.subquery()
        )
        count_result = await self._session.execute(count_stmt)
        total = int(count_result.scalar_one())

        # Fetch page
        page_stmt = (
            base_stmt
            .order_by(ClaimHeaderModel.created_date.desc(), ClaimHeaderModel.id)
            .offset(skip)
            .limit(limit)
        )
        result = await self._session.execute(page_stmt)
        models = result.scalars().all()
        return [self._to_entity(m) for m in models], total

    async def list_all(
        self,
        filters: ClaimFilterParams,
        skip: int,
        limit: int,
    ) -> tuple[list[ClaimHeader], int]:
        """
        Paginated, filtered list of all claims (Admin / MIS view).

        Applies optional filters from ``ClaimFilterParams``:
        - vendor_id  → exact match
        - status     → exact match
        - claim_number → case-insensitive partial match (ILIKE)
        - start_date / end_date → inclusive range on claim_date

        Returns ``(items, total_count)``.  Requirement 12.2.
        """
        stmt = select(ClaimHeaderModel)

        if filters.vendor_id is not None:
            stmt = stmt.where(ClaimHeaderModel.vendor_id == filters.vendor_id)
        if filters.status is not None:
            stmt = stmt.where(ClaimHeaderModel.status == filters.status)
        if filters.status_exclude is not None:
            stmt = stmt.where(ClaimHeaderModel.status != filters.status_exclude)
        if filters.claim_number is not None:
            stmt = stmt.where(
                ClaimHeaderModel.claim_number.ilike(f"%{filters.claim_number}%")
            )
        if filters.start_date is not None:
            stmt = stmt.where(ClaimHeaderModel.claim_date >= filters.start_date)
        if filters.end_date is not None:
            stmt = stmt.where(ClaimHeaderModel.claim_date <= filters.end_date)

        # Count total before pagination
        count_stmt = select(func.count()).select_from(stmt.subquery())
        count_result = await self._session.execute(count_stmt)
        total = int(count_result.scalar_one())

        # Fetch page
        page_stmt = (
            stmt
            .order_by(ClaimHeaderModel.created_date.desc(), ClaimHeaderModel.id)
            .offset(skip)
            .limit(limit)
        )
        result = await self._session.execute(page_stmt)
        models = result.scalars().all()
        return [self._to_entity(m) for m in models], total

    async def list_pending_for_user(self, user_id: UUID) -> list[ClaimHeader]:
        """
        Return all Pending claims for which ``user_id`` has an active PENDING
        approval task.  Only returns claims where the user is the currently
        assigned approver via the approval_tasks table.

        This ensures that after an approver takes action, the claim disappears
        from their queue, and only the next assigned approver sees it.
        """
        from src.infrastructure.database.models.workflow.approval_matrix_models import (
            ApprovalTaskModel,
        )

        # Find workflow instance IDs where this user has a PENDING task
        pending_instances_stmt = (
            select(ApprovalTaskModel.instance_id)
            .where(
                ApprovalTaskModel.assignee_id == str(user_id),
                ApprovalTaskModel.status == "PENDING",
            )
            .distinct()
        )
        pending_result = await self._session.execute(pending_instances_stmt)
        pending_instance_ids = [row[0] for row in pending_result.all()]

        if not pending_instance_ids:
            return []

        # Fetch claim headers for those workflow instances with Pending status
        stmt = (
            select(ClaimHeaderModel)
            .where(
                ClaimHeaderModel.workflow_instance_id.in_(pending_instance_ids),
                ClaimHeaderModel.status == ClaimStatus.Pending.value,
            )
            .order_by(ClaimHeaderModel.created_date.asc(), ClaimHeaderModel.id)
        )
        result = await self._session.execute(stmt)
        models = result.scalars().all()
        return [self._to_entity(m) for m in models]

    async def list_by_workflow_instances(
        self,
        instance_ids: list[UUID],
        skip: int,
        limit: int,
    ) -> tuple[list[ClaimHeader], int]:
        """
        Return claims whose workflow_instance_id is in the given list AND
        whose status is Pending.

        Used for approval-matrix-based filtering. Returns only claims
        currently pending at the user's approval level (instance_ids come
        from approval_tasks WHERE assignee_id = user AND status = PENDING).
        """
        if not instance_ids:
            return [], 0

        # Convert to strings for UUID comparison
        id_strs = [str(iid) for iid in instance_ids]

        base_stmt = select(ClaimHeaderModel).where(
            ClaimHeaderModel.workflow_instance_id.in_(id_strs),
            ClaimHeaderModel.status == ClaimStatus.Pending.value,
        )

        # Count
        count_stmt = select(func.count()).select_from(base_stmt.subquery())
        count_result = await self._session.execute(count_stmt)
        total = int(count_result.scalar_one())

        # Fetch page
        page_stmt = (
            base_stmt
            .order_by(ClaimHeaderModel.created_date.desc(), ClaimHeaderModel.id)
            .offset(skip)
            .limit(limit)
        )
        result = await self._session.execute(page_stmt)
        models = result.scalars().all()
        return [self._to_entity(m) for m in models], total

    # ──────────────────────────────────────────────────────────────────────────
    # Write operations
    # ──────────────────────────────────────────────────────────────────────────

    async def create(self, header: ClaimHeader) -> ClaimHeader:
        """Persist a new ClaimHeader and return the stored entity."""
        model = ClaimHeaderModel(
            id=header.id,
            vendor_id=header.vendor_id,
            entity_id=header.entity_id,
            claim_number=header.claim_number,
            claim_date=header.claim_date,
            status=header.status.value,
            workflow_instance_id=header.workflow_instance_id,
            total_claim_amount=header.total_claim_amount,
            total_commission_amount=header.total_commission_amount,
            total_gst_amount=header.total_gst_amount,
            total_tds_amount=header.total_tds_amount,
            total_ld_amount=header.total_ld_amount,
            total_retention_amount=header.total_retention_amount,
            gstn_verification_status=header.gstn_verification_status,
            gst_invoice_number=header.gst_invoice_number,
            gst_invoice_upload_date=header.gst_invoice_upload_date,
            sap_p2p_booking_reference=header.sap_p2p_booking_reference,
            created_by=header.created_by,
            modified_by=header.modified_by,
        )
        self._session.add(model)
        await self._session.flush()
        return self._to_entity(model)

    async def update(self, header: ClaimHeader) -> ClaimHeader:
        """Update all mutable fields on an existing ClaimHeader."""
        stmt = select(ClaimHeaderModel).where(ClaimHeaderModel.id == header.id)
        result = await self._session.execute(stmt)
        model = result.scalar_one_or_none()
        if model is None:
            raise ValueError(f"ClaimHeader with id {header.id} not found")

        model.claim_number = header.claim_number
        model.claim_date = header.claim_date
        model.status = header.status.value
        model.workflow_instance_id = header.workflow_instance_id
        model.entity_id = header.entity_id
        model.total_claim_amount = header.total_claim_amount
        model.total_commission_amount = header.total_commission_amount
        model.total_gst_amount = header.total_gst_amount
        model.total_tds_amount = header.total_tds_amount
        model.total_ld_amount = header.total_ld_amount
        model.total_retention_amount = header.total_retention_amount
        model.gstn_verification_status = header.gstn_verification_status
        model.gst_invoice_number = header.gst_invoice_number
        model.gst_invoice_upload_date = header.gst_invoice_upload_date
        model.sap_p2p_booking_reference = header.sap_p2p_booking_reference
        model.modified_by = header.modified_by
        model.modified_date = header.modified_date

        await self._session.flush()
        return self._to_entity(model)

    # ──────────────────────────────────────────────────────────────────────────
    # Sequence — used by ClaimNumberSequenceService
    # ──────────────────────────────────────────────────────────────────────────

    async def get_next_sequence(self, financial_year: str) -> int:
        """
        Return the next sequence integer for the given Indian financial year.

        Uses ``SELECT ... FOR UPDATE`` to prevent duplicate numbers under
        concurrent submissions.  If no row exists for ``financial_year``, one
        is inserted atomically.

        Requirements: 6.2, 13.1–13.4.
        """
        stmt = (
            select(ClaimNumberSequenceModel)
            .where(ClaimNumberSequenceModel.financial_year == financial_year)
            .with_for_update()
        )
        result = await self._session.execute(stmt)
        seq_model = result.scalar_one_or_none()

        if seq_model is None:
            # First submission in this financial year — seed the row
            seq_model = ClaimNumberSequenceModel(
                financial_year=financial_year,
                last_sequence=0,
                created_by="system",
                modified_by="system",
            )
            self._session.add(seq_model)
            await self._session.flush()

        seq_model.last_sequence += 1
        await self._session.flush()
        return seq_model.last_sequence

    # ──────────────────────────────────────────────────────────────────────────
    # ORM → Domain mapper
    # ──────────────────────────────────────────────────────────────────────────

    @staticmethod
    def _to_entity(model: ClaimHeaderModel) -> ClaimHeader:
        """Map a ClaimHeaderModel ORM row to a ClaimHeader domain entity."""
        return ClaimHeader(
            id=model.id,
            vendor_id=model.vendor_id,
            entity_id=model.entity_id,
            claim_number=model.claim_number,
            claim_date=model.claim_date,
            status=ClaimStatus(model.status),
            workflow_instance_id=model.workflow_instance_id,
            total_claim_amount=model.total_claim_amount,
            total_commission_amount=model.total_commission_amount,
            total_gst_amount=model.total_gst_amount,
            total_tds_amount=model.total_tds_amount,
            total_ld_amount=model.total_ld_amount,
            total_retention_amount=model.total_retention_amount,
            gstn_verification_status=model.gstn_verification_status,
            gst_invoice_number=model.gst_invoice_number,
            gst_invoice_upload_date=model.gst_invoice_upload_date,
            sap_p2p_booking_reference=model.sap_p2p_booking_reference,
            created_by=model.created_by,
            created_date=model.created_date,
            modified_by=model.modified_by,
            modified_date=model.modified_date,
        )
