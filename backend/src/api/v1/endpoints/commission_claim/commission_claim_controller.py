"""
Commission Claim API — Thin FastAPI controller.

Implements all claim lifecycle, line management, workflow action,
post-closure, approval queue, and MIS endpoints.
Delegates all business logic to CommissionClaimService.

Endpoints (task 8.2 — claim lifecycle and line management):
    POST   /claims                              → create_claim
    GET    /claims                              → list_claims
    GET    /claims/{claim_id}                   → get_claim_detail
    GET    /claims/{claim_id}/audit             → get_claim_audit
    POST   /claims/{claim_id}/lines             → add_invoice_line
    PATCH  /claims/{claim_id}/lines/{line_id}   → update_line
    DELETE /claims/{claim_id}/lines/{line_id}   → remove_line
    POST   /claims/{claim_id}/lines/{line_id}/pod → upload_pod

Endpoints (task 8.3 — workflow actions, post-closure, approval queue, MIS):
    GET    /claims/approval-queue                              → get_approval_queue
    GET    /claims/mis/pending                                 → get_mis_pending
    GET    /claims/mis/history                                 → get_mis_history
    GET    /claims/mis/pending/export                          → export_mis_pending
    GET    /claims/mis/history/export                          → export_mis_history
    POST   /claims/{claim_id}/submit                           → submit_claim
    POST   /claims/{claim_id}/approve                          → approve_claim
    POST   /claims/{claim_id}/refer-back                       → refer_back_claim
    POST   /claims/{claim_id}/reject                           → reject_claim
    PATCH  /claims/{claim_id}/lines/{line_id}/payment-clearing-date → update_payment_clearing_date
    PATCH  /claims/{claim_id}/sap-booking                      → record_sap_booking
    POST   /claims/{claim_id}/gst-invoice                      → upload_gst_invoice

IMPORTANT — route ordering:
    Static-path GET routes (/approval-queue, /mis/*) are declared BEFORE the
    parameterised /{claim_id} route so FastAPI does not interpret the literal
    path segments as UUID claim ids.

Requirements: 1.1, 1.4, 2.1–2.5, 3.11, 4.1, 5.1–5.3, 6.4, 7.1–7.7,
              8.1–8.5, 9.3, 9.5, 12.3, 12.4, 12.5, 15.1–15.4, 16.1–16.3,
              17.1–17.3
"""

from __future__ import annotations

from datetime import date
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.responses import Response
from sqlalchemy.ext.asyncio import AsyncSession

from src.api.v1.dependencies import get_current_active_user
from src.api.v1.schemas.commission_claim.commission_claim_request import (
    AddInvoiceLineRequest,
    ClaimCreateRequest,
    ClaimEntityUpdateRequest,
    GSTInvoiceRequest,
    LineUpdateRequest,
    MISFilterParams,
    PaymentClearingDateRequest,
    PODUploadRequest,
    SAPBookingRequest,
    WorkflowActionRequest,
)
from src.api.v1.schemas.commission_claim.commission_claim_response import (
    ApprovalQueueItemResponse,
    ClaimAuditEntryResponse,
    ClaimDetailResponse,
    ClaimHeaderResponse,
    ClaimLineResponse,
    ClaimListResponse,
)
from src.application.services.commission_claim_service import (
    CommissionClaimService,
    LineOverrides,
    LineUpdateRequest as SvcLineUpdateRequest,
)
from src.domain.entities.user import User
from src.infrastructure.database.session import get_db_session
from src.infrastructure.security.permission_manager import require_permission
from src.application.services.workflow.workflow_engine import WorkflowEngine
from src.infrastructure.security.audit_service import AuditService

router = APIRouter(prefix="/claims", tags=["Commission Claims"])


# ── Service factory ────────────────────────────────────────────────────────────


