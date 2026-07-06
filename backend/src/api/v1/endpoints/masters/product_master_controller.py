"""
Product Master API endpoints.

Provides CRUD operations for the merged Product Master entity.
The former separate product_detail endpoints have been removed — all
product data now lives under ``/api/v1/product-masters``.

_Requirements: 9.2-9.7, 20.2, 20.3_
"""

from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from sqlalchemy.ext.asyncio import AsyncSession

from src.api.v1.dependencies import get_current_active_user
from src.api.v1.schemas.masters.common import PaginatedResponse
from src.api.v1.schemas.masters.product import (
    ProductMasterCreateRequest,
    ProductMasterResponse,
    ProductMasterUpdateRequest,
)
from src.application.exceptions.application_exceptions import (
    MasterConflictError,
    MasterNotFoundError,
    MasterValidationError,
)
from src.application.services.masters.product_service import (
    ProductMasterCreateInput,
    ProductMasterUpdateInput,
    ProductService,
)
from src.domain.entities.user import User
from src.infrastructure.database.repositories.masters.product_repository_impl import (
    ProductRepositoryImpl,
)
from src.infrastructure.database.session import get_db_session
from src.infrastructure.security.permission_manager import require_api_permission

router = APIRouter(prefix="/product-masters", tags=["Product Master"])


def _get_product_service(
    session: AsyncSession = Depends(get_db_session),
) -> ProductService:
    return ProductService(session=session, product_repo=ProductRepositoryImpl(session))


def _raise_for_master_error(exc: Exception) -> None:
    if isinstance(exc, MasterValidationError):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail={"field": exc.field, "reason": exc.reason},
        )
    if isinstance(exc, MasterConflictError):
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=exc.detail)
    if isinstance(exc, MasterNotFoundError):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc))
    raise exc


@router.get(
    "",
    response_model=PaginatedResponse[ProductMasterResponse],
    summary="List Product Masters",
    dependencies=[Depends(require_api_permission("products", "READ"))],
)
async def list_product_masters(
    skip: int = Query(0, ge=0),
    limit: int = Query(20, ge=1, le=1000),
    service: ProductService = Depends(_get_product_service),
) -> PaginatedResponse[ProductMasterResponse]:
    """GET /api/v1/product-masters"""
    items, total = await service.list(skip=skip, limit=limit)
    return PaginatedResponse[ProductMasterResponse](
        items=[ProductMasterResponse.from_entity(m) for m in items],
        total=total,
        skip=skip,
        limit=limit,
    )


@router.post(
    "",
    response_model=ProductMasterResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create a Product Master",
    dependencies=[Depends(require_api_permission("products", "CREATE"))],
)
async def create_product_master(
    request: ProductMasterCreateRequest,
    current_user: User = Depends(get_current_active_user),
    service: ProductService = Depends(_get_product_service),
) -> ProductMasterResponse:
    """POST /api/v1/product-masters"""
    try:
        product = await service.create(
            ProductMasterCreateInput(
                basic_material_code=request.basic_material_code,
                product_name=request.product_name,
                child_code=request.child_code,
                variant_description=request.variant_description,
                hsn_code=request.hsn_code,
                pack_size=request.pack_size,
                unit_of_measure=request.unit_of_measure,
                mrp=request.mrp,
                rate=request.rate,
                gst_percent=request.gst_percent,
                status=request.status,
            ),
            actor=current_user,
        )
    except (MasterValidationError, MasterConflictError) as exc:
        _raise_for_master_error(exc)
    return ProductMasterResponse.from_entity(product)


@router.get(
    "/{product_id}",
    response_model=ProductMasterResponse,
    summary="Get a Product Master by ID",
    dependencies=[Depends(require_api_permission("products", "READ"))],
)
async def get_product_master(
    product_id: UUID,
    service: ProductService = Depends(_get_product_service),
) -> ProductMasterResponse:
    """GET /api/v1/product-masters/{product_id}"""
    try:
        product = await service.get(product_id)
    except MasterNotFoundError as exc:
        _raise_for_master_error(exc)
    return ProductMasterResponse.from_entity(product)


@router.patch(
    "/{product_id}",
    response_model=ProductMasterResponse,
    summary="Update a Product Master",
    dependencies=[Depends(require_api_permission("products", "UPDATE"))],
)
async def update_product_master(
    product_id: UUID,
    request: ProductMasterUpdateRequest,
    current_user: User = Depends(get_current_active_user),
    service: ProductService = Depends(_get_product_service),
) -> ProductMasterResponse:
    """PATCH /api/v1/product-masters/{product_id}"""
    supplied = request.model_fields_set
    patch = ProductMasterUpdateInput(
        **{
            field: getattr(request, field)
            for field in (
                "basic_material_code",
                "product_name",
                "child_code",
                "variant_description",
                "hsn_code",
                "pack_size",
                "unit_of_measure",
                "mrp",
                "rate",
                "gst_percent",
                "status",
            )
            if field in supplied
        }
    )
    try:
        product = await service.update(product_id, patch, actor=current_user)
    except (MasterValidationError, MasterConflictError, MasterNotFoundError) as exc:
        _raise_for_master_error(exc)
    return ProductMasterResponse.from_entity(product)


@router.delete(
    "/{product_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete a Product Master",
    dependencies=[Depends(require_api_permission("products", "DELETE"))],
)
async def delete_product_master(
    product_id: UUID,
    current_user: User = Depends(get_current_active_user),
    service: ProductService = Depends(_get_product_service),
) -> Response:
    """DELETE /api/v1/product-masters/{product_id}"""
    try:
        await service.delete(product_id, actor=current_user)
        return Response(status_code=status.HTTP_204_NO_CONTENT)
    except (MasterConflictError, MasterNotFoundError) as exc:
        _raise_for_master_error(exc)
