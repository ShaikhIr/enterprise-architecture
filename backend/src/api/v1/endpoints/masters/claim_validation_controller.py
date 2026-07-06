"""
Claim Validation Triangle API endpoint.

Thin controller — validates the request schema, enforces RBAC + authentication,
maps ``ClaimValidationService`` exceptions to HTTP responses, and delegates all
business logic to the service.

The single route evaluates a set of submitted Invoice Lines against the
three-check triangle (active Agreement, active Vendor–Customer Mapping, Invoice
Header Status ``Payment Cleared``) and returns one result per supplied line.
Valid and blocked lines coexist in one response without rejecting the whole
claim (Req 18.5); each blocked line carries one distinct error per failed check
(Req 18.6).

Exception mapping (per design):
* ``MasterValidationError`` -> 422 Unprocessable Entity
* ``MasterConflictError``   -> 409 Conflict
* ``MasterNotFoundError``   -> 404 Not Found

Requirements: 20.2 (authentication), 20.3 (RBAC).

NOTE: The router is intentionally **not** registered in ``router.py`` here; that
wiring is performed by task 15.2.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from src.api.v1.dependencies import get_current_active_user
from src.api.v1.schemas.masters.claim_validation_request import (
    ValidateClaimRequest,
)
from src.api.v1.schemas.masters.claim_validation_response import (
    LineValidationResult,
)
from src.application.exceptions.application_exceptions import (
    MasterConflictError,
    MasterNotFoundError,
    MasterValidationError,
)
from src.application.services.masters.claim_validation_service import (
    ClaimValidationService,
)
from src.domain.entities.user import User
from src.infrastructure.database.repositories.masters.agreement_repository_impl import (
    AgreementRepositoryImpl,
)
from src.infrastructure.database.repositories.masters.invoice_repository_impl import (
    InvoiceRepositoryImpl,
)
from src.infrastructure.database.repositories.masters.mapping_repository_impl import (
    MappingRepositoryImpl,
)
from src.infrastructure.database.repositories.masters.vendor_repository_impl import (
    VendorRepositoryImpl,
)
from src.infrastructure.database.session import get_db_session
from src.infrastructure.security.permission_manager import require_api_permission

router = APIRouter(prefix="/claims", tags=["Claims"])

_RESOURCE = "claims"


def _get_claim_validation_service(
    session: AsyncSession = Depends(get_db_session),
) -> ClaimValidationService:
    """FastAPI dependency — build ClaimValidationService with injected deps."""
    return ClaimValidationService(
        session=session,
        invoice_repo=InvoiceRepositoryImpl(session),
        agreement_repo=AgreementRepositoryImpl(session),
        mapping_repo=MappingRepositoryImpl(session),
        vendor_repo=VendorRepositoryImpl(session),
    )


def _to_http_exception(exc: Exception) -> HTTPException:
    """Translate a master application exception into an ``HTTPException``."""
    if isinstance(exc, MasterValidationError):
        return HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail={"field": exc.field, "reason": exc.reason},
        )
    if isinstance(exc, MasterConflictError):
        return HTTPException(
            status_code=status.HTTP_409_CONFLICT, detail=exc.detail
        )
    if isinstance(exc, MasterNotFoundError):
        return HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)
        )
    return HTTPException(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(exc)
    )


@router.post(
    "/validate",
    response_model=list[LineValidationResult],
    summary="Validate invoice lines against the Claim Validation Triangle",
    dependencies=[Depends(require_api_permission(_RESOURCE, "READ"))],
)
async def validate_claim(
    request: ValidateClaimRequest,
    current_user: User = Depends(get_current_active_user),
    service: ClaimValidationService = Depends(_get_claim_validation_service),
) -> list[LineValidationResult]:
    """POST /api/v1/claims/validate — one result per supplied invoice line."""
    try:
        results = await service.validate_lines(request.invoice_line_ids)
        return [LineValidationResult.from_result(result) for result in results]
    except (MasterValidationError, MasterConflictError, MasterNotFoundError) as exc:
        raise _to_http_exception(exc)
