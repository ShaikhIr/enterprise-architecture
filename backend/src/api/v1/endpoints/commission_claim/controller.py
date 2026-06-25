"""
Commission Claim API — Example module using the Workflow Engine.

Demonstrates how a business module integrates with the reusable workflow framework:
1. Create a claim (business logic)
2. Submit → starts workflow
3. View status, available actions
4. Execute actions (approve/reject) → delegates to workflow engine
"""

import random
import string
from uuid import UUID, uuid4

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.api.v1.dependencies import get_current_active_user
from src.domain.entities.user import User
from src.infrastructure.database.session import get_db_session
from src.infrastructure.database.models.commission_claim.commission_claim_model import CommissionClaimModel
from src.api.v1.endpoints.commission_claim.schemas import ClaimCreate, ClaimListResponse, ClaimResponse
from src.application.services.workflow.workflow_engine import WorkflowEngine

router = APIRouter(prefix="/claims", tags=["Commission Claims (Example)"])


def _generate_claim_number() -> str:
    """Generate a unique claim number like CLM-2026-ABCD."""
    suffix = ''.join(random.choices(string.ascii_uppercase + string.digits, k=5))
    return f"CLM-{suffix}"


@router.get(
    "",
    response_model=ClaimListResponse,
    summary="List all commission claims",
)
async def list_claims(
    skip: int = Query(default=0, ge=0),
    limit: int = Query(default=50, ge=1, le=200),
    current_user: User = Depends(get_current_active_user),
    session: AsyncSession = Depends(get_db_session),
) -> ClaimListResponse:
    """GET /claims — List claims."""
    stmt = (
        select(CommissionClaimModel)
        .order_by(CommissionClaimModel.created_date.desc())
        .offset(skip)
        .limit(limit)
    )
    result = await session.execute(stmt)
    claims = result.scalars().all()
    return ClaimListResponse(
        claims=[ClaimResponse.model_validate(c) for c in claims],
        total=len(claims),
    )


@router.post(
    "",
    response_model=ClaimResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create a new commission claim (status: DRAFT)",
)
async def create_claim(
    request: ClaimCreate,
    current_user: User = Depends(get_current_active_user),
    session: AsyncSession = Depends(get_db_session),
) -> ClaimResponse:
    """POST /claims — Create a claim in DRAFT status."""
    claim = CommissionClaimModel(
        id=uuid4(),
        claim_number=_generate_claim_number(),
        employee_id=str(current_user.id),
        employee_name=request.employee_name,
        amount=request.amount,
        company=request.company,
        department=request.department,
        region=request.region,
        description=request.description,
        status="DRAFT",
        workflow_instance_id=None,
        created_by=current_user.username,
        modified_by=current_user.username,
    )
    session.add(claim)
    await session.flush()
    return ClaimResponse.model_validate(claim)


@router.post(
    "/{claim_id}/submit",
    response_model=ClaimResponse,
    summary="Submit claim — starts the workflow",
)
async def submit_claim(
    claim_id: UUID,
    current_user: User = Depends(get_current_active_user),
    session: AsyncSession = Depends(get_db_session),
) -> ClaimResponse:
    """POST /claims/{id}/submit — Starts the COMMISSION_CLAIM workflow."""
    claim = await session.get(CommissionClaimModel, str(claim_id))
    if not claim:
        raise HTTPException(status_code=404, detail="Claim not found")
    if claim.status != "DRAFT":
        raise HTTPException(status_code=400, detail=f"Cannot submit claim in '{claim.status}' status")

    # Start workflow
    engine = WorkflowEngine(session)
    result = await engine.start_workflow(
        definition_code="COMMISSION_CLAIM",
        entity_type="commission_claim",
        entity_id=claim_id,
        initiated_by=current_user.id,
        metadata={
            "amount": float(claim.amount),
            "company": claim.company,
            "department": claim.department,
            "region": claim.region,
            "claim_number": claim.claim_number,
        },
    )

    # Update claim status and link workflow instance
    claim.status = "SUBMITTED"
    claim.workflow_instance_id = result["instance_id"]
    claim.modified_by = current_user.username

    # Execute the SUBMIT transition on the workflow
    await engine.execute_action(
        instance_id=UUID(result["instance_id"]),
        action_code="SUBMIT",
        actor_id=current_user.id,
        actor_username=current_user.username,
    )

    return ClaimResponse.model_validate(claim)


@router.get(
    "/{claim_id}",
    summary="Get claim details with workflow status",
)
async def get_claim(
    claim_id: UUID,
    current_user: User = Depends(get_current_active_user),
    session: AsyncSession = Depends(get_db_session),
) -> dict:
    """GET /claims/{id} — Claim details + workflow state + available actions."""
    claim = await session.get(CommissionClaimModel, str(claim_id))
    if not claim:
        raise HTTPException(status_code=404, detail="Claim not found")

    response = {
        "claim": ClaimResponse.model_validate(claim),
        "workflow_status": None,
        "available_actions": [],
        "history": [],
    }

    # If workflow is active, get status and actions
    if claim.workflow_instance_id:
        engine = WorkflowEngine(session)
        wf_status = await engine.get_workflow_status(claim.workflow_instance_id)
        actions = await engine.get_available_actions(claim.workflow_instance_id)
        response["workflow_status"] = wf_status
        response["available_actions"] = actions

    return response


@router.post(
    "/{claim_id}/action",
    summary="Execute workflow action on claim (approve, reject, refer back, etc.)",
)
async def execute_claim_action(
    claim_id: UUID,
    action_code: str = Query(..., description="Action code: APPROVE, REJECT, REFER_BACK, CANCEL, CLOSE"),
    comments: str = Query(default="", description="Comments for the action"),
    current_user: User = Depends(get_current_active_user),
    session: AsyncSession = Depends(get_db_session),
) -> dict:
    """POST /claims/{id}/action?action_code=APPROVE — Execute workflow action."""
    claim = await session.get(CommissionClaimModel, str(claim_id))
    if not claim:
        raise HTTPException(status_code=404, detail="Claim not found")
    if not claim.workflow_instance_id:
        raise HTTPException(status_code=400, detail="Claim has no active workflow")

    engine = WorkflowEngine(session)
    result = await engine.execute_action(
        instance_id=claim.workflow_instance_id,
        action_code=action_code,
        actor_id=current_user.id,
        actor_username=current_user.username,
        comments=comments,
    )

    # Sync claim status with workflow state
    claim.status = result["current_status_code"]
    claim.modified_by = current_user.username

    return {
        "claim_id": str(claim_id),
        "claim_number": claim.claim_number,
        "previous_status": result.get("previous_status"),
        "current_status": result["current_status_code"],
        "is_completed": result["is_completed"],
        "action_executed": action_code,
        "comments": comments,
    }
