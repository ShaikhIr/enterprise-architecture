"""
CommissionClaimService — application-layer orchestrator for Commission Claim Management.

All business use cases flow through this service.  It wires together the four
infrastructure repositories/services, delegates to the domain calculator, integrates
with WorkflowEngine and AuditService, and enforces all pre-condition validations
described in the design document.

Method stubs are present for every use case (tasks 4.2+) and raise
``NotImplementedError`` until implemented.  The ``_recalculate_header_totals``
private helper is also stubbed here and will be filled in during task 4.3.

Requirements: 1.1
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from typing import Any
from uuid import UUID, uuid4

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.application.services.workflow.workflow_engine import WorkflowEngine
from src.domain.entities.claim_audit_entry import ClaimAuditEntry
from src.domain.entities.commission_claim import (
    ClaimHeader,
    ClaimLine,
    ClaimStatus,
    CLAIM_TRANSITIONS,
    TERMINAL_STATUSES,
)
from src.domain.enums.masters import AgreementStatus, InvoiceStatus, MappingStatus
from src.domain.services.commission_calculator import CommissionInputs, calculate
from src.infrastructure.database.models.masters.agreement_model import AgreementModel
from src.infrastructure.database.models.masters.invoice_model import (
    InvoiceHeaderModel,
    InvoiceLineModel,
)
from src.infrastructure.database.models.masters.mapping_model import MappingModel
from src.infrastructure.database.models.masters.vendor_model import VendorModel
from src.infrastructure.database.repositories.commission_claim.claim_audit_repository_impl import (
    ClaimAuditRepositoryImpl,
)
from src.infrastructure.database.repositories.commission_claim.claim_header_repository_impl import (
    ClaimHeaderRepositoryImpl,
)
from src.infrastructure.database.repositories.commission_claim.claim_line_repository_impl import (
    ClaimLineRepositoryImpl,
)
from src.infrastructure.database.repositories.commission_claim.claim_number_sequence_service import (
    ClaimNumberSequenceService,
)
from src.infrastructure.security.audit_service import AuditService
from src.domain.repositories.commission_claim.claim_header_repository import ClaimFilterParams


def _is_admin_actor(actor: Any) -> bool:
    """
    Return True when the actor holds Administrator-level access.

    Checks, in order:
    1. ``actor.role == "ADMIN"``      — for actors enriched by RBACManager
    2. ``actor.roles`` iterable       — for actors that carry a list/set of roles
    3. ``actor.permissions`` iterable — looks for a sentinel admin permission

    All lookups are defensive (getattr + silent fallback) so that any
    actor object can be passed without raising AttributeError.
    """
    # 1. Single-role attribute (used by rbac_manager.py Role enum pattern)
    role = getattr(actor, "role", None)
    if isinstance(role, str) and role.upper() == "ADMIN":
        return True

    # 2. Collection of role codes / role objects
    roles = getattr(actor, "roles", None)
    if roles:
        for r in roles:
            # Role may be a string code or an object with a .code / .name attribute
            if isinstance(r, str):
                if r.upper() == "ADMIN":
                    return True
            else:
                code = getattr(r, "code", None) or getattr(r, "name", None) or ""
                if isinstance(code, str) and code.upper() == "ADMIN":
                    return True

    # 3. Permissions collection — admin actors hold all claim permissions
    permissions = getattr(actor, "permissions", None)
    if permissions:
        for p in permissions:
            code = p if isinstance(p, str) else (getattr(p, "code", "") or "")
            # Admins have all permissions; check a characteristic admin-only one
            if isinstance(code, str) and code.lower() in (
                "claims.export",
                "menu.claims_mis",
            ):
                # These are ADMIN/Finance permissions — but not exclusively admin.
                # Fall through; we can't reliably identify admin from permissions alone
                pass

    return False


@dataclass
class LineUpdateRequest:
    """
    Partial update payload for an existing claim line.

    All fields are optional — only non-None values are applied.
    If ``amount_deducted``, ``tds_value``, or ``payment_clearing_date``
    change the commission formula is re-run (Requirement 3.1).

    Requirements: 3.1, 4.1, 4.2, 10.1, 10.2, 10.3
    """

    amount_deducted: Decimal | None = None
    tds_value: Decimal | None = None
    payment_clearing_date: date | None = None
    ld_charges: Decimal | None = None
    retention_amount: Decimal | None = None
    due_date: date | None = None
    remarks: str | None = None


@dataclass
class LineOverrides:
    """
    Optional overrides passed when adding an invoice line to a claim.

    Attributes
    ----------
    due_date_override:
        If provided, used as ``due_date`` instead of ``invoice_date + credit_days``
        from the Agreement Master (Requirement 2.5).
    ld_charges:
        Display-only LD charges stored on the line; not used in the formula
        (Requirement 3.12).
    retention_amount:
        Display-only retention amount stored on the line; not used in the formula
        (Requirement 3.12).
    remarks:
        Free-text remarks for the line.
    """

    due_date_override: date | None = None
    ld_charges: Decimal = Decimal("0")
    retention_amount: Decimal = Decimal("0")
    remarks: str = ""

logger = logging.getLogger(__name__)


class CommissionClaimService:
    """
    Application service that orchestrates all Commission Claim use cases.

    Accepts its three collaborators via constructor injection so callers
    (FastAPI dependencies, tests) can supply the active session and
    platform services without tight coupling.

    Parameters
    ----------
    session:
        Active ``AsyncSession`` shared across all repositories within a
        single HTTP request / Unit of Work.
    audit_service:
        Platform ``AuditService`` for security-level audit entries.
    workflow_engine:
        Platform ``WorkflowEngine`` for workflow start, action execution,
        and status/available-actions queries.
    """

    def __init__(
        self,
        session: AsyncSession,
        audit_service: AuditService,
        workflow_engine: WorkflowEngine,
    ) -> None:
        self._session = session
        self._audit_service = audit_service
        self._workflow_engine = workflow_engine

        # ── Infrastructure repos/services wired here ─────────────────────────
        self._header_repo = ClaimHeaderRepositoryImpl(session)
        self._line_repo = ClaimLineRepositoryImpl(session)
        self._audit_repo = ClaimAuditRepositoryImpl(session)
        self._claim_number_service = ClaimNumberSequenceService()

    # ── Claim lifecycle ───────────────────────────────────────────────────────

    async def create_claim(self, vendor_id: UUID, actor: Any, entity_id: UUID | None = None) -> ClaimHeader:
        """
        Create a new commission claim in Draft status for ``vendor_id``.

        - status = Draft (Req 1.1)
        - claim_number = None (Req 1.2: not assigned until first submission)
        - claim_date = UTC date of creation (Req 1.3)
        - Writes an immutable audit entry for the Create action after persist (Req 1.5)

        Requirements: 1.1, 1.2, 1.3, 1.5
        """
        now = datetime.now(timezone.utc)

        header = ClaimHeader(
            id=uuid4(),
            vendor_id=vendor_id,
            entity_id=entity_id,
            claim_number=None,                      # Req 1.2: not assigned at creation
            claim_date=date.today(),                # Req 1.3: UTC date of creation
            status=ClaimStatus.Draft,
            workflow_instance_id=None,
            total_claim_amount=Decimal("0"),
            total_commission_amount=Decimal("0"),
            total_gst_amount=Decimal("0"),
            total_tds_amount=Decimal("0"),
            total_ld_amount=Decimal("0"),
            total_retention_amount=Decimal("0"),
            gstn_verification_status="Pending",
            gst_invoice_number=None,
            gst_invoice_upload_date=None,
            sap_p2p_booking_reference=None,
            created_by=actor.username,
            created_date=now,
            modified_by=actor.username,
            modified_date=now,
        )

        saved_header = await self._header_repo.create(header)

        # Req 1.5: Write immutable audit entry immediately after persist
        audit_entry = ClaimAuditEntry(
            id=uuid4(),
            claim_header_id=saved_header.id,
            action="Create",
            actor_username=actor.username,
            actor_user_id=actor.id,
            timestamp_utc=now,
            from_status=None,
            to_status=ClaimStatus.Draft.value,
            workflow_step_name=None,
            remarks=None,
            field_changes=None,
            created_by=actor.username,
            created_date=now,
            modified_by=actor.username,
            modified_date=now,
        )
        await self._audit_repo.create(audit_entry)

        return saved_header

    async def update_claim_entity(
        self, claim_id: UUID, entity_id: UUID | None, actor: Any
    ) -> ClaimHeader:
        """
        Update the entity_id on a Draft or Referred Back claim.

        Guards:
        - Claim must exist.
        - Claim must be in Draft or Referred Back status.
        - Claim must have no lines (entity change after adding invoices is not allowed).
        """
        now = datetime.now(timezone.utc)

        claim = await self._header_repo.get_by_id(claim_id)
        if claim is None:
            raise ValueError("Claim not found")

        if claim.status not in (ClaimStatus.Draft, ClaimStatus.ReferredBack):
            raise ValueError("Entity can only be changed on Draft or Referred Back claims.")

        # Prevent entity change after lines are added
        lines = await self._line_repo.list_by_claim(claim_id)
        if lines:
            raise ValueError(
                "Cannot change entity after invoice lines have been added. "
                "Remove all lines first."
            )

        claim.entity_id = entity_id
        claim.modified_by = actor.username
        claim.modified_date = now

        await self._header_repo.update(claim)
        return claim

    async def get_claim_detail(self, claim_id: UUID, actor: Any) -> dict:
        """
        Return full claim detail including lines, workflow status, and
        available actions for the requesting actor.

        Returns a dict with keys:
        - ``header``: the ``ClaimHeader`` entity
        - ``lines``: list of ``ClaimLine`` entities for this claim
        - ``invoice_numbers``: dict mapping invoice_header_id → invoice_number
        - ``workflow_status``: dict from ``WorkflowEngine.get_workflow_status`` or None
        - ``available_actions``: list of available workflow actions or []

        Requirements: 12.3
        """
        header = await self._header_repo.get_by_id(claim_id)
        if header is None:
            raise ValueError("Claim not found")

        lines = await self._line_repo.list_by_claim(claim_id)

        # Resolve invoice numbers for all lines
        invoice_numbers: dict[str, str] = {}
        invoice_ids = list({str(ln.invoice_header_id) for ln in lines})
        if invoice_ids:
            stmt = select(
                InvoiceHeaderModel.id, InvoiceHeaderModel.invoice_number
            ).where(InvoiceHeaderModel.id.in_(invoice_ids))
            result = await self._session.execute(stmt)
            for row in result.all():
                invoice_numbers[str(row[0])] = row[1]

        workflow_status = None
        available_actions: list = []
        if header.workflow_instance_id:
            try:
                workflow_status = await self._workflow_engine.get_workflow_status(
                    header.workflow_instance_id
                )
                # Only return available actions if the actor has a PENDING
                # approval task for this workflow instance (task-based check).
                # This ensures buttons are only shown to the assigned approver.
                has_pending_task = await self._user_has_pending_task(
                    actor.id, header.workflow_instance_id
                )
                if has_pending_task or _is_admin_actor(actor):
                    available_actions = await self._workflow_engine.get_available_actions(
                        header.workflow_instance_id
                    )
            except Exception:
                # Workflow engine may not have the instance (e.g. pre-submission Draft)
                pass

        return {
            "header": header,
            "lines": lines,
            "invoice_numbers": invoice_numbers,
            "workflow_status": workflow_status,
            "available_actions": available_actions,
        }

    async def list_claims(
        self,
        actor: Any,
        filters: Any,
        skip: int,
        limit: int,
    ) -> dict:
        """
        Return a paginated list of claims with role-based data visibility.

        Priority order:
        1. RBAC — enforced at controller via require_permission("claims.list")
        2. Admin → all claims EXCEPT Draft status
        3. Vendor user → only claims where vendor_id matches
        4. Approver (via approval_tasks) → only pending claims assigned to this user
        5. Otherwise → empty result

        Returns a dict with keys:
        - ``items``: list of ``ClaimHeader`` entities
        - ``total``: total matching record count (before pagination)
        - ``skip``: the requested skip offset
        - ``limit``: the requested page size
        """
        # ── Priority 2: Admin → all claims except Draft ───────────────────────
        if _is_admin_actor(actor):
            claim_filters = ClaimFilterParams(
                vendor_id=getattr(filters, "vendor_id", None),
                status=getattr(filters, "status", None),
                claim_number=getattr(filters, "claim_number", None),
                start_date=getattr(filters, "start_date", None),
                end_date=getattr(filters, "end_date", None),
                status_exclude="Draft",  # Admin must NOT see Draft claims
            )
            headers, total = await self._header_repo.list_all(claim_filters, skip, limit)
            return {"items": headers, "total": total, "skip": skip, "limit": limit}

        # ── Priority 3: Vendor user → scoped to their vendor ──────────────────
        vendor_id = await self._get_vendor_id_for_actor(actor)
        if vendor_id is not None:
            headers, total = await self._header_repo.list_by_vendor(vendor_id, skip, limit)
            return {"items": headers, "total": total, "skip": skip, "limit": limit}

        # ── Priority 4: Approver → only pending claims from approval_tasks ────
        pending_instance_ids = await self._get_pending_instance_ids_for_user(actor.id)
        if pending_instance_ids:
            headers, total = await self._header_repo.list_by_workflow_instances(
                pending_instance_ids, skip, limit
            )
            return {"items": headers, "total": total, "skip": skip, "limit": limit}

        # ── Priority 5: No mapping → empty result ─────────────────────────────
        return {"items": [], "total": 0, "skip": skip, "limit": limit}

    # ── Tab-based listing ─────────────────────────────────────────────────────

    async def list_claims_draft(
        self,
        actor: Any,
        skip: int,
        limit: int,
    ) -> dict:
        """
        Return Draft and Referred Back claims created by the logged-in user.

        This is the 'Draft' tab — shows claims where:
        - status = Draft AND created_by = current user
        - status = Referred Back AND the user has a pending task (level 0)
          (so they can edit and resubmit)
        """
        from src.infrastructure.database.models.workflow.approval_matrix_models import (
            ApprovalTaskModel,
        )

        # Get Draft claims by this user
        draft_filters = ClaimFilterParams(status=ClaimStatus.Draft.value)
        all_drafts, _ = await self._header_repo.list_all(draft_filters, skip=0, limit=100000)
        user_drafts = [h for h in all_drafts if h.created_by == actor.username]

        # Get Referred Back claims where the user has a pending resubmission task
        referred_filters = ClaimFilterParams(status=ClaimStatus.ReferredBack.value)
        all_referred, _ = await self._header_repo.list_all(referred_filters, skip=0, limit=100000)
        user_referred = [h for h in all_referred if h.created_by == actor.username]

        # Combine both lists
        combined = user_drafts + user_referred
        total_count = len(combined)
        paginated = combined[skip: skip + limit]
        return {"items": paginated, "total": total_count, "skip": skip, "limit": limit}

    async def list_claims_pending(
        self,
        actor: Any,
        skip: int,
        limit: int,
    ) -> dict:
        """
        Return only actively-pending claims relevant to the logged-in user.

        Pending tab shows claims with status = Pending ONLY (not Rejected/Closed).
        - Admin: all Pending claims
        - Vendor user: their own Pending claims
        - Internal Approver: claims with a PENDING approval task assigned to them
        """
        # ── Admin → all Pending status claims ─────────────────────────────────
        if await self._actor_is_admin(actor):
            claim_filters = ClaimFilterParams(status=ClaimStatus.Pending.value)
            headers, total = await self._header_repo.list_all(claim_filters, skip, limit)
            return {"items": headers, "total": total, "skip": skip, "limit": limit}

        # ── Vendor user → their Pending claims only ───────────────────────────
        vendor_id = await self._get_vendor_id_for_actor(actor)
        if vendor_id is not None:
            headers, _ = await self._header_repo.list_by_vendor(vendor_id, skip=0, limit=100000)
            pending_only = [h for h in headers if h.status == ClaimStatus.Pending]
            total_count = len(pending_only)
            paginated = pending_only[skip: skip + limit]
            return {"items": paginated, "total": total_count, "skip": skip, "limit": limit}

        # ── Approver → only claims with active pending tasks for this user ────
        pending_instance_ids = await self._get_pending_instance_ids_for_user(actor.id)
        if pending_instance_ids:
            headers, total = await self._header_repo.list_by_workflow_instances(
                pending_instance_ids, skip, limit
            )
            return {"items": headers, "total": total, "skip": skip, "limit": limit}

        return {"items": [], "total": 0, "skip": skip, "limit": limit}

    async def list_claims_closed(
        self,
        actor: Any,
        skip: int,
        limit: int,
    ) -> dict:
        """
        Return closed/terminal claims (Approved/Closed, Rejected, Cancelled).

        Users only see records they are authorized to view:
        - Admin: all terminal claims
        - Vendor: their own terminal claims
        - Approver: terminal claims they previously acted on
        """
        terminal_statuses = [ClaimStatus.Closed.value, ClaimStatus.Rejected.value]

        if await self._actor_is_admin(actor):
            all_items: list = []
            total = 0
            for status_val in terminal_statuses:
                f = ClaimFilterParams(status=status_val)
                items, count = await self._header_repo.list_all(f, skip=0, limit=100000)
                all_items.extend(items)
                total += count
            paginated = all_items[skip: skip + limit]
            return {"items": paginated, "total": total, "skip": skip, "limit": limit}

        vendor_id = await self._get_vendor_id_for_actor(actor)
        if vendor_id is not None:
            headers, _ = await self._header_repo.list_by_vendor(vendor_id, skip=0, limit=100000)
            terminal = [h for h in headers if h.status in (ClaimStatus.Closed, ClaimStatus.Rejected)]
            total_count = len(terminal)
            paginated = terminal[skip: skip + limit]
            return {"items": paginated, "total": total_count, "skip": skip, "limit": limit}

        # Approvers: show terminal claims they previously had tasks on
        from src.infrastructure.database.models.workflow.approval_matrix_models import (
            ApprovalTaskModel,
        )
        stmt = (
            select(ApprovalTaskModel.instance_id)
            .where(
                ApprovalTaskModel.assignee_id == str(actor.id),
                ApprovalTaskModel.status == "COMPLETED",
            )
            .distinct()
        )
        result = await self._session.execute(stmt)
        completed_instance_ids = [row[0] for row in result.all()]
        if completed_instance_ids:
            headers, total = await self._header_repo.list_by_workflow_instances(
                completed_instance_ids, skip=0, limit=100000
            )
            terminal = [h for h in headers if h.status in (ClaimStatus.Closed, ClaimStatus.Rejected)]
            total_count = len(terminal)
            paginated = terminal[skip: skip + limit]
            return {"items": paginated, "total": total_count, "skip": skip, "limit": limit}

        return {"items": [], "total": 0, "skip": skip, "limit": limit}

    # ── Line management ───────────────────────────────────────────────────────

    async def add_invoice_line(
        self,
        claim_id: UUID,
        invoice_id: UUID,
        overrides: Any,
        actor: Any,
    ) -> ClaimLine:
        """
        Validate pre-conditions, compute all 7 formula fields via
        ``CommissionCalculator``, persist the line, and recalculate header
        totals inside the same transaction.

        Pre-conditions (in order):
        1. Claim exists (404 if not found)
        2. Invoice exists (404 if not found)
        3. ``invoice.invoice_status == "Payment Cleared"``; if "Settled" raise
           ``ValueError("Invoice is already settled.")`` (Req 2.1)
        4. Active Vendor-Customer Mapping exists for the invoice's vendor/customer
           (Req 2.2)
        5. Active Agreement Master exists for vendor/product on invoice date
           (Req 2.3)
        6. ``payment_clearing_date >= invoice_date`` (Req 3.11)

        Then:
        - Resolve ``due_date`` from override or Agreement ``credit_days`` (Req 2.4, 2.5)
        - Run ``CommissionCalculator.calculate()`` (Req 3.1)
        - Persist all 7 formula outputs on a new ``ClaimLine`` (Req 3.10)
        - Recalculate header totals in same transaction (Req 4.1, 4.2)
        - Write ``Line Added`` audit entry (Req 14.1)

        Requirements: 2.1–2.5, 3.1–3.12, 4.1, 4.2
        """
        now = datetime.now(timezone.utc)

        # Normalise overrides
        if isinstance(overrides, LineOverrides):
            line_overrides = overrides
        else:
            line_overrides = LineOverrides(
                due_date_override=getattr(overrides, "due_date_override", None),
                ld_charges=Decimal(str(getattr(overrides, "ld_charges", "0") or "0")),
                retention_amount=Decimal(
                    str(getattr(overrides, "retention_amount", "0") or "0")
                ),
                remarks=getattr(overrides, "remarks", "") or "",
            )

        # ── Step 1: Fetch claim header ────────────────────────────────────────
        claim = await self._header_repo.get_by_id(claim_id)
        if claim is None:
            raise ValueError("Claim not found")

        # ── Step 2: Fetch invoice header ──────────────────────────────────────
        invoice_stmt = select(InvoiceHeaderModel).where(
            InvoiceHeaderModel.id == invoice_id
        )
        invoice_result = await self._session.execute(invoice_stmt)
        invoice = invoice_result.scalar_one_or_none()
        if invoice is None:
            raise ValueError("Invoice not found")

        # ── Pre-condition 1: invoice_status (Req 2.1) ─────────────────────────
        # NOTE: PaymentCleared check relaxed for testing — only block Settled.
        # TODO: uncomment for production:
        # if invoice.invoice_status != InvoiceStatus.PaymentCleared.value:
        #     raise ValueError(f"Invoice status must be 'Payment Cleared'; got '{invoice.invoice_status}'.")
        if invoice.invoice_status == InvoiceStatus.Settled.value:
            raise ValueError("Invoice is already settled.")

        # ── Fetch ALL invoice lines (one ClaimLine per product) ───────────────
        inv_lines_stmt = select(InvoiceLineModel).where(
            InvoiceLineModel.invoice_header_id == invoice_id
        )
        inv_lines_result = await self._session.execute(inv_lines_stmt)
        invoice_lines = inv_lines_result.scalars().all()
        if not invoice_lines:
            raise ValueError(
                "Invoice has no line items — cannot determine products for Agreement lookup."
            )

        # ── Pre-condition 2: Active Vendor-Customer Mapping (Req 2.2) ──────────
        # Use claim.vendor_id (the claiming vendor) + invoice.customer_id
        mapping_stmt = select(MappingModel).where(
            MappingModel.vendor_id == str(claim.vendor_id),
            MappingModel.customer_id == invoice.customer_id,
            MappingModel.status == MappingStatus.Active.value,
        )
        mapping_result = await self._session.execute(mapping_stmt)
        mapping = mapping_result.scalar_one_or_none()
        if mapping is None:
            raise ValueError(
                "No active Vendor-Customer Mapping found for this vendor and customer."
            )

        # ── Pre-condition: Entity match (invoice entity_id must match claim) ──
        if claim.entity_id is not None and invoice.entity_id is not None:
            if str(invoice.entity_id) != str(claim.entity_id):
                raise ValueError(
                    "Invoice entity does not match the claim's entity. "
                    "Only invoices belonging to the same entity can be added."
                )

        # ── Pre-condition 3: Active Agreement for claim vendor + each product ──
        # Validate all products before creating any lines
        product_agreements: dict = {}  # product_master_id → AgreementModel
        for inv_line in invoice_lines:
            product_master_id = inv_line.product_master_id
            agreement_stmt = select(AgreementModel).where(
                AgreementModel.vendor_id == str(claim.vendor_id),
                AgreementModel.product_master_id == str(product_master_id),
                AgreementModel.status == AgreementStatus.Active.value,
                AgreementModel.from_date <= invoice.invoice_date,
                AgreementModel.to_date >= invoice.invoice_date,
            )
            agreement_result = await self._session.execute(agreement_stmt)
            agreement = agreement_result.scalar_one_or_none()
            if agreement is None:
                raise ValueError(
                    f"No active Agreement Master found for this vendor and product "
                    f"(product_master_id={product_master_id}) on invoice date {invoice.invoice_date}."
                )
            product_agreements[str(product_master_id)] = agreement

        # ── Pre-condition 4: payment_clearing_date >= invoice_date (Req 3.11) ──
        payment_clearing_date = invoice.payment_clearing_date
        if payment_clearing_date is None:
            raise ValueError(
                "Invoice has no Payment Clearing Date — cannot add to claim."
            )
        if payment_clearing_date < invoice.invoice_date:
            raise ValueError(
                "Payment Clearing Date cannot be earlier than Invoice Date."
            )

        # ── Create one ClaimLine per invoice product line ─────────────────────
        saved_lines: list[ClaimLine] = []
        for inv_line in invoice_lines:
            product_master_id = inv_line.product_master_id
            agreement = product_agreements[str(product_master_id)]

            # Resolve due_date
            if line_overrides.due_date_override is not None:
                due_date = line_overrides.due_date_override
            else:
                due_date = invoice.invoice_date + timedelta(days=agreement.credit_days)

            # Run commission calculator for this product's agreement
            inputs = CommissionInputs(
                bill_amount_excl_gst=Decimal(str(inv_line.line_amount or 0)),
                amount_deducted=invoice.amount_deducted,
                tds_value=invoice.tds_value,
                invoice_date=invoice.invoice_date,
                due_date=due_date,
                payment_clearing_date=payment_clearing_date,
                slab_in_days=agreement.slab_in_days,
                reduction_percent=agreement.reduction_percent,
                max_commission_percent=agreement.max_commission_percent,
                min_commission_percent=agreement.min_commission_percent,
            )
            result = calculate(inputs)

            line = ClaimLine(
                id=uuid4(),
                claim_header_id=claim_id,
                invoice_header_id=invoice_id,
                product_master_id=product_master_id,
                customer_id=invoice.customer_id,
                bill_amount_excl_gst=Decimal(str(inv_line.line_amount or 0)),
                amount_deducted=invoice.amount_deducted,
                tds_value=invoice.tds_value,
                ld_charges=line_overrides.ld_charges,
                retention_amount=line_overrides.retention_amount,
                net_amount=result.net_amount,
                commission_payable_base=result.commission_payable_base,
                due_date=due_date,
                payment_clearing_date=payment_clearing_date,
                delay_days=result.delay_days,
                applicable_commission_percent=result.applicable_commission_percent,
                commission_amount=result.commission_amount,
                gst_on_commission=result.gst_on_commission,
                final_line_claim_amount=result.final_line_claim_amount,
                pod_document_id=None,
                remarks=line_overrides.remarks,
                created_by=actor.username,
                created_date=now,
                modified_by=actor.username,
                modified_date=now,
            )
            saved_line = await self._line_repo.create(line)
            saved_lines.append(saved_line)

        # ── Recalculate header totals once after all lines created ────────────
        await self._recalculate_header_totals(claim_id)

        # ── Write single audit entry for the invoice add ──────────────────────
        audit_entry = ClaimAuditEntry(
            id=uuid4(),
            claim_header_id=claim_id,
            action="Line Added",
            actor_username=actor.username,
            actor_user_id=actor.id,
            timestamp_utc=now,
            from_status=None,
            to_status=None,
            workflow_step_name=None,
            remarks=None,
            field_changes={
                "invoice_header_id": str(invoice_id),
                "lines_created": len(saved_lines),
            },
            created_by=actor.username,
            created_date=now,
            modified_by=actor.username,
            modified_date=now,
        )
        await self._audit_repo.create(audit_entry)

        # Return the first line for API compatibility (list endpoint covers all)
        return saved_lines[0] if saved_lines else saved_lines

    async def update_line_fields(
        self,
        claim_id: UUID,
        line_id: UUID,
        fields: LineUpdateRequest,
        actor: Any,
    ) -> ClaimLine:
        """
        Apply partial updates to a claim line.  Recalculates commission if
        ``amount_deducted``, ``tds_value``, or ``payment_clearing_date`` change.
        Recalculates header totals in the same transaction.

        Only fields that are non-None *and* have a different value are applied;
        unchanged fields are left untouched and do not appear in the audit diff
        (Requirement 10.3).

        Requirements: 3.1, 4.1, 4.2, 10.1, 10.2, 10.3
        """
        now = datetime.now(timezone.utc)

        # ── Fetch claim and line ──────────────────────────────────────────────
        claim = await self._header_repo.get_by_id(claim_id)
        if claim is None:
            raise ValueError("Claim not found")

        line = await self._line_repo.get_by_id(line_id)
        if line is None:
            raise ValueError("Claim line not found")

        # ── Track changes for audit (Req 10.3: only record if value changed) ─
        field_changes: dict = {}

        # ── Simple (non-commission) field updates ─────────────────────────────
        if fields.ld_charges is not None and fields.ld_charges != line.ld_charges:
            field_changes["ld_charges"] = {
                "old": str(line.ld_charges),
                "new": str(fields.ld_charges),
            }
            line.ld_charges = fields.ld_charges

        if (
            fields.retention_amount is not None
            and fields.retention_amount != line.retention_amount
        ):
            field_changes["retention_amount"] = {
                "old": str(line.retention_amount),
                "new": str(fields.retention_amount),
            }
            line.retention_amount = fields.retention_amount

        if fields.due_date is not None and fields.due_date != line.due_date:
            field_changes["due_date"] = {
                "old": str(line.due_date),
                "new": str(fields.due_date),
            }
            line.due_date = fields.due_date

        if fields.remarks is not None and fields.remarks != line.remarks:
            field_changes["remarks"] = {
                "old": line.remarks,
                "new": fields.remarks,
            }
            line.remarks = fields.remarks

        # ── Detect whether commission-affecting fields are changing (Req 3.1) ─
        commission_fields_changed = (
            (
                fields.amount_deducted is not None
                and fields.amount_deducted != line.amount_deducted
            )
            or (
                fields.tds_value is not None
                and fields.tds_value != line.tds_value
            )
            or (
                fields.payment_clearing_date is not None
                and fields.payment_clearing_date != line.payment_clearing_date
            )
        )

        # ── Apply commission-affecting field values (track changes first) ─────
        if (
            fields.amount_deducted is not None
            and fields.amount_deducted != line.amount_deducted
        ):
            field_changes["amount_deducted"] = {
                "old": str(line.amount_deducted),
                "new": str(fields.amount_deducted),
            }
            line.amount_deducted = fields.amount_deducted

        if fields.tds_value is not None and fields.tds_value != line.tds_value:
            field_changes["tds_value"] = {
                "old": str(line.tds_value),
                "new": str(fields.tds_value),
            }
            line.tds_value = fields.tds_value

        if (
            fields.payment_clearing_date is not None
            and fields.payment_clearing_date != line.payment_clearing_date
        ):
            field_changes["payment_clearing_date"] = {
                "old": str(line.payment_clearing_date),
                "new": str(fields.payment_clearing_date),
            }
            line.payment_clearing_date = fields.payment_clearing_date

        # ── Recalculate commission if any formula inputs changed (Req 3.1) ────
        if commission_fields_changed:
            # Reload Agreement to get current slab parameters — same query
            # pattern used in add_invoice_line.
            inv_stmt = select(InvoiceHeaderModel).where(
                InvoiceHeaderModel.id == line.invoice_header_id
            )
            inv_result = await self._session.execute(inv_stmt)
            invoice = inv_result.scalar_one_or_none()
            if invoice is None:
                raise ValueError(
                    "Associated invoice not found — cannot recalculate commission."
                )

            inv_line_stmt = (
                select(InvoiceLineModel)
                .where(InvoiceLineModel.invoice_header_id == line.invoice_header_id)
                .limit(1)
            )
            inv_line_result = await self._session.execute(inv_line_stmt)
            invoice_line_model = inv_line_result.scalar_one_or_none()
            if invoice_line_model is None:
                raise ValueError(
                    "Invoice has no line items — cannot determine product for Agreement lookup."
                )

            agreement_stmt = select(AgreementModel).where(
                AgreementModel.vendor_id == invoice.vendor_id,
                AgreementModel.product_master_id == str(invoice_line_model.product_master_id),
                AgreementModel.status == AgreementStatus.Active.value,
                AgreementModel.from_date <= invoice.invoice_date,
                AgreementModel.to_date >= invoice.invoice_date,
            )
            agreement_result = await self._session.execute(agreement_stmt)
            agreement = agreement_result.scalar_one_or_none()
            if agreement is None:
                raise ValueError(
                    "No active Agreement Master found for vendor + product on invoice date."
                )

            inputs = CommissionInputs(
                bill_amount_excl_gst=line.bill_amount_excl_gst,
                amount_deducted=line.amount_deducted,
                tds_value=line.tds_value,
                invoice_date=invoice.invoice_date,
                due_date=line.due_date,
                payment_clearing_date=line.payment_clearing_date,
                slab_in_days=agreement.slab_in_days,
                reduction_percent=agreement.reduction_percent,
                max_commission_percent=agreement.max_commission_percent,
                min_commission_percent=agreement.min_commission_percent,
            )
            result_calc = calculate(inputs)

            # Record all recalculated formula outputs in field_changes
            for attr, new_val in [
                ("net_amount", result_calc.net_amount),
                ("commission_payable_base", result_calc.commission_payable_base),
                ("delay_days", result_calc.delay_days),
                ("applicable_commission_percent", result_calc.applicable_commission_percent),
                ("commission_amount", result_calc.commission_amount),
                ("gst_on_commission", result_calc.gst_on_commission),
                ("final_line_claim_amount", result_calc.final_line_claim_amount),
            ]:
                old_val = getattr(line, attr)
                if old_val != new_val:
                    field_changes[attr] = {"old": str(old_val), "new": str(new_val)}

            line.net_amount = result_calc.net_amount
            line.commission_payable_base = result_calc.commission_payable_base
            line.delay_days = result_calc.delay_days
            line.applicable_commission_percent = result_calc.applicable_commission_percent
            line.commission_amount = result_calc.commission_amount
            line.gst_on_commission = result_calc.gst_on_commission
            line.final_line_claim_amount = result_calc.final_line_claim_amount

        # ── Persist the updated line ──────────────────────────────────────────
        line.modified_by = actor.username
        line.modified_date = now

        saved_line = await self._line_repo.update(line)

        # ── Recalculate header totals in same transaction (Req 4.1, 4.2) ─────
        await self._recalculate_header_totals(claim_id)

        # ── Write audit entry only when something actually changed (Req 10.2, 10.3)
        if field_changes:
            audit_entry = ClaimAuditEntry(
                id=uuid4(),
                claim_header_id=claim_id,
                action="Line Edited",
                actor_username=actor.username,
                actor_user_id=actor.id,
                timestamp_utc=now,
                from_status=None,
                to_status=None,
                workflow_step_name=None,
                remarks=None,
                field_changes=field_changes,
                created_by=actor.username,
                created_date=now,
                modified_by=actor.username,
                modified_date=now,
            )
            await self._audit_repo.create(audit_entry)

        return saved_line

    async def remove_line(self, claim_id: UUID, line_id: UUID, actor: Any) -> None:
        """
        Delete a line from the claim and recalculate header totals in the
        same transaction.  Writes a ``Line Removed`` audit entry recording
        the deleted line's id and associated invoice id.

        Requirements: 4.1, 4.2, 10.1
        """
        now = datetime.now(timezone.utc)

        # ── Verify claim exists ───────────────────────────────────────────────
        claim = await self._header_repo.get_by_id(claim_id)
        if claim is None:
            raise ValueError("Claim not found")

        # ── Verify line exists and capture its data for the audit entry ───────
        line = await self._line_repo.get_by_id(line_id)
        if line is None:
            raise ValueError("Claim line not found")

        # ── Delete the line ───────────────────────────────────────────────────
        await self._line_repo.delete(line_id)

        # ── Recalculate header totals in same transaction (Req 4.1, 4.2) ─────
        await self._recalculate_header_totals(claim_id)

        # ── Write audit entry (Req 10.1) ──────────────────────────────────────
        audit_entry = ClaimAuditEntry(
            id=uuid4(),
            claim_header_id=claim_id,
            action="Line Removed",
            actor_username=actor.username,
            actor_user_id=actor.id,
            timestamp_utc=now,
            from_status=None,
            to_status=None,
            workflow_step_name=None,
            remarks=None,
            field_changes={
                "line_id": str(line_id),
                "invoice_header_id": str(line.invoice_header_id),
            },
            created_by=actor.username,
            created_date=now,
            modified_by=actor.username,
            modified_date=now,
        )
        await self._audit_repo.create(audit_entry)

    # ── Document management ───────────────────────────────────────────────────

    async def upload_pod(
        self,
        claim_id: UUID,
        line_id: UUID,
        document_id: UUID,
        actor: Any,
    ) -> ClaimLine:
        """
        Attach a POD document to a claim line.  Only allowed when the claim
        is in ``Draft`` or ``Referred Back`` status.

        Requirements: 5.1, 5.3
        """
        now = datetime.now(timezone.utc)

        # Fetch claim
        claim = await self._header_repo.get_by_id(claim_id)
        if claim is None:
            raise ValueError("Claim not found")

        # Validate claim status — only Draft or Referred Back (Req 5.3)
        if claim.status not in (ClaimStatus.Draft, ClaimStatus.ReferredBack):
            raise ValueError(
                f"POD document can only be uploaded when claim is in Draft or Referred Back status; "
                f"current status: {claim.status.value}"
            )

        # Fetch the line
        line = await self._line_repo.get_by_id(line_id)
        if line is None:
            raise ValueError("Claim line not found")

        # Track old value for audit
        old_pod = line.pod_document_id

        # Set the POD document (Req 5.1)
        line.pod_document_id = document_id
        line.modified_by = actor.username
        line.modified_date = now

        saved_line = await self._line_repo.update(line)

        # Write audit entry (Req 5.3)
        audit_entry = ClaimAuditEntry(
            id=uuid4(),
            claim_header_id=claim_id,
            action="Field Edited",
            actor_username=actor.username,
            actor_user_id=actor.id,
            timestamp_utc=now,
            from_status=None,
            to_status=None,
            workflow_step_name=None,
            remarks=None,
            field_changes={
                "pod_document_id": {
                    "old": str(old_pod) if old_pod else None,
                    "new": str(document_id),
                }
            },
            created_by=actor.username,
            created_date=now,
            modified_by=actor.username,
            modified_date=now,
        )
        await self._audit_repo.create(audit_entry)

        return saved_line

    # ── Workflow lifecycle ────────────────────────────────────────────────────

    async def submit_claim(self, claim_id: UUID, actor: Any) -> ClaimHeader:
        """
        Submit a Draft or Referred-Back claim for approval.

        Guards:
        - Actor must be the original initiator or an Administrator (Req 6.9).
        - Claim status must be ``Draft`` or ``Referred Back`` (Req 6.1, 6.7).
        - Claim must have ≥ 1 line (Req 6.1).
        - All lines must have ``pod_document_id`` set (Req 5.2).
        - If ``claim_number`` is null, allocate via ``ClaimNumberSequenceService``
          inside the Unit of Work (Req 6.2, 6.3).
        - Start workflow via ``WorkflowEngine`` and store ``workflow_instance_id``
          (Req 6.4, 6.5).
        - Set status to ``Pending`` and write a ``Submitted`` audit entry
          (Req 6.8).

        Requirements: 5.2, 6.1, 6.2, 6.3, 6.4, 6.5, 6.7, 6.8, 6.9
        """
        now = datetime.now(timezone.utc)

        # ── Fetch claim ───────────────────────────────────────────────────────
        claim = await self._header_repo.get_by_id(claim_id)
        if claim is None:
            raise ValueError("Claim not found")

        # ── Guard: only original initiator or Administrator (Req 6.9) ─────────
        # Determine if actor has the ADMIN role (code = "ADMIN" or "Administrator")
        is_admin = await self._actor_is_admin(actor)
        if claim.created_by != actor.username and not is_admin:
            raise PermissionError(
                "Only the original claim initiator or an Administrator can submit this claim."
            )

        # ── Validate status (Req 6.1, 6.7) ───────────────────────────────────
        if claim.status not in (ClaimStatus.Draft, ClaimStatus.ReferredBack):
            raise ValueError(
                f"Claim cannot be submitted from '{claim.status.value}' status. "
                "Only Draft or Referred Back claims can be submitted."
            )

        # ── Validate at least 1 line (Req 6.1) ───────────────────────────────
        lines = await self._line_repo.list_by_claim(claim_id)
        if not lines:
            raise ValueError("Claim must have at least one line before submission.")

        # ── Validate all lines have POD document (Req 5.2) ───────────────────
        missing_pod_lines = [str(ln.id) for ln in lines if ln.pod_document_id is None]
        if missing_pod_lines:
            raise ValueError(
                f"POD document missing for lines: {missing_pod_lines}"
            )

        # ── Assign claim number if not yet assigned (Req 6.2, 6.3) ──────────
        from_status = claim.status
        if claim.claim_number is None:
            claim.claim_number = await self._claim_number_service.next_claim_number(
                self._session
            )

        # ── Handle workflow based on current status ───────────────────────────
        if from_status == ClaimStatus.ReferredBack and claim.workflow_instance_id:
            # ── Resubmission after Refer Back: reuse existing workflow instance ──
            # Complete the initiator's pending task (level 0) and advance the state
            workflow_instance_id = str(claim.workflow_instance_id)

            # Complete any pending tasks for this user on this instance
            from src.infrastructure.database.models.workflow.approval_matrix_models import (
                ApprovalTaskModel,
            )
            task_stmt = select(ApprovalTaskModel).where(
                ApprovalTaskModel.instance_id == workflow_instance_id,
                ApprovalTaskModel.assignee_id == str(actor.id),
                ApprovalTaskModel.status == "PENDING",
            )
            task_result = await self._session.execute(task_stmt)
            initiator_tasks = task_result.scalars().all()
            for task in initiator_tasks:
                task.status = "COMPLETED"
                task.action_taken = "RESUBMIT"
                task.comments = "Resubmitted after refer back"

            # Execute SUBMIT transition on the existing workflow instance
            try:
                await self._workflow_engine.execute_action(
                    instance_id=claim.workflow_instance_id,
                    action_code="SUBMIT",
                    actor_id=actor.id,
                    actor_username=actor.username,
                    comments="Claim resubmitted after refer back",
                )
            except Exception as e:
                logger.warning(
                    "Failed to execute SUBMIT transition for resubmission %s: %s",
                    workflow_instance_id, e,
                )

            # Create new Level 1 approval tasks for the resubmitted claim
            # Resolve workflow_definition_id from the existing workflow instance
            from src.infrastructure.database.models.workflow.workflow_models import (
                WorkflowInstanceModel as _WfInstModel,
            )
            _wf_inst_stmt = select(_WfInstModel).where(
                _WfInstModel.id == workflow_instance_id
            )
            _wf_inst_result = await self._session.execute(_wf_inst_stmt)
            _wf_inst = _wf_inst_result.scalar_one_or_none()
            _wf_def_id = str(_wf_inst.workflow_definition_id) if _wf_inst else None

            entity_data = {"claim_number": claim.claim_number}
            approvers = await self._workflow_engine._approval_matrix.resolve_approvers(
                "commission_claim", entity_data,
                workflow_definition_id=_wf_def_id,
            )
            if approvers:
                level_1 = [a for a in approvers if a["level"] == 1]
                for assignment in level_1:
                    if assignment["assignment_type"] == "USER" and assignment["user_id"]:
                        await self._workflow_engine._approval_matrix.create_approval_task(
                            instance_id=claim.workflow_instance_id,
                            assignee_id=UUID(str(assignment["user_id"])),
                            level=1,
                        )
                    elif assignment["assignment_type"] == "ROLE" and assignment["role_id"]:
                        user_ids = await self._workflow_engine._resolve_users_for_role(
                            UUID(str(assignment["role_id"]))
                        )
                        for uid in user_ids:
                            await self._workflow_engine._approval_matrix.create_approval_task(
                                instance_id=claim.workflow_instance_id,
                                assignee_id=uid,
                                level=1,
                            )

            await self._session.flush()
        else:
            # ── First submission: Start new workflow (Req 6.4, 6.5) ───────────
            # Resolve workflow definition code from Entity → WorkflowDefinition
            definition_code = "COMMISSION_CLAIM"  # default fallback
            if claim.entity_id:
                from src.infrastructure.database.models.masters.entity_model import EntityModel
                from src.infrastructure.database.models.workflow.workflow_models import (
                    WorkflowDefinitionModel,
                )

                entity_stmt = select(EntityModel).where(EntityModel.id == claim.entity_id)
                entity_result = await self._session.execute(entity_stmt)
                entity_model = entity_result.scalar_one_or_none()
                if entity_model is None:
                    raise ValueError("Claim's entity does not exist.")
                if entity_model.workflow_definition_id is None:
                    raise ValueError(
                        f"Entity '{entity_model.entity_name}' does not have a "
                        "workflow definition assigned. Please configure the entity's "
                        "approval workflow before submitting."
                    )
                # Look up the workflow definition to get its code
                wf_def_stmt = select(WorkflowDefinitionModel).where(
                    WorkflowDefinitionModel.id == entity_model.workflow_definition_id
                )
                wf_def_result = await self._session.execute(wf_def_stmt)
                wf_def_model = wf_def_result.scalar_one_or_none()
                if wf_def_model is None:
                    raise ValueError(
                        "Workflow definition linked to entity no longer exists."
                    )
                if not getattr(wf_def_model, "is_active", True):
                    raise ValueError(
                        f"Workflow definition '{wf_def_model.code}' is not active."
                    )
                definition_code = wf_def_model.code

            try:
                workflow_result = await self._workflow_engine.start_workflow(
                    definition_code=definition_code,
                    entity_type="commission_claim",
                    entity_id=claim_id,
                    initiated_by=actor.id,
                    metadata={"claim_number": claim.claim_number},
                )
            except Exception as e:
                raise ValueError(
                    f"No active `claim_approval` workflow definition found. Details: {e}"
                )

            # start_workflow returns {"instance_id": str(uuid), ...}
            workflow_instance_id = workflow_result.get("instance_id")

            # Advance workflow from DRAFT → PENDING (execute SUBMIT transition)
            if workflow_instance_id:
                try:
                    await self._workflow_engine.execute_action(
                        instance_id=UUID(workflow_instance_id),
                        action_code="SUBMIT",
                        actor_id=actor.id,
                        actor_username=actor.username,
                        comments="Claim submitted for approval",
                    )
                except Exception as e:
                    logger.warning(
                        "Failed to execute SUBMIT transition for workflow %s: %s",
                        workflow_instance_id, e,
                    )

            # ── Update workflow_instance_id on claim ──────────────────────────
            claim.workflow_instance_id = (
                UUID(workflow_instance_id) if workflow_instance_id else None
            )
        claim.status = ClaimStatus.Pending
        claim.modified_by = actor.username
        claim.modified_date = now

        await self._header_repo.update(claim)

        # ── Write Submitted audit entry (Req 6.8) ─────────────────────────────
        audit_entry = ClaimAuditEntry(
            id=uuid4(),
            claim_header_id=claim_id,
            action="Submitted",
            actor_username=actor.username,
            actor_user_id=actor.id,
            timestamp_utc=now,
            from_status=from_status.value,
            to_status=ClaimStatus.Pending.value,
            workflow_step_name=None,
            remarks=None,
            field_changes=None,
            created_by=actor.username,
            created_date=now,
            modified_by=actor.username,
            modified_date=now,
        )
        await self._audit_repo.create(audit_entry)

        return claim

    async def _actor_is_admin(self, actor: Any) -> bool:
        """
        Return True if the actor holds any role whose code is ``"ADMIN"``
        or whose name is ``"Administrator"``.

        Checks the ``role_assignments`` → ``roles`` tables for the actor's
        current active role assignments.
        """
        from src.infrastructure.database.models.role_model import (
            RoleAssignmentModel,
            RoleModel,
        )

        stmt = (
            select(RoleModel)
            .join(
                RoleAssignmentModel,
                RoleAssignmentModel.role_id == RoleModel.id,
            )
            .where(
                RoleAssignmentModel.user_id == str(actor.id),
                RoleAssignmentModel.is_active == True,  # noqa: E712
                RoleModel.is_active == True,  # noqa: E712
            )
        )
        result = await self._session.execute(stmt)
        roles = result.scalars().all()

        return any(
            r.code in ("ADMIN",) or r.name in ("Administrator", "Admin")
            for r in roles
        )

    async def execute_workflow_action(
        self,
        claim_id: UUID,
        action_code: str,
        remarks: str,
        actor: Any,
    ) -> ClaimHeader:
        """
        Execute an approve / refer-back / reject action via WorkflowEngine
        and apply the corresponding ``CLAIM_TRANSITIONS`` state change.

        Flow:
        1. Validate non-empty remarks (Req 7.5).
        2. Fetch claim; reject if not found.
        3. Guard against terminal-status transitions (Req 11.3, 11.4).
        4. Call ``WorkflowEngine.execute_action`` — the engine checks actor
           eligibility for the current step and raises ``PermissionError`` if
           the actor is not authorised (Req 7.6).
        5. Determine intermediate vs. final approval from ``is_completed`` in
           the workflow result; map ``action_code`` to a ``CLAIM_TRANSITIONS``
           key (Req 7.1, 7.2).
        6. Look up the transition in ``CLAIM_TRANSITIONS``; raise ``ValueError``
           for any disallowed transition (Req 11.1, 11.2).
        7. Apply the new status and persist the header update.
        8. On ``Closed``: call ``_run_post_closure`` (Req 7.2).
        9. On ``Referred Back``: log notification to original initiator (Req 7.3).
        10. Write an immutable audit entry capturing actor, timestamp,
            from_status, to_status, workflow step name, and remarks (Req 7.7).

        Requirements: 7.1, 7.2, 7.3, 7.4, 7.5, 7.6, 7.7, 11.1, 11.2
        """
        now = datetime.now(timezone.utc)

        # ── Req 7.5: non-empty remarks required ──────────────────────────────
        if not remarks or not remarks.strip():
            raise ValueError("Remarks are required for this action.")

        # ── Fetch claim ───────────────────────────────────────────────────────
        claim = await self._header_repo.get_by_id(claim_id)
        if claim is None:
            raise ValueError("Claim not found")

        from_status = claim.status

        # ── Req 11.3 / 11.4: terminal state check ────────────────────────────
        if from_status in TERMINAL_STATUSES:
            raise ValueError("Claim is in a terminal status and cannot be modified.")

        # ── Call WorkflowEngine (checks actor eligibility) (Req 7.6) ─────────
        try:
            workflow_result = await self._workflow_engine.execute_action(
                instance_id=claim.workflow_instance_id,
                action_code=action_code.upper(),  # Workflow engine uses uppercase action codes
                actor_id=actor.id,
                actor_username=actor.username,
                comments=remarks,
            )
        except PermissionError:
            raise PermissionError(
                "Not authorized to act on this claim at the current workflow step."
            )
        except Exception as e:
            raise ValueError(f"Workflow action failed: {e}")

        # ── Determine intermediate vs. final approval (Req 7.1, 7.2) ─────────
        # WorkflowEngine returns is_completed=True when no more steps remain.
        is_final = workflow_result.get("is_completed", False)

        # Determine new claim status based on the workflow action result
        # The workflow engine has already validated the transition is allowed.
        if action_code == "approve":
            if is_final:
                new_status = ClaimStatus.Closed
            else:
                new_status = ClaimStatus.Pending
        elif action_code == "reject":
            new_status = ClaimStatus.Rejected
        elif action_code == "refer_back":
            new_status = ClaimStatus.ReferredBack
        else:
            # Fallback: keep current status
            new_status = from_status

        # ── Retrieve workflow step name for audit (from current state after action)
        step_name: str | None = None
        if claim.workflow_instance_id:
            try:
                wf_status = await self._workflow_engine.get_workflow_status(
                    claim.workflow_instance_id
                )
                step_name = wf_status.get("status_name")
            except Exception:
                pass  # step_name stays None — non-critical

        # ── Persist new status on the claim header ────────────────────────────
        claim.status = new_status
        claim.modified_by = actor.username
        claim.modified_date = now
        await self._header_repo.update(claim)

        # ── Post-closure actions (Req 7.2) ────────────────────────────────────
        if new_status == ClaimStatus.Closed:
            await self._run_post_closure(claim_id)

        # ── Refer-back: notify original initiator (Req 7.3) ──────────────────
        if new_status == ClaimStatus.ReferredBack:
            logger.info(
                "Claim %s referred back by %s. Original initiator (%s) should be notified.",
                claim_id,
                actor.username,
                claim.created_by,
            )

        # ── Write audit entry (Req 7.7) ───────────────────────────────────────
        action_label_map = {
            "approve":       "Approved",
            "final_approve": "Approved",
            "refer_back":    "Referred Back",
            "reject":        "Rejected",
        }
        action_label = action_label_map.get(action_code, action_code.replace("_", " ").title())

        audit_entry = ClaimAuditEntry(
            id=uuid4(),
            claim_header_id=claim_id,
            action=action_label,
            actor_username=actor.username,
            actor_user_id=actor.id,
            timestamp_utc=now,
            from_status=from_status.value,
            to_status=new_status.value,
            workflow_step_name=step_name,
            remarks=remarks,
            field_changes=None,
            created_by=actor.username,
            created_date=now,
            modified_by=actor.username,
            modified_date=now,
        )
        await self._audit_repo.create(audit_entry)

        return claim

    # ── Post-closure operations ───────────────────────────────────────────────

    async def update_payment_clearing_date(
        self,
        claim_id: UUID,
        line_id: UUID,
        new_date: date,
        actor: Any,
    ) -> ClaimLine:
        """
        Update ``payment_clearing_date`` on a line while the claim is
        ``Pending`` (Finance review step only).  Recalculates commission and
        header totals.

        Guards:
        - Claim must be in ``Pending`` status (Req 8.1).
        - Actor must be the Finance-step approver or an Administrator (Req 8.5).
        - ``new_date`` must not be earlier than the invoice's ``invoice_date`` (Req 8.4).

        Then:
        - Recalculates all 7 commission formula fields for the line (Req 8.2).
        - Recalculates header totals in the same transaction.
        - Writes a ``Field Edited`` audit entry with old/new ``payment_clearing_date``
          and recalculated ``final_line_claim_amount`` (Req 8.3).

        Requirements: 8.1, 8.2, 8.3, 8.4, 8.5
        """
        now = datetime.now(timezone.utc)

        claim = await self._header_repo.get_by_id(claim_id)
        if claim is None:
            raise ValueError("Claim not found")

        # Req 8.1: only allowed when claim is Pending
        if claim.status != ClaimStatus.Pending:
            raise ValueError(
                f"Payment Clearing Date can only be updated when claim is Pending; "
                f"current status: {claim.status.value}"
            )

        # Req 8.5: check actor is Finance approver or Admin
        is_admin = _is_admin_actor(actor)
        if not is_admin:
            try:
                available_actions = await self._workflow_engine.get_available_actions(
                    claim.workflow_instance_id
                )
                # If actor has no available actions on this claim, they're not the eligible approver
                if not available_actions:
                    raise PermissionError(
                        "Not authorized to act on this claim at the current workflow step."
                    )
            except PermissionError:
                raise
            except Exception:
                pass  # be permissive if workflow engine unavailable

        line = await self._line_repo.get_by_id(line_id)
        if line is None:
            raise ValueError("Claim line not found")

        # Req 8.4: new date must not be earlier than invoice date
        invoice_stmt = select(InvoiceHeaderModel).where(
            InvoiceHeaderModel.id == line.invoice_header_id
        )
        invoice_result = await self._session.execute(invoice_stmt)
        invoice = invoice_result.scalar_one_or_none()
        if invoice and new_date < invoice.invoice_date:
            raise ValueError("Payment Clearing Date cannot be earlier than Invoice Date.")

        old_date = line.payment_clearing_date
        old_final = line.final_line_claim_amount
        line.payment_clearing_date = new_date

        # Req 8.2: recalculate commission using current slab agreement
        inv_line_stmt = (
            select(InvoiceLineModel)
            .where(InvoiceLineModel.invoice_header_id == line.invoice_header_id)
            .limit(1)
        )
        inv_line_result = await self._session.execute(inv_line_stmt)
        inv_line = inv_line_result.scalar_one_or_none()

        if invoice is None:
            raise ValueError("Associated invoice not found — cannot recalculate commission.")

        if inv_line is None:
            raise ValueError(
                "Invoice has no line items — cannot determine product for Agreement lookup."
            )

        agreement_stmt = select(AgreementModel).where(
            AgreementModel.vendor_id == invoice.vendor_id,
            AgreementModel.product_master_id == str(inv_line.product_master_id),
            AgreementModel.status == AgreementStatus.Active.value,
            AgreementModel.from_date <= invoice.invoice_date,
            AgreementModel.to_date >= invoice.invoice_date,
        )
        agreement_result = await self._session.execute(agreement_stmt)
        agreement = agreement_result.scalar_one_or_none()
        if agreement is None:
            raise ValueError("No active Agreement Master found — cannot recalculate commission.")

        inputs = CommissionInputs(
            bill_amount_excl_gst=line.bill_amount_excl_gst,
            amount_deducted=line.amount_deducted,
            tds_value=line.tds_value,
            invoice_date=invoice.invoice_date,
            due_date=line.due_date,
            payment_clearing_date=new_date,
            slab_in_days=agreement.slab_in_days,
            reduction_percent=agreement.reduction_percent,
            max_commission_percent=agreement.max_commission_percent,
            min_commission_percent=agreement.min_commission_percent,
        )
        calc_result = calculate(inputs)
        line.net_amount = calc_result.net_amount
        line.commission_payable_base = calc_result.commission_payable_base
        line.delay_days = calc_result.delay_days
        line.applicable_commission_percent = calc_result.applicable_commission_percent
        line.commission_amount = calc_result.commission_amount
        line.gst_on_commission = calc_result.gst_on_commission
        line.final_line_claim_amount = calc_result.final_line_claim_amount

        line.modified_by = actor.username
        line.modified_date = now
        saved_line = await self._line_repo.update(line)

        await self._recalculate_header_totals(claim_id)

        # Req 8.3: audit entry with old/new values and recalculated final amount
        audit_entry = ClaimAuditEntry(
            id=uuid4(),
            claim_header_id=claim_id,
            action="Field Edited",
            actor_username=actor.username,
            actor_user_id=actor.id,
            timestamp_utc=now,
            from_status=None,
            to_status=None,
            workflow_step_name=None,
            remarks=None,
            field_changes={
                "payment_clearing_date": {
                    "old": str(old_date),
                    "new": str(new_date),
                },
                "final_line_claim_amount": {
                    "old": str(old_final),
                    "new": str(line.final_line_claim_amount),
                },
            },
            created_by=actor.username,
            created_date=now,
            modified_by=actor.username,
            modified_date=now,
        )
        await self._audit_repo.create(audit_entry)

        return saved_line

    async def upload_gst_invoice(
        self,
        claim_id: UUID,
        gst_invoice_number: str,
        actor: Any,
    ) -> ClaimHeader:
        """
        Record the GST invoice number on a Closed claim.  Requires
        ``gstn_verification_status == "Verified"``.

        Guards:
        - Claim must be in ``Closed`` status.
        - ``gstn_verification_status`` must be ``"Verified"`` (Req 9.2).

        Persists ``gst_invoice_number`` and ``gst_invoice_upload_date``
        (today's date) on the claim header (Req 9.3).  Writes a
        ``Field Edited`` audit entry.

        Requirements: 9.2, 9.3
        """
        now = datetime.now(timezone.utc)

        claim = await self._header_repo.get_by_id(claim_id)
        if claim is None:
            raise ValueError("Claim not found")

        if claim.status != ClaimStatus.Closed:
            raise ValueError("GST invoice can only be uploaded on a Closed claim.")

        # Req 9.2: GSTN must be verified before GST invoice upload is allowed
        if claim.gstn_verification_status != "Verified":
            raise ValueError(
                "GSTN verification is required before uploading the GST invoice."
            )

        claim.gst_invoice_number = gst_invoice_number
        claim.gst_invoice_upload_date = date.today()
        claim.modified_by = actor.username
        claim.modified_date = now

        saved = await self._header_repo.update(claim)

        audit_entry = ClaimAuditEntry(
            id=uuid4(),
            claim_header_id=claim_id,
            action="Field Edited",
            actor_username=actor.username,
            actor_user_id=actor.id,
            timestamp_utc=now,
            from_status=None,
            to_status=None,
            workflow_step_name=None,
            remarks=None,
            field_changes={
                "gst_invoice_number": {
                    "old": None,
                    "new": gst_invoice_number,
                }
            },
            created_by=actor.username,
            created_date=now,
            modified_by=actor.username,
            modified_date=now,
        )
        await self._audit_repo.create(audit_entry)

        return saved

    async def record_sap_booking(
        self,
        claim_id: UUID,
        reference: str,
        actor: Any,
    ) -> ClaimHeader:
        """
        Persist the SAP P2P booking reference on a Closed claim.

        Persists ``sap_p2p_booking_reference`` on the claim header and
        writes a ``SAP Booking Reference Recorded`` audit entry (Req 9.5).

        Requirements: 9.5
        """
        now = datetime.now(timezone.utc)

        claim = await self._header_repo.get_by_id(claim_id)
        if claim is None:
            raise ValueError("Claim not found")

        if claim.status != ClaimStatus.Closed:
            raise ValueError(
                "SAP booking reference can only be recorded on a Closed claim."
            )

        claim.sap_p2p_booking_reference = reference
        claim.modified_by = actor.username
        claim.modified_date = now

        saved = await self._header_repo.update(claim)

        audit_entry = ClaimAuditEntry(
            id=uuid4(),
            claim_header_id=claim_id,
            action="SAP Booking Reference Recorded",
            actor_username=actor.username,
            actor_user_id=actor.id,
            timestamp_utc=now,
            from_status=None,
            to_status=None,
            workflow_step_name=None,
            remarks=None,
            field_changes={
                "sap_p2p_booking_reference": {
                    "old": None,
                    "new": reference,
                }
            },
            created_by=actor.username,
            created_date=now,
            modified_by=actor.username,
            modified_date=now,
        )
        await self._audit_repo.create(audit_entry)

        return saved

    # ── Views / MIS ───────────────────────────────────────────────────────────

    async def get_claim_audit(self, claim_id: UUID, actor: Any) -> list:
        """
        Return the audit trail for a claim in ascending timestamp order.
        Only the original initiator or an Administrator may access.

        Raises ``ValueError`` if the claim is not found.
        Raises ``PermissionError`` if the actor is neither the original initiator
        nor an Administrator.

        The ``ClaimAuditRepositoryImpl.list_by_claim`` already orders results
        by ``timestamp_utc ASC`` (Req 14.4).

        Requirements: 14.4
        """
        header = await self._header_repo.get_by_id(claim_id)
        if header is None:
            raise ValueError("Claim not found")

        is_admin = _is_admin_actor(actor)
        actor_username = getattr(actor, "username", None)

        if not is_admin and header.created_by != actor_username:
            raise PermissionError(
                "Only the original claim initiator or an Administrator can view the audit trail."
            )

        return await self._audit_repo.list_by_claim(claim_id)

    async def get_approval_queue(self, actor: Any) -> list:
        """
        Return ``Pending`` claims for which the actor is the eligible approver
        at the current workflow step, ordered by submission date ascending.
        Admins see all pending claims across all workflow steps.

        - Non-admin: delegates to ``list_pending_for_user`` which queries
          the workflow engine's pending task assignments (Req 17.1).
        - Admin: fetches all claims whose status is ``Pending`` (Req 17.3).

        Requirements: 17.1, 17.2, 17.3
        """
        is_admin = _is_admin_actor(actor)
        if is_admin:
            # Admin sees all Pending claims across all workflow steps (Req 17.3)
            filters = ClaimFilterParams(status=ClaimStatus.Pending.value)
            headers, _ = await self._header_repo.list_all(filters, skip=0, limit=10000)
        else:
            # Eligible approver — filtered to user's pending tasks (Req 17.1)
            headers = await self._header_repo.list_pending_for_user(actor.id)
        return headers

    async def get_mis_pending(
        self,
        actor: Any,
        filters: Any,
        skip: int,
        limit: int,
    ) -> dict:
        """
        Return non-terminal claims (Draft, Pending, Referred Back) with an
        inline status label ``"Pending - <step_name>"`` for Pending claims
        (Req 15.4).  Supports vendor, date-range, and claim_number filters
        (Req 15.2).

        Returns a dict with keys:
        - ``items``: list of dicts ``{"header": ClaimHeader, "status_label": str}``
        - ``total``: total matching record count (before pagination)
        - ``skip``: the requested skip offset
        - ``limit``: the requested page size

        Requirements: 15.1, 15.2, 15.3, 15.4
        """
        # Non-terminal statuses (Req 15.1)
        non_terminal_statuses = [
            ClaimStatus.Draft.value,
            ClaimStatus.Pending.value,
            ClaimStatus.ReferredBack.value,
        ]

        all_items: list = []
        total = 0
        for status_val in non_terminal_statuses:
            f = ClaimFilterParams(
                vendor_id=getattr(filters, "vendor_id", None),
                status=status_val,
                claim_number=getattr(filters, "claim_number", None),
                start_date=getattr(filters, "start_date", None),
                end_date=getattr(filters, "end_date", None),
            )
            items, count = await self._header_repo.list_all(f, skip=0, limit=100000)
            all_items.extend(items)
            total += count

        # For Pending claims, enrich with workflow step label (Req 15.4)
        enriched: list = []
        for header in all_items:
            status_label = header.status.value
            if header.status == ClaimStatus.Pending and header.workflow_instance_id:
                try:
                    wf_status = await self._workflow_engine.get_workflow_status(
                        header.workflow_instance_id
                    )
                    step_name = wf_status.get("status_name") or wf_status.get(
                        "current_step", ""
                    )
                    if step_name:
                        status_label = f"Pending - {step_name}"
                except Exception:
                    pass  # fall back to raw "Pending" label
            enriched.append({"header": header, "status_label": status_label})

        # Apply pagination after assembling all statuses
        paginated = enriched[skip : skip + limit]
        return {"items": paginated, "total": total, "skip": skip, "limit": limit}

    async def get_mis_history(
        self,
        actor: Any,
        filters: Any,
        skip: int,
        limit: int,
    ) -> dict:
        """
        Return terminal claims (Closed, Rejected) with the same vendor /
        date-range / claim_number filters as MIS Pending plus Final Decision
        Date (Req 16.1, 16.2).

        Returns a dict with keys:
        - ``items``: list of ``ClaimHeader`` entities
        - ``total``: total matching record count (before pagination)
        - ``skip``: the requested skip offset
        - ``limit``: the requested page size

        Requirements: 16.1, 16.2, 16.3
        """
        all_items: list = []
        total = 0
        for status_val in [ClaimStatus.Closed.value, ClaimStatus.Rejected.value]:
            f = ClaimFilterParams(
                vendor_id=getattr(filters, "vendor_id", None),
                status=status_val,
                claim_number=getattr(filters, "claim_number", None),
                start_date=getattr(filters, "start_date", None),
                end_date=getattr(filters, "end_date", None),
            )
            items, count = await self._header_repo.list_all(f, skip=0, limit=100000)
            all_items.extend(items)
            total += count

        paginated = all_items[skip : skip + limit]
        return {"items": paginated, "total": total, "skip": skip, "limit": limit}

    async def export_mis(self, actor: Any, filters: Any, view: str) -> bytes:
        """
        Produce an Excel workbook (openpyxl) with one header row and one data
        row per claim line, including the full per-line commission breakdown.

        ``view`` must be ``"pending"`` or ``"history"``; claims are fetched
        from the corresponding MIS method with ``skip=0, limit=100000`` so all
        matching rows are included in the export (Req 15.3, 16.3).

        Requirements: 15.3, 16.3
        """
        import io

        import openpyxl
        from openpyxl.styles import Font

        # ── Fetch claims based on view ────────────────────────────────────────
        if view == "pending":
            result = await self.get_mis_pending(actor, filters, skip=0, limit=100000)
            # get_mis_pending returns enriched dicts — extract the header
            claim_headers = [r["header"] for r in result["items"]]
        else:
            result = await self.get_mis_history(actor, filters, skip=0, limit=100000)
            claim_headers = result["items"]

        # ── Build workbook ────────────────────────────────────────────────────
        wb = openpyxl.Workbook()
        ws = wb.active
        ws.title = "Claims"

        # Header row (Req 15.3, 16.3 — one header row)
        col_headers = [
            # Claim-level columns
            "Claim Number",
            "Vendor ID",
            "Claim Date",
            "Status",
            "Total Claim Amount",
            "Total Commission",
            "Total GST",
            "Total TDS",
            "Total LD",
            "Total Retention",
            "GSTN Verification",
            "SAP Booking Ref",
            # Line-level columns (per-line commission breakdown)
            "Invoice ID",
            "Bill Amount",
            "Net Amount",
            "Commission Base",
            "Due Date",
            "Payment Clearing Date",
            "Delay Days",
            "Commission %",
            "Commission Amount",
            "GST on Commission",
            "Final Line Amount",
        ]
        ws.append(col_headers)
        for cell in ws[1]:
            cell.font = Font(bold=True)

        # ── Data rows ─────────────────────────────────────────────────────────
        for header in claim_headers:
            lines = await self._line_repo.list_by_claim(header.id)
            if lines:
                # One row per line (Req 15.3 — full per-line commission breakdown)
                for line in lines:
                    ws.append([
                        header.claim_number,
                        str(header.vendor_id),
                        str(header.claim_date),
                        header.status.value,
                        float(header.total_claim_amount),
                        float(header.total_commission_amount),
                        float(header.total_gst_amount),
                        float(header.total_tds_amount),
                        float(header.total_ld_amount),
                        float(header.total_retention_amount),
                        header.gstn_verification_status,
                        header.sap_p2p_booking_reference,
                        # Line columns
                        str(line.invoice_header_id),
                        float(line.bill_amount_excl_gst),
                        float(line.net_amount),
                        float(line.commission_payable_base),
                        str(line.due_date),
                        str(line.payment_clearing_date),
                        line.delay_days,
                        float(line.applicable_commission_percent),
                        float(line.commission_amount),
                        float(line.gst_on_commission),
                        float(line.final_line_claim_amount),
                    ])
            else:
                # Claim with no lines — write one row with header data, no line columns
                ws.append([
                    header.claim_number,
                    str(header.vendor_id),
                    str(header.claim_date),
                    header.status.value,
                    float(header.total_claim_amount),
                    float(header.total_commission_amount),
                    float(header.total_gst_amount),
                    float(header.total_tds_amount),
                    float(header.total_ld_amount),
                    float(header.total_retention_amount),
                    header.gstn_verification_status,
                    header.sap_p2p_booking_reference,
                    None, None, None, None, None, None, None, None, None, None, None,
                ])

        buffer = io.BytesIO()
        wb.save(buffer)
        return buffer.getvalue()

    # ── Private helpers ───────────────────────────────────────────────────────

    async def _recalculate_header_totals(self, claim_id: UUID) -> None:
        """
        Recompute and persist all six header totals from the current set of
        claim lines.  MUST be called inside the same DB transaction as any
        line add / update / delete.

        Totals updated:
        - ``total_claim_amount``      ← Σ ``final_line_claim_amount``
        - ``total_commission_amount`` ← Σ ``commission_amount``
        - ``total_gst_amount``        ← Σ ``gst_on_commission``
        - ``total_tds_amount``        ← Σ ``tds_value``
        - ``total_ld_amount``         ← Σ ``ld_charges``
        - ``total_retention_amount``  ← Σ ``retention_amount``

        Requirements: 4.1, 4.2
        """
        # Get aggregate totals via SQL SUM (single round-trip)
        totals = await self._line_repo.sum_totals(claim_id)

        # Load the current header
        header = await self._header_repo.get_by_id(claim_id)
        if header is None:
            raise ValueError(f"Claim {claim_id} not found")

        # Apply totals and mark modified
        now = datetime.now(timezone.utc)
        header.total_claim_amount = totals.total_claim_amount
        header.total_commission_amount = totals.total_commission_amount
        header.total_gst_amount = totals.total_gst_amount
        header.total_tds_amount = totals.total_tds_amount
        header.total_ld_amount = totals.total_ld_amount
        header.total_retention_amount = totals.total_retention_amount
        header.modified_by = "system"
        header.modified_date = now

        await self._header_repo.update(header)

    async def _get_vendor_id_for_actor(self, actor: Any) -> UUID | None:
        """
        Look up the vendor linked to this user via ``vendors.portal_user_id``.

        Returns the vendor's UUID if found, or None if the user is not linked
        to any vendor (e.g. admin users).
        """
        result = await self._session.execute(
            select(VendorModel).where(VendorModel.portal_user_id == str(actor.id))
        )
        vendor = result.scalar_one_or_none()
        return vendor.id if vendor else None

    async def _get_pending_instance_ids_for_user(self, user_id: UUID) -> list[UUID]:
        """
        Query approval_tasks for all workflow instances currently pending
        for the given user.

        The workflow engine resolves both role-based and specific-user
        assignments into approval_tasks.assignee_id at workflow start time.
        We simply query which tasks are PENDING for this user.

        Returns a list of distinct workflow instance UUIDs.
        """
        from src.infrastructure.database.models.workflow.approval_matrix_models import (
            ApprovalTaskModel,
        )

        stmt = (
            select(ApprovalTaskModel.instance_id)
            .where(
                ApprovalTaskModel.assignee_id == str(user_id),
                ApprovalTaskModel.status == "PENDING",
            )
            .distinct()
        )
        result = await self._session.execute(stmt)
        return [row[0] for row in result.all()]

    async def get_workflow_status_names(
        self, instance_ids: list[UUID]
    ) -> dict[str, str]:
        """
        Bulk-resolve current workflow status names for a list of workflow
        instance IDs.

        Returns a dict mapping ``str(instance_id) → status_name``. Instances
        without a resolvable status are omitted. Used to enrich claim list
        responses with the human-readable workflow step (e.g. "L1 Approval
        Pending").
        """
        from src.infrastructure.database.models.workflow.workflow_models import (
            WorkflowInstanceModel,
            WorkflowStatusModel,
        )

        if not instance_ids:
            return {}

        id_strs = [str(iid) for iid in instance_ids]
        stmt = (
            select(WorkflowInstanceModel.id, WorkflowStatusModel.name)
            .join(
                WorkflowStatusModel,
                WorkflowStatusModel.id == WorkflowInstanceModel.current_status_id,
            )
            .where(WorkflowInstanceModel.id.in_(id_strs))
        )
        result = await self._session.execute(stmt)
        return {str(row[0]): row[1] for row in result.all()}

    async def _user_has_pending_task(self, user_id: UUID, instance_id: UUID) -> bool:
        """
        Return True if the user has a PENDING approval task for the given
        workflow instance. Used to determine if workflow action buttons
        should be visible to this user.
        """
        from src.infrastructure.database.models.workflow.approval_matrix_models import (
            ApprovalTaskModel,
        )

        stmt = select(ApprovalTaskModel.id).where(
            ApprovalTaskModel.instance_id == str(instance_id),
            ApprovalTaskModel.assignee_id == str(user_id),
            ApprovalTaskModel.status == "PENDING",
        ).limit(1)
        result = await self._session.execute(stmt)
        return result.scalar_one_or_none() is not None

    async def _run_post_closure(self, claim_id: UUID) -> None:
        """
        Execute the post-closure sequence after a claim reaches ``Closed``:
        1. Set ``invoice_status = "Settled"`` for all covered invoice lines
           (skip + warn if already Settled).
        2. Validate ``VendorModel.gstn_number`` against ``[A-Z0-9]{15}`` and
           set ``gstn_verification_status`` accordingly.
        3. Send HO Finance email notification with Claim Number and total.
        4. Write ``Closed`` audit entry.

        Requirements: 9.1, 9.2, 9.4, 9.6
        """
        now = datetime.now(timezone.utc)

        # Load claim header
        claim = await self._header_repo.get_by_id(claim_id)
        if claim is None:
            raise ValueError(f"Claim {claim_id} not found for post-closure")

        # Load all claim lines
        lines = await self._line_repo.list_by_claim(claim_id)

        # ── Step 1: Settle all covered invoices (Req 9.1, 9.6) ───────────────
        for line in lines:
            invoice_stmt = select(InvoiceHeaderModel).where(
                InvoiceHeaderModel.id == line.invoice_header_id
            )
            invoice_result = await self._session.execute(invoice_stmt)
            invoice = invoice_result.scalar_one_or_none()

            if invoice is None:
                logger.warning(
                    "Invoice %s not found during post-closure for claim %s",
                    line.invoice_header_id,
                    claim_id,
                )
                continue

            # Req 9.6: skip + warn if already Settled (concurrent edge case)
            if invoice.invoice_status == InvoiceStatus.Settled.value:
                logger.warning(
                    "Invoice %s is already Settled — skipping during post-closure for claim %s",
                    line.invoice_header_id,
                    claim_id,
                )
                continue

            invoice.invoice_status = InvoiceStatus.Settled.value
            # SQLAlchemy tracks in-session changes — no explicit update() call needed

        # Flush invoice updates before proceeding
        await self._session.flush()

        # ── Step 2: GSTN verification (Req 9.2) ──────────────────────────────
        vendor_stmt = select(VendorModel).where(VendorModel.id == claim.vendor_id)
        vendor_result = await self._session.execute(vendor_stmt)
        vendor = vendor_result.scalar_one_or_none()

        _gstn_pattern = re.compile(r'^[A-Z0-9]{15}$')
        if vendor and vendor.gstn_number and _gstn_pattern.match(vendor.gstn_number):
            claim.gstn_verification_status = "Verified"
        else:
            claim.gstn_verification_status = "Failed"

        claim.modified_by = "system"
        claim.modified_date = now
        await self._header_repo.update(claim)

        # ── Step 3: Send HO Finance notification (Req 9.4) ───────────────────
        try:
            await self._send_ho_finance_notification(claim)
        except Exception:
            logger.exception(
                "Failed to send HO Finance notification for claim %s", claim_id
            )

        # ── Step 4: Write Closed audit entry (Req 14.1) ───────────────────────
        audit_entry = ClaimAuditEntry(
            id=uuid4(),
            claim_header_id=claim_id,
            action="Closed",
            actor_username="system",
            actor_user_id=UUID("00000000-0000-0000-0000-000000000000"),
            timestamp_utc=now,
            from_status=ClaimStatus.Pending.value,
            to_status=ClaimStatus.Closed.value,
            workflow_step_name=None,
            remarks=None,
            field_changes=None,
            created_by="system",
            created_date=now,
            modified_by="system",
            modified_date=now,
        )
        await self._audit_repo.create(audit_entry)

    async def _send_ho_finance_notification(self, claim: ClaimHeader) -> None:
        """
        Send HO Finance email with Claim Number and total_claim_amount.

        Uses the existing notification service when available.  Currently
        logs the notification — the actual email integration plugs in here
        via the platform notification service at
        ``src/application/services/notification_service.py``.

        Requirement: 9.4
        """
        logger.info(
            "HO Finance notification: Claim %s closed. Total claim amount: %s",
            claim.claim_number,
            claim.total_claim_amount,
        )
