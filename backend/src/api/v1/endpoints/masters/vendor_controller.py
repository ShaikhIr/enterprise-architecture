"""
Vendor Master API endpoints.

Thin controller mirroring ``user_controller.py``: a ``_get_vendor_service``
dependency factory, ``require_api_permission("vendors", "<ACTION>")`` on each
route, ``get_current_active_user`` for the actor, and exception-to-HTTP mapping
(``MasterValidationError`` → 422, ``MasterConflictError`` → 409,
``MasterNotFoundError`` → 404). All business logic lives in ``VendorService``.

Requirements: 6.11 (paginated list), 6.12 (pagination bounds), 20.2
(authentication), 20.3 (RBAC).
"""

from typing import NoReturn
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from src.api.v1.dependencies import get_current_active_user, get_user_repository
from src.api.v1.schemas.masters.common import PaginatedResponse
from src.api.v1.schemas.masters.vendor import (
    CreateVendorRequest,
    UpdateVendorRequest,
    VendorResponse,
)
from src.application.exceptions.application_exceptions import (
    MasterConflictError,
    MasterError,
    MasterNotFoundError,
    MasterValidationError,
)
from src.application.services.masters.vendor_service import (
    VendorCreateInput,
    VendorService,
    VendorUpdateInput,
)
from src.domain.entities.user import User
from src.domain.repositories.user_repository import IUserRepository
from src.infrastructure.database.repositories.masters.vendor_repository_impl import (
    VendorRepositoryImpl,
)
from src.infrastructure.database.session import get_db_session
from src.infrastructure.security.permission_manager import require_api_permission

router = APIRouter(prefix="/vendors", tags=["Vendors"])


def _get_vendor_service(
    session: AsyncSession = Depends(get_db_session),
    user_repo: IUserRepository = Depends(get_user_repository),
) -> VendorService:
    """FastAPI dependency — builds VendorService with injected dependencies."""
    return VendorService(
        session=session,
        vendor_repo=VendorRepositoryImpl(session),
        user_repo=user_repo,
    )


def _raise_http(exc: MasterError) -> NoReturn:
    """Map a master application exception to the matching HTTP error."""
    if isinstance(exc, MasterValidationError):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail={"field": exc.field, "reason": exc.reason},
        )
    if isinstance(exc, MasterConflictError):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=exc.detail,
        )
    if isinstance(exc, MasterNotFoundError):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(exc),
        )
    raise exc  # pragma: no cover - defensive: unknown master error


@router.get(
    "",
    response_model=PaginatedResponse[VendorResponse],
    summary="List vendors (paginated, filterable)",
    dependencies=[Depends(require_api_permission("vendors", "READ"))],
)
async def list_vendors(
    skip: int = Query(0, ge=0),
    limit: int = Query(20, ge=1, le=1000),
    vendor_code: str | None = Query(default=None),
    vendor_name: str | None = Query(default=None),
    vendor_email: str | None = Query(default=None),
    city: str | None = Query(default=None),
    status: str | None = Query(default=None),
    service: VendorService = Depends(_get_vendor_service),
) -> PaginatedResponse[VendorResponse]:
    """GET /api/v1/vendors"""
    items, total = await service.list_vendors(
        skip=skip, limit=limit,
        vendor_code=vendor_code, vendor_name=vendor_name,
        vendor_email=vendor_email, city=city, status=status,
    )
    return PaginatedResponse[VendorResponse](
        items=[VendorResponse.from_entity(v) for v in items],
        total=total,
        skip=skip,
        limit=limit,
    )


@router.post(
    "",
    response_model=VendorResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create a vendor",
    dependencies=[Depends(require_api_permission("vendors", "CREATE"))],
)
async def create_vendor(
    request: CreateVendorRequest,
    current_user: User = Depends(get_current_active_user),
    service: VendorService = Depends(_get_vendor_service),
) -> VendorResponse:
    """POST /api/v1/vendors"""
    try:
        vendor = await service.create_vendor(
            VendorCreateInput(
                vendor_code=request.vendor_code,
                vendor_name=request.vendor_name,
                vendor_email=request.vendor_email,
                vendor_contact=request.vendor_contact,
                vendor_address=request.vendor_address,
                city=request.city,
                gstn_number=request.gstn_number,
                pan_number=request.pan_number,
                bank_account_no=request.bank_account_no,
                bank_ifsc=request.bank_ifsc,
                bank_name=request.bank_name,
            ),
            actor=current_user,
        )
    except MasterError as exc:
        _raise_http(exc)
    return VendorResponse.from_entity(vendor)


@router.get(
    "/{vendor_id}",
    response_model=VendorResponse,
    summary="Get a vendor by ID",
    dependencies=[Depends(require_api_permission("vendors", "READ"))],
)
async def get_vendor(
    vendor_id: UUID,
    current_user: User = Depends(get_current_active_user),
    service: VendorService = Depends(_get_vendor_service),
) -> VendorResponse:
    """GET /api/v1/vendors/{vendor_id}"""
    try:
        vendor = await service.get_vendor(vendor_id)
    except MasterError as exc:
        _raise_http(exc)
    return VendorResponse.from_entity(vendor)


@router.patch(
    "/{vendor_id}",
    response_model=VendorResponse,
    summary="Update a vendor (partial)",
    dependencies=[Depends(require_api_permission("vendors", "UPDATE"))],
)
async def update_vendor(
    vendor_id: UUID,
    request: UpdateVendorRequest,
    current_user: User = Depends(get_current_active_user),
    service: VendorService = Depends(_get_vendor_service),
) -> VendorResponse:
    """PATCH /api/v1/vendors/{vendor_id} — only supplied fields are applied."""
    supplied = request.model_dump(exclude_unset=True)
    try:
        vendor = await service.update_vendor(
            vendor_id,
            VendorUpdateInput(**supplied),
            actor=current_user,
        )
    except MasterError as exc:
        _raise_http(exc)
    return VendorResponse.from_entity(vendor)


@router.post(
    "/{vendor_id}/deactivate",
    response_model=VendorResponse,
    summary="Deactivate a vendor",
    dependencies=[Depends(require_api_permission("vendors", "UPDATE"))],
)
async def deactivate_vendor(
    vendor_id: UUID,
    current_user: User = Depends(get_current_active_user),
    service: VendorService = Depends(_get_vendor_service),
) -> VendorResponse:
    """POST /api/v1/vendors/{vendor_id}/deactivate — sets status Inactive (Req 7)."""
    try:
        vendor = await service.deactivate_vendor(vendor_id, actor=current_user)
    except MasterError as exc:
        _raise_http(exc)
    return VendorResponse.from_entity(vendor)