async def _get_claim_service(
    session: AsyncSession = Depends(get_db_session),
) -> CommissionClaimService:
    """FastAPI dependency — builds CommissionClaimService with all collaborators."""
    workflow_engine = WorkflowEngine(session)
    audit_service = AuditService(session)
    return CommissionClaimService(
        session=session,
        audit_service=audit_service,
        workflow_engine=workflow_engine,
    )


async def _enrich_with_workflow_status(
    headers: list,
    service: CommissionClaimService,
) -> list[dict]:
    """
    Enrich claim header objects with ``workflow_status_name``.

    Delegates the workflow status name resolution to the service layer
    (no direct DB access in the controller). Returns a list of dicts
    (``vars(header)`` + ``workflow_status_name``) ready for response mapping.
    """
    instance_ids = [h.workflow_instance_id for h in headers if h.workflow_instance_id]
    status_name_map = await service.get_workflow_status_names(instance_ids)

    enriched: list[dict] = []
    for h in headers:
        data = vars(h)
        key = str(h.workflow_instance_id) if h.workflow_instance_id else None
        data["workflow_status_name"] = status_name_map.get(key) if key else None
        enriched.append(data)
    return enriched


# ── Static-path view / MIS endpoints  (MUST come before /{claim_id} routes) ──
#
# FastAPI evaluates routes in declaration order.  Placing these static GET
# routes before the parameterised /{claim_id} routes prevents FastAPI from
# treating "approval-queue" or "mis" as a UUID claim-id.

@router.get(
    "/approval-queue",
    response_model=list[ApprovalQueueItemResponse],
    summary="Get pending claims awaiting the current user's approval",
    dependencies=[Depends(require_permission("claims.approve"))],
)
async def get_approval_queue(
    current_user: User = Depends(get_current_active_user),
    service: CommissionClaimService = Depends(_get_claim_service),
) -> list[ApprovalQueueItemResponse]:
    """GET /claims/approval-queue — returns claims pending the actor's action."""
    items = await service.get_approval_queue(actor=current_user)
    return [ApprovalQueueItemResponse.model_validate(vars(h)) for h in items]


@router.get(
    "/tab/draft",
    response_model=ClaimListResponse,
    summary="List claims in Draft tab — user's own drafts",
    dependencies=[Depends(require_permission("claims.list"))],
)
async def list_claims_draft(
    skip: int = Query(default=0, ge=0),
    limit: int = Query(default=50, ge=1, le=200),
    current_user: User = Depends(get_current_active_user),
    service: CommissionClaimService = Depends(_get_claim_service),
) -> ClaimListResponse:
    """GET /claims/tab/draft — drafts created by the current user."""
    result = await service.list_claims_draft(
        actor=current_user, skip=skip, limit=limit,
    )
    enriched = await _enrich_with_workflow_status(result["items"], service)
    return ClaimListResponse(
        items=[ClaimHeaderResponse.model_validate(d) for d in enriched],
        total=result["total"],
        skip=result["skip"],
        limit=result["limit"],
    )


@router.get(
    "/tab/pending",
    response_model=ClaimListResponse,
    summary="List claims in Pending tab — role-based view",
    dependencies=[Depends(require_permission("claims.list"))],
)
async def list_claims_pending(
    skip: int = Query(default=0, ge=0),
    limit: int = Query(default=50, ge=1, le=200),
    current_user: User = Depends(get_current_active_user),
    service: CommissionClaimService = Depends(_get_claim_service),
) -> ClaimListResponse:
    """GET /claims/tab/pending — pending claims based on user role."""
    result = await service.list_claims_pending(
        actor=current_user, skip=skip, limit=limit,
    )
    enriched = await _enrich_with_workflow_status(result["items"], service)
    return ClaimListResponse(
        items=[ClaimHeaderResponse.model_validate(d) for d in enriched],
        total=result["total"],
        skip=result["skip"],
        limit=result["limit"],
    )


