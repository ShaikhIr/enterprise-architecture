"""
Customer Master API endpoints.

Thin controller — validates request schemas, enforces RBAC + authentication,
maps ``CustomerService`` exceptions to HTTP responses, and delegates all
business logic to the service.

Exception mapping (per design):
* ``MasterValidationError`` -> 422 Unprocessable Entity
* ``MasterConflictError``   -> 409 Conflict
* ``MasterNotFoundError``   -> 404 Not Found

Pagination bounds (Req 8.7) are enforced at the boundary with
``skip = Query(0, ge=0)`` and ``limit = Query(20, ge=1, le=100)``.
"""

from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from sqlalchemy.ext.asyncio import AsyncSession

from src.api.v1.dependencies import get_current_active_user
from src.api.v1.schemas.masters.common import PaginatedResponse
from src.api.v1.schemas.masters.customer_request import (
    CreateCustomerRequest,
    UpdateCustomerRequest,
)
from src.api.v1.schemas.masters.customer_response import CustomerResponse
from src.application.exceptions.application_exceptions import (
    MasterConflictError,
    MasterNotFoundError,
    MasterValidationError,
)
from src.application.services.masters.customer_service import (
    UNSET,
    CustomerCreateInput,
    CustomerService,
    CustomerUpdateInput,
)
from src.domain.entities.user import User
from src.domain.repositories.masters.customer_repository import ICustomerRepository
from src.infrastructure.database.repositories.masters.customer_repository_impl import (
    CustomerRepositoryImpl,
)
from src.infrastructure.database.session import get_db_session
from src.infrastructure.security.permission_manager import require_api_permission

router = APIRouter(prefix="/customers", tags=["Customers"])

_RESOURCE = "customers"


def get_customer_repository(
    session: AsyncSession = Depends(get_db_session),
) -> ICustomerRepository:
    """Provide the Customer repository with an injected session."""
    return CustomerRepositoryImpl(session)


def _get_customer_service(
    session: AsyncSession = Depends(get_db_session),
    customer_repo: ICustomerRepository = Depends(get_customer_repository),
) -> CustomerService:
    """FastAPI dependency — build CustomerService with injected dependencies."""
    return CustomerService(session=session, customer_repo=customer_repo)


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


def _to_update_input(request: UpdateCustomerRequest) -> CustomerUpdateInput:
    """Map a partial-update request to a service ``CustomerUpdateInput``.

    Only fields explicitly present in the request body are forwarded; omitted
    fields remain ``UNSET`` so the service leaves them unchanged. ``status`` is
    non-nullable, so an explicit ``null`` is treated as "not supplied".
    """
    fields_set = request.model_fields_set

    def supplied(name: str) -> bool:
        return name in fields_set

    return CustomerUpdateInput(
        customer_code=request.customer_code if supplied("customer_code") else UNSET,
        customer_name=request.customer_name if supplied("customer_name") else UNSET,
        address=request.address if supplied("address") else UNSET,
        gstn_number=request.gstn_number if supplied("gstn_number") else UNSET,
        contact_person=(
            request.contact_person if supplied("contact_person") else UNSET
        ),
        contact_number=(
            request.contact_number if supplied("contact_number") else UNSET
        ),
        contact_email=(
            request.contact_email if supplied("contact_email") else UNSET
        ),
        status=(
            request.status
            if supplied("status") and request.status is not None
            else UNSET
        ),
    )


@router.post(
    "",
    response_model=CustomerResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create a new customer",
    dependencies=[Depends(require_api_permission(_RESOURCE, "CREATE"))],
)
async def create_customer(
    request: CreateCustomerRequest,
    current_user: User = Depends(get_current_active_user),
    service: CustomerService = Depends(_get_customer_service),
) -> CustomerResponse:
    """POST /api/v1/customers"""
    try:
        customer = await service.create_customer(
            data=CustomerCreateInput(
                customer_code=request.customer_code,
                customer_name=request.customer_name,
                address=request.address,
                gstn_number=request.gstn_number,
                contact_person=request.contact_person,
                contact_number=request.contact_number,
                contact_email=request.contact_email,
                status=request.status,
            ),
            actor=current_user,
        )
        return CustomerResponse.from_entity(customer)
    except (MasterValidationError, MasterConflictError, MasterNotFoundError) as exc:
        raise _to_http_exception(exc)


@router.get(
    "",
    response_model=PaginatedResponse[CustomerResponse],
    summary="List customers (paginated, filterable)",
    dependencies=[Depends(require_api_permission(_RESOURCE, "READ"))],
)
async def list_customers(
    skip: int = Query(default=0, ge=0),
    limit: int = Query(default=20, ge=1, le=1000),
    customer_code: str | None = Query(default=None),
    customer_name: str | None = Query(default=None),
    service: CustomerService = Depends(_get_customer_service),
) -> PaginatedResponse[CustomerResponse]:
    """GET /api/v1/customers"""
    items, total = await service.list_customers(
        skip=skip, limit=limit,
        customer_code=customer_code, customer_name=customer_name,
    )
    return PaginatedResponse[CustomerResponse](
        items=[CustomerResponse.from_entity(c) for c in items],
        total=total,
        skip=skip,
        limit=limit,
    )


@router.get(
    "/{customer_id}",
    response_model=CustomerResponse,
    summary="Get a customer by ID",
    dependencies=[Depends(require_api_permission(_RESOURCE, "READ"))],
)
async def get_customer(
    customer_id: UUID,
    service: CustomerService = Depends(_get_customer_service),
) -> CustomerResponse:
    """GET /api/v1/customers/{customer_id}"""
    try:
        customer = await service.get_customer(customer_id)
        return CustomerResponse.from_entity(customer)
    except (MasterValidationError, MasterConflictError, MasterNotFoundError) as exc:
        raise _to_http_exception(exc)


@router.patch(
    "/{customer_id}",
    response_model=CustomerResponse,
    summary="Update a customer (partial)",
    dependencies=[Depends(require_api_permission(_RESOURCE, "UPDATE"))],
)
async def update_customer(
    customer_id: UUID,
    request: UpdateCustomerRequest,
    current_user: User = Depends(get_current_active_user),
    service: CustomerService = Depends(_get_customer_service),
) -> CustomerResponse:
    """PATCH /api/v1/customers/{customer_id}"""
    try:
        customer = await service.update_customer(
            customer_id=customer_id,
            patch=_to_update_input(request),
            actor=current_user,
        )
        return CustomerResponse.from_entity(customer)
    except (MasterValidationError, MasterConflictError, MasterNotFoundError) as exc:
        raise _to_http_exception(exc)


@router.delete(
    "/{customer_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete a customer (blocked while in use)",
    dependencies=[Depends(require_api_permission(_RESOURCE, "DELETE"))],
)
async def delete_customer(
    customer_id: UUID,
    current_user: User = Depends(get_current_active_user),
    service: CustomerService = Depends(_get_customer_service),
) -> Response:
    """DELETE /api/v1/customers/{customer_id}"""
    try:
        await service.delete_customer(customer_id, actor=current_user)
        return Response(status_code=status.HTTP_204_NO_CONTENT)
    except (MasterValidationError, MasterConflictError, MasterNotFoundError) as exc:
        raise _to_http_exception(exc)
