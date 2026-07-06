"""
Vendor-Customer Mapping API endpoints.

Thin controller — validates request schemas, enforces RBAC + authentication,
maps ``MappingService`` exceptions to HTTP responses, and delegates all
business logic to the service.

Exception mapping (per design):
* ``MasterValidationError`` -> 422 Unprocessable Entity
* ``MasterConflictError``   -> 409 Conflict
* ``MasterNotFoundError``   -> 404 Not Found

List filtering (Req 14.7, 20.4) supports any combination of ``vendor_id`` and
``customer_id`` query parameters. Pagination bounds (Req 14) are enforced at the
boundary with ``skip = Query(0, ge=0)`` and ``limit = Query(20, ge=1, le=100)``.

NOTE: This router is aggregated into ``api_v1_router`` in ``router.py``.
"""

from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from sqlalchemy.ext.asyncio import AsyncSession

from src.api.v1.dependencies import get_current_active_user
from src.api.v1.schemas.masters.common import PaginatedResponse
from src.api.v1.schemas.masters.mapping_request import (
    CreateMappingRequest,
    UpdateMappingRequest,
)
from src.api.v1.schemas.masters.mapping_response import MappingResponse
from src.application.exceptions.application_exceptions import (
    MasterConflictError,
    MasterNotFoundError,
    MasterValidationError,
)
from src.application.services.masters.mapping_service import (
    UNSET,
    MappingCreateInput,
    MappingService,
    MappingUpdateInput,
)
from src.domain.entities.user import User
from src.infrastructure.database.repositories.masters.customer_repository_impl import (
    CustomerRepositoryImpl,
)
from src.infrastructure.database.repositories.masters.mapping_repository_impl import (
    MappingRepositoryImpl,
)
from src.infrastructure.database.repositories.masters.vendor_repository_impl import (
    VendorRepositoryImpl,
)
from src.infrastructure.database.session import get_db_session
from src.infrastructure.security.permission_manager import require_api_permission

router = APIRouter(prefix="/mappings", tags=["Mappings"])

_RESOURCE = "mappings"


def _get_mapping_service(
    session: AsyncSession = Depends(get_db_session),
) -> MappingService:
    """FastAPI dependency — build MappingService with injected dependencies."""
    return MappingService(
        session=session,
        mapping_repo=MappingRepositoryImpl(session),
        vendor_repo=VendorRepositoryImpl(session),
        customer_repo=CustomerRepositoryImpl(session),
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


def _to_update_input(request: UpdateMappingRequest) -> MappingUpdateInput:
    """Map a dates-only partial-update request to ``MappingUpdateInput``.

    Only fields explicitly present in the request body are forwarded; omitted
    fields remain ``UNSET`` so the service leaves them unchanged (Req 14.6).
    Validity dates are non-nullable, so an explicit ``null`` is treated as "not
    supplied".
    """
    fields_set = request.model_fields_set

    def supplied(name: str) -> bool:
        return name in fields_set and getattr(request, name) is not None

    return MappingUpdateInput(
        validity_from=(
            request.validity_from if supplied("validity_from") else UNSET
        ),
        validity_to=(
            request.validity_to if supplied("validity_to") else UNSET
        ),
    )


@router.post(
    "",
    response_model=MappingResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create a new vendor-customer mapping",
    dependencies=[Depends(require_api_permission(_RESOURCE, "CREATE"))],
)
async def create_mapping(
    request: CreateMappingRequest,
    current_user: User = Depends(get_current_active_user),
    service: MappingService = Depends(_get_mapping_service),
) -> MappingResponse:
    """POST /api/v1/mappings"""
    try:
        mapping = await service.create_mapping(
            data=MappingCreateInput(
                vendor_id=request.vendor_id,
                customer_id=request.customer_id,
                validity_from=request.validity_from,
                validity_to=request.validity_to,
                status=request.status,
            ),
            actor=current_user,
        )
        return MappingResponse.from_entity(mapping)
    except (MasterValidationError, MasterConflictError, MasterNotFoundError) as exc:
        raise _to_http_exception(exc)


@router.get(
    "",
    response_model=PaginatedResponse[MappingResponse],
    summary="List mappings (paginated, filterable by vendor and/or customer)",
    dependencies=[Depends(require_api_permission(_RESOURCE, "READ"))],
)
async def list_mappings(
    vendor_id: UUID | None = Query(default=None),
    customer_id: UUID | None = Query(default=None),
    skip: int = Query(0, ge=0),
    limit: int = Query(20, ge=1, le=1000),
    service: MappingService = Depends(_get_mapping_service),
) -> PaginatedResponse[MappingResponse]:
    """GET /api/v1/mappings — combined vendor/customer filters (Req 14.7, 20.4)."""
    items, total = await service.list_mappings(
        skip=skip,
        limit=limit,
        vendor_id=vendor_id,
        customer_id=customer_id,
    )
    return PaginatedResponse[MappingResponse](
        items=[
            MappingResponse.from_entity(entity, vendor_name, customer_name)
            for entity, vendor_name, customer_name in items
        ],
        total=total,
        skip=skip,
        limit=limit,
    )


@router.get(
    "/{mapping_id}",
    response_model=MappingResponse,
    summary="Get a mapping by ID",
    dependencies=[Depends(require_api_permission(_RESOURCE, "READ"))],
)
async def get_mapping(
    mapping_id: UUID,
    service: MappingService = Depends(_get_mapping_service),
) -> MappingResponse:
    """GET /api/v1/mappings/{mapping_id}"""
    try:
        mapping = await service.get_mapping(mapping_id)
        return MappingResponse.from_entity(mapping)
    except (MasterValidationError, MasterConflictError, MasterNotFoundError) as exc:
        raise _to_http_exception(exc)


@router.patch(
    "/{mapping_id}",
    response_model=MappingResponse,
    summary="Update a mapping (validity dates only)",
    dependencies=[Depends(require_api_permission(_RESOURCE, "UPDATE"))],
)
async def update_mapping(
    mapping_id: UUID,
    request: UpdateMappingRequest,
    current_user: User = Depends(get_current_active_user),
    service: MappingService = Depends(_get_mapping_service),
) -> MappingResponse:
    """PATCH /api/v1/mappings/{mapping_id} — only validity dates are applied."""
    try:
        mapping = await service.update_mapping(
            mapping_id=mapping_id,
            patch=_to_update_input(request),
            actor=current_user,
        )
        return MappingResponse.from_entity(mapping)
    except (MasterValidationError, MasterConflictError, MasterNotFoundError) as exc:
        raise _to_http_exception(exc)


@router.delete(
    "/{mapping_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete a mapping",
    dependencies=[Depends(require_api_permission(_RESOURCE, "DELETE"))],
)
async def delete_mapping(
    mapping_id: UUID,
    current_user: User = Depends(get_current_active_user),
    service: MappingService = Depends(_get_mapping_service),
) -> Response:
    """DELETE /api/v1/mappings/{mapping_id}"""
    try:
        await service.delete_mapping(mapping_id, actor=current_user)
        return Response(status_code=status.HTTP_204_NO_CONTENT)
    except (MasterValidationError, MasterConflictError, MasterNotFoundError) as exc:
        raise _to_http_exception(exc)