@router.get(
    "/tab/closed",
    response_model=ClaimListResponse,
    summary="List claims in Closed tab — terminal workflow states",
    dependencies=[Depends(require_permission("claims.list"))],
)
async def list_claims_closed(
    skip: int = Query(default=0, ge=0),
    limit: int = Query(default=50, ge=1, le=200),
    current_user: User = Depends(get_current_active_user),
    service: CommissionClaimService = Depends(_get_claim_service),
) -> ClaimListResponse:
    """GET /claims/tab/closed — closed/rejected/cancelled claims."""
    result = await service.list_claims_closed(
        actor=current_user, skip=skip, limit=limit,
    )
    enriched = await _enrich_with_workflow_status(result["items"], service)
    return ClaimListResponse(
        items=[ClaimHeaderResponse.model_validate(d) for d in enriched],
        total=result["total"],
        skip=result["skip"],
        limit=result["limit"],
    )


@router.get(
    "/mis/pending",
    response_model=ClaimListResponse,
    summary="MIS view — non-terminal (pending) claims with optional filters",
    dependencies=[Depends(require_permission("menu.claims_mis"))],
)
async def get_mis_pending(
    skip: int = Query(default=0, ge=0),
    limit: int = Query(default=50, ge=1, le=500),
    vendor_id: UUID | None = Query(default=None),
    claim_number: str | None = Query(default=None),
    start_date: date | None = Query(default=None),
    end_date: date | None = Query(default=None),
    current_user: User = Depends(get_current_active_user),
    service: CommissionClaimService = Depends(_get_claim_service),
) -> ClaimListResponse:
    """GET /claims/mis/pending — paginated non-terminal claims."""
    filters = MISFilterParams(
        vendor_id=vendor_id,
        claim_number=claim_number,
        start_date=start_date,
        end_date=end_date,
    )
    result = await service.get_mis_pending(
        actor=current_user, filters=filters, skip=skip, limit=limit
    )
    # get_mis_pending returns enriched dicts — each item is {"header": ClaimHeader, "status_label": str}
    return ClaimListResponse(
        items=[ClaimHeaderResponse.model_validate(vars(row["header"])) for row in result["items"]],
        total=result["total"],
        skip=result["skip"],
        limit=result["limit"],
    )


@router.get(
    "/mis/history",
    response_model=ClaimListResponse,
    summary="MIS view — terminal (closed/rejected) claims with optional filters",
    dependencies=[Depends(require_permission("menu.claims_mis"))],
)
async def get_mis_history(
    skip: int = Query(default=0, ge=0),
    limit: int = Query(default=50, ge=1, le=500),
    vendor_id: UUID | None = Query(default=None),
    claim_number: str | None = Query(default=None),
    start_date: date | None = Query(default=None),
    end_date: date | None = Query(default=None),
    current_user: User = Depends(get_current_active_user),
    service: CommissionClaimService = Depends(_get_claim_service),
) -> ClaimListResponse:
    """GET /claims/mis/history — paginated terminal claims."""
    filters = MISFilterParams(
        vendor_id=vendor_id,
        claim_number=claim_number,
        start_date=start_date,
        end_date=end_date,
    )
    result = await service.get_mis_history(
        actor=current_user, filters=filters, skip=skip, limit=limit
    )
    return ClaimListResponse(
        items=[ClaimHeaderResponse.model_validate(vars(h)) for h in result["items"]],
        total=result["total"],
        skip=result["skip"],
        limit=result["limit"],
    )


@router.get(
    "/mis/pending/export",
    response_class=Response,
    summary="Export non-terminal MIS claims to Excel",
    dependencies=[Depends(require_permission("claims.export"))],
)
async def export_mis_pending(
    vendor_id: UUID | None = Query(default=None),
    claim_number: str | None = Query(default=None),
    start_date: date | None = Query(default=None),
    end_date: date | None = Query(default=None),
    current_user: User = Depends(get_current_active_user),
    service: CommissionClaimService = Depends(_get_claim_service),
) -> Response:
    """GET /claims/mis/pending/export — download XLSX for non-terminal claims."""
    filters = MISFilterParams(
        vendor_id=vendor_id,
        claim_number=claim_number,
        start_date=start_date,
        end_date=end_date,
    )
    excel_bytes = await service.export_mis(actor=current_user, filters=filters, view="pending")
    return Response(
        content=excel_bytes,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": "attachment; filename=mis_pending.xlsx"},
    )


@router.get(
    "/mis/history/export",
    response_class=Response,
    summary="Export terminal MIS claims to Excel",
    dependencies=[Depends(require_permission("claims.export"))],
)
async def export_mis_history(
    vendor_id: UUID | None = Query(default=None),
    claim_number: str | None = Query(default=None),
    start_date: date | None = Query(default=None),
    end_date: date | None = Query(default=None),
    current_user: User = Depends(get_current_active_user),
    service: CommissionClaimService = Depends(_get_claim_service),
) -> Response:
    """GET /claims/mis/history/export — download XLSX for terminal claims."""
    filters = MISFilterParams(
        vendor_id=vendor_id,
        claim_number=claim_number,
        start_date=start_date,
        end_date=end_date,
    )
    excel_bytes = await service.export_mis(actor=current_user, filters=filters, view="history")
    return Response(
        content=excel_bytes,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": "attachment; filename=mis_history.xlsx"},
    )


# ── Claim lifecycle ────────────────────────────────────────────────────────────


@router.post(
    "",
    response_model=ClaimHeaderResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create a new commission claim (Draft)",
    dependencies=[Depends(require_permission("claims.create"))],
)
async def create_claim(
    request: ClaimCreateRequest,
    current_user: User = Depends(get_current_active_user),
    service: CommissionClaimService = Depends(_get_claim_service),
) -> ClaimHeaderResponse:
    """POST /claims — create a new draft claim for the given vendor."""
    try:
        result = await service.create_claim(
            vendor_id=request.vendor_id,
            entity_id=request.entity_id,
            actor=current_user,
        )
        return ClaimHeaderResponse.model_validate(vars(result))
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))


@router.get(
    "",
    response_model=ClaimListResponse,
    summary="List commission claims (paginated)",
    dependencies=[Depends(require_permission("claims.list"))],
)
async def list_claims(
    skip: int = Query(default=0, ge=0),
    limit: int = Query(default=50, ge=1, le=200),
    vendor_id: UUID | None = Query(default=None),
    claim_number: str | None = Query(default=None),
    start_date: date | None = Query(default=None),
    end_date: date | None = Query(default=None),
    current_user: User = Depends(get_current_active_user),
    service: CommissionClaimService = Depends(_get_claim_service),
) -> ClaimListResponse:
    """GET /claims — returns paginated list scoped to the actor's role."""
    filters = MISFilterParams(
        vendor_id=vendor_id,
        claim_number=claim_number,
        start_date=start_date,
        end_date=end_date,
    )
    result = await service.list_claims(
        actor=current_user,
        filters=filters,
        skip=skip,
        limit=limit,
    )
    return ClaimListResponse(
        items=[ClaimHeaderResponse.model_validate(vars(h)) for h in result["items"]],
        total=result["total"],
        skip=result["skip"],
        limit=result["limit"],
    )


@router.get(
    "/{claim_id}",
    response_model=ClaimDetailResponse,
    summary="Get full claim detail (header + lines + workflow status)",
    dependencies=[Depends(require_permission("claims.view"))],
)
async def get_claim_detail(
    claim_id: UUID,
    current_user: User = Depends(get_current_active_user),
    service: CommissionClaimService = Depends(_get_claim_service),
) -> ClaimDetailResponse:
    """GET /claims/{claim_id}"""
    try:
        result = await service.get_claim_detail(claim_id=claim_id, actor=current_user)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc))

    header = ClaimHeaderResponse.model_validate(vars(result["header"]))
    invoice_numbers = result.get("invoice_numbers", {})
    lines = []
    for ln in result["lines"]:
        line_data = vars(ln)
        line_data["invoice_number"] = invoice_numbers.get(str(ln.invoice_header_id))
        lines.append(ClaimLineResponse.model_validate(line_data))

    return ClaimDetailResponse(
        header=header,
        lines=lines,
        workflow_status=result.get("workflow_status"),
        available_actions=result.get("available_actions", []),
    )


@router.get(
    "/{claim_id}/audit",
    response_model=list[ClaimAuditEntryResponse],
    summary="Get audit trail for a claim",
    dependencies=[Depends(require_permission("claims.view"))],
)
async def get_claim_audit(
    claim_id: UUID,
    current_user: User = Depends(get_current_active_user),
    service: CommissionClaimService = Depends(_get_claim_service),
) -> list[ClaimAuditEntryResponse]:
    """GET /claims/{claim_id}/audit — returns audit entries ascending by timestamp."""
    try:
        entries = await service.get_claim_audit(claim_id=claim_id, actor=current_user)
    except PermissionError as exc:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(exc))
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc))

    return [ClaimAuditEntryResponse.model_validate(vars(e)) for e in entries]


# ── Claim entity update ────────────────────────────────────────────────────────


@router.patch(
    "/{claim_id}/entity",
    response_model=ClaimHeaderResponse,
    summary="Update the entity (company) assigned to a draft claim",
    dependencies=[Depends(require_permission("claims.create"))],
)
async def update_claim_entity(
    claim_id: UUID,
    request: ClaimEntityUpdateRequest,
    current_user: User = Depends(get_current_active_user),
    service: CommissionClaimService = Depends(_get_claim_service),
) -> ClaimHeaderResponse:
    """PATCH /claims/{claim_id}/entity — sets entity_id on a draft claim."""
    try:
        result = await service.update_claim_entity(
            claim_id=claim_id,
            entity_id=request.entity_id,
            actor=current_user,
        )
        return ClaimHeaderResponse.model_validate(vars(result))
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))


# ── Line management ────────────────────────────────────────────────────────────


@router.post(
    "/{claim_id}/lines",
    response_model=ClaimLineResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Add an invoice line to a claim",
    dependencies=[Depends(require_permission("claims.create"))],
)
async def add_invoice_line(
    claim_id: UUID,
    request: AddInvoiceLineRequest,
    current_user: User = Depends(get_current_active_user),
    service: CommissionClaimService = Depends(_get_claim_service),
) -> ClaimLineResponse:
    """POST /claims/{claim_id}/lines — validate pre-conditions and compute commission."""
    overrides = LineOverrides(
        due_date_override=request.due_date_override,
        ld_charges=request.ld_charges,
        retention_amount=request.retention_amount,
        remarks=request.remarks,
    )
    try:
        result = await service.add_invoice_line(
            claim_id=claim_id,
            invoice_id=request.invoice_id,
            overrides=overrides,
            actor=current_user,
        )
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))

    return ClaimLineResponse.model_validate(vars(result))


@router.patch(
    "/{claim_id}/lines/{line_id}",
    response_model=ClaimLineResponse,
    summary="Partially update a claim line",
    dependencies=[Depends(require_permission("claims.create"))],
)
async def update_line(
    claim_id: UUID,
    line_id: UUID,
    request: LineUpdateRequest,
    current_user: User = Depends(get_current_active_user),
    service: CommissionClaimService = Depends(_get_claim_service),
) -> ClaimLineResponse:
    """PATCH /claims/{claim_id}/lines/{line_id} — only supplied fields are applied."""
    svc_request = SvcLineUpdateRequest(
        amount_deducted=request.amount_deducted,
        tds_value=request.tds_value,
        payment_clearing_date=request.payment_clearing_date,
        ld_charges=request.ld_charges,
        retention_amount=request.retention_amount,
        due_date=request.due_date,
        remarks=request.remarks,
    )
    try:
        result = await service.update_line_fields(
            claim_id=claim_id,
            line_id=line_id,
            fields=svc_request,
            actor=current_user,
        )
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))

    return ClaimLineResponse.model_validate(vars(result))


@router.delete(
    "/{claim_id}/lines/{line_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    response_model=None,
    summary="Remove a line from a claim",
    dependencies=[Depends(require_permission("claims.create"))],
)
async def remove_line(
    claim_id: UUID,
    line_id: UUID,
    current_user: User = Depends(get_current_active_user),
    service: CommissionClaimService = Depends(_get_claim_service),
):
    """DELETE /claims/{claim_id}/lines/{line_id} — deletes line and recalculates totals."""
    try:
        await service.remove_line(
            claim_id=claim_id,
            line_id=line_id,
            actor=current_user,
        )
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))


@router.post(
    "/{claim_id}/lines/{line_id}/pod",
    response_model=ClaimLineResponse,
    summary="Upload / attach a POD document to a claim line",
    dependencies=[Depends(require_permission("claims.submit"))],
)
async def upload_pod(
    claim_id: UUID,
    line_id: UUID,
    request: PODUploadRequest,
    current_user: User = Depends(get_current_active_user),
    service: CommissionClaimService = Depends(_get_claim_service),
) -> ClaimLineResponse:
    """POST /claims/{claim_id}/lines/{line_id}/pod — only allowed on Draft or Referred Back claims."""
    try:
        result = await service.upload_pod(
            claim_id=claim_id,
            line_id=line_id,
            document_id=request.document_id,
            actor=current_user,
        )
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))

    return ClaimLineResponse.model_validate(vars(result))


# ── Workflow actions ───────────────────────────────────────────────────────────


@router.post(
    "/{claim_id}/submit",
    response_model=ClaimHeaderResponse,
    summary="Submit a Draft or Referred-Back claim for approval",
    dependencies=[Depends(require_permission("claims.submit"))],
)
async def submit_claim(
    claim_id: UUID,
    current_user: User = Depends(get_current_active_user),
    service: CommissionClaimService = Depends(_get_claim_service),
) -> ClaimHeaderResponse:
    """POST /claims/{claim_id}/submit — starts the claim_approval workflow."""
    try:
        result = await service.submit_claim(claim_id=claim_id, actor=current_user)
        return ClaimHeaderResponse.model_validate(vars(result))
    except PermissionError as exc:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(exc))
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))


@router.post(
    "/{claim_id}/approve",
    response_model=ClaimHeaderResponse,
    summary="Approve the claim at the current workflow step",
    dependencies=[Depends(require_permission("claims.approve"))],
)
async def approve_claim(
    claim_id: UUID,
    request: WorkflowActionRequest,
    current_user: User = Depends(get_current_active_user),
    service: CommissionClaimService = Depends(_get_claim_service),
) -> ClaimHeaderResponse:
    """POST /claims/{claim_id}/approve — intermediate or final approval."""
    try:
        result = await service.execute_workflow_action(
            claim_id=claim_id,
            action_code="approve",
            remarks=request.remarks,
            actor=current_user,
        )
        return ClaimHeaderResponse.model_validate(vars(result))
    except PermissionError as exc:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(exc))
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))


@router.post(
    "/{claim_id}/refer-back",
    response_model=ClaimHeaderResponse,
    summary="Refer the claim back to the original initiator for correction",
    dependencies=[Depends(require_permission("claims.refer_back"))],
)
async def refer_back_claim(
    claim_id: UUID,
    request: WorkflowActionRequest,
    current_user: User = Depends(get_current_active_user),
    service: CommissionClaimService = Depends(_get_claim_service),
) -> ClaimHeaderResponse:
    """POST /claims/{claim_id}/refer-back — sends claim back with remarks."""
    try:
        result = await service.execute_workflow_action(
            claim_id=claim_id,
            action_code="refer_back",
            remarks=request.remarks,
            actor=current_user,
        )
        return ClaimHeaderResponse.model_validate(vars(result))
    except PermissionError as exc:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(exc))
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))


@router.post(
    "/{claim_id}/reject",
    response_model=ClaimHeaderResponse,
    summary="Reject the claim permanently",
    dependencies=[Depends(require_permission("claims.reject"))],
)
async def reject_claim(
    claim_id: UUID,
    request: WorkflowActionRequest,
    current_user: User = Depends(get_current_active_user),
    service: CommissionClaimService = Depends(_get_claim_service),
) -> ClaimHeaderResponse:
    """POST /claims/{claim_id}/reject — moves claim to terminal Rejected status."""
    try:
        result = await service.execute_workflow_action(
            claim_id=claim_id,
            action_code="reject",
            remarks=request.remarks,
            actor=current_user,
        )
        return ClaimHeaderResponse.model_validate(vars(result))
    except PermissionError as exc:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(exc))
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))


# ── Post-closure endpoints ─────────────────────────────────────────────────────


@router.patch(
    "/{claim_id}/lines/{line_id}/payment-clearing-date",
    response_model=ClaimLineResponse,
    summary="Update payment clearing date on a claim line (Finance step only)",
    dependencies=[Depends(require_permission("claims.approve"))],
)
async def update_payment_clearing_date(
    claim_id: UUID,
    line_id: UUID,
    request: PaymentClearingDateRequest,
    current_user: User = Depends(get_current_active_user),
    service: CommissionClaimService = Depends(_get_claim_service),
) -> ClaimLineResponse:
    """PATCH /claims/{claim_id}/lines/{line_id}/payment-clearing-date — recalculates commission."""
    try:
        result = await service.update_payment_clearing_date(
            claim_id=claim_id,
            line_id=line_id,
            new_date=request.payment_clearing_date,
            actor=current_user,
        )
        return ClaimLineResponse.model_validate(vars(result))
    except PermissionError as exc:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(exc))
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))


@router.patch(
    "/{claim_id}/sap-booking",
    response_model=ClaimHeaderResponse,
    summary="Record SAP P2P booking reference on a closed claim",
    dependencies=[Depends(require_permission("claims.approve"))],
)
async def record_sap_booking(
    claim_id: UUID,
    request: SAPBookingRequest,
    current_user: User = Depends(get_current_active_user),
    service: CommissionClaimService = Depends(_get_claim_service),
) -> ClaimHeaderResponse:
    """PATCH /claims/{claim_id}/sap-booking — persists SAP P2P booking reference."""
    try:
        result = await service.record_sap_booking(
            claim_id=claim_id,
            reference=request.sap_p2p_booking_reference,
            actor=current_user,
        )
        return ClaimHeaderResponse.model_validate(vars(result))
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))


@router.post(
    "/{claim_id}/gst-invoice",
    response_model=ClaimHeaderResponse,
    summary="Upload GST invoice number after GSTN verification",
    dependencies=[Depends(require_permission("claims.submit"))],
)
async def upload_gst_invoice(
    claim_id: UUID,
    request: GSTInvoiceRequest,
    current_user: User = Depends(get_current_active_user),
    service: CommissionClaimService = Depends(_get_claim_service),
) -> ClaimHeaderResponse:
    """POST /claims/{claim_id}/gst-invoice — only allowed when GSTN is Verified."""
    try:
        result = await service.upload_gst_invoice(
            claim_id=claim_id,
            gst_invoice_number=request.gst_invoice_number,
            actor=current_user,
        )
        return ClaimHeaderResponse.model_validate(vars(result))
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))
