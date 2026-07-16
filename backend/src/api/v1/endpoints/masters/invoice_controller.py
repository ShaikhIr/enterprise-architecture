"""
Invoice Master API endpoints (Header + Line).

Thin controller — validates request schemas, enforces RBAC + authentication,
maps ``InvoiceService`` exceptions to HTTP responses, and delegates all business
logic to the service. An Invoice is a two-level aggregate, so create accepts a
header plus its lines and the responses nest the lines.

Exception mapping (per design):
* ``MasterValidationError`` -> 422 Unprocessable Entity
* ``MasterConflictError``   -> 409 Conflict
* ``MasterNotFoundError``   -> 404 Not Found

Beyond the standard CRUD routes this controller exposes the status-lifecycle
routes:
* ``POST /{invoice_id}/sap-payment`` — record an SAP payment (Req 17.1)
* ``POST /{invoice_id}/settle``      — mark the invoice Settled (Req 17.2)

Pagination bounds are enforced at the boundary with ``skip = Query(0, ge=0)``
and ``limit = Query(20, ge=1, le=100)``.

Requirements: 20.2 (authentication), 20.3 (RBAC).

NOTE: The router is intentionally **not** registered in ``router.py`` here; that
wiring is performed by task 15.2.
"""

from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from sqlalchemy.ext.asyncio import AsyncSession

from src.api.v1.dependencies import get_current_active_user
from src.api.v1.schemas.masters.common import PaginatedResponse
from src.api.v1.schemas.masters.invoice_request import (
    CreateInvoiceRequest,
    SapPaymentRequest,
    UpdateInvoiceRequest,
)
from src.api.v1.schemas.masters.invoice_response import InvoiceResponse
from src.application.exceptions.application_exceptions import (
    MasterConflictError,
    MasterNotFoundError,
    MasterValidationError,
)
from src.application.services.masters.invoice_service import (
    UNSET,
    InvoiceCreateInput,
    InvoiceLineInput,
    InvoiceService,
    InvoiceUpdateInput,
    SapPaymentInput,
)
from src.domain.entities.user import User
from src.infrastructure.database.repositories.masters.agreement_repository_impl import (
    AgreementRepositoryImpl,
)
from src.infrastructure.database.repositories.masters.customer_repository_impl import (
    CustomerRepositoryImpl,
)
from src.infrastructure.database.repositories.masters.invoice_repository_impl import (
    InvoiceRepositoryImpl,
)
from src.infrastructure.database.repositories.masters.product_repository_impl import (
    ProductRepositoryImpl,
)
from src.infrastructure.database.repositories.masters.vendor_repository_impl import (
    VendorRepositoryImpl,
)
from src.infrastructure.database.session import get_db_session
from src.infrastructure.security.permission_manager import require_api_permission

router = APIRouter(prefix="/invoices", tags=["Invoices"])

_RESOURCE = "invoices"


def _get_invoice_service(
    session: AsyncSession = Depends(get_db_session),
) -> InvoiceService:
    """FastAPI dependency — build InvoiceService with injected dependencies."""
    return InvoiceService(
        session=session,
        invoice_repo=InvoiceRepositoryImpl(session),
        vendor_repo=VendorRepositoryImpl(session),
        customer_repo=CustomerRepositoryImpl(session),
        product_repo=ProductRepositoryImpl(session),
        agreement_repo=AgreementRepositoryImpl(session),
    )


async def _build_product_lookup(
    product_master_ids: list[UUID],
    session: AsyncSession,
) -> dict:
    """Return a {product_master_id: (child_code, product_name)} map for the given IDs."""
    if not product_master_ids:
        return {}
    repo = ProductRepositoryImpl(session)
    lookup: dict = {}
    for pid in set(product_master_ids):
        product = await repo.get_by_id(pid)
        if product:
            lookup[pid] = (product.child_code, product.product_name)
    return lookup


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


def _to_create_input(request: CreateInvoiceRequest) -> InvoiceCreateInput:
    """Map a create request (header + lines) to a service ``InvoiceCreateInput``."""
    return InvoiceCreateInput(
        invoice_number=request.invoice_number,
        invoice_date=request.invoice_date,
        vendor_id=request.vendor_id,
        customer_id=request.customer_id,
        entity_id=request.entity_id,
        bill_amount_excl_gst=request.bill_amount_excl_gst,
        lines=[
            InvoiceLineInput(
                product_master_id=line.product_master_id,
                quantity=line.quantity,
                line_amount=line.line_amount,
                vat_gst_amount=line.vat_gst_amount,
            )
            for line in request.lines
        ],
        bill_amount_incl_tax=request.bill_amount_incl_tax,
        amount_deducted=request.amount_deducted,
        tds_value=request.tds_value,
        due_date=request.due_date,
    )


def _to_update_input(request: UpdateInvoiceRequest) -> InvoiceUpdateInput:
    """Map a partial-update request to a service ``InvoiceUpdateInput``.

    Only fields explicitly present in the request body are forwarded; omitted
    fields remain ``UNSET`` so the service leaves them unchanged. Nullable
    fields (``bill_amount_incl_tax``, ``due_date``) preserve an explicit ``null``
    so the service can clear them; non-nullable fields treat an explicit
    ``null`` as "not supplied".
    """
    fields_set = request.model_fields_set

    def supplied(name: str) -> bool:
        return name in fields_set

    def required_field(name: str, value: object) -> object:
        return value if supplied(name) and value is not None else UNSET

    def nullable_field(name: str, value: object) -> object:
        return value if supplied(name) else UNSET

    return InvoiceUpdateInput(
        bill_amount_excl_gst=required_field(
            "bill_amount_excl_gst", request.bill_amount_excl_gst
        ),
        bill_amount_incl_tax=nullable_field(
            "bill_amount_incl_tax", request.bill_amount_incl_tax
        ),
        amount_deducted=required_field("amount_deducted", request.amount_deducted),
        tds_value=required_field("tds_value", request.tds_value),
        due_date=nullable_field("due_date", request.due_date),
    )


@router.post(
    "",
    response_model=InvoiceResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create a new invoice (header + lines)",
    dependencies=[Depends(require_api_permission(_RESOURCE, "CREATE"))],
)
async def create_invoice(
    request: CreateInvoiceRequest,
    current_user: User = Depends(get_current_active_user),
    service: InvoiceService = Depends(_get_invoice_service),
    session: AsyncSession = Depends(get_db_session),
) -> InvoiceResponse:
    """POST /api/v1/invoices"""
    try:
        invoice = await service.create_invoice(
            data=_to_create_input(request), actor=current_user
        )
        product_ids = [l.product_master_id for l in invoice.lines if l.product_master_id]
        lookup = await _build_product_lookup(product_ids, session)
        return InvoiceResponse.from_entity(invoice, product_lookup=lookup)
    except (MasterValidationError, MasterConflictError, MasterNotFoundError) as exc:
        raise _to_http_exception(exc)


@router.get(
    "",
    response_model=PaginatedResponse[InvoiceResponse],
    summary="List invoices (paginated, filterable)",
    dependencies=[Depends(require_api_permission(_RESOURCE, "READ"))],
)
async def list_invoices(
    skip: int = Query(0, ge=0),
    limit: int = Query(20, ge=1, le=500),
    invoice_number: str | None = Query(default=None),
    vendor_name: str | None = Query(default=None),
    customer_name: str | None = Query(default=None),
    invoice_status: str | None = Query(default=None, alias="status"),
    vendor_id: str | None = Query(default=None),
    entity_id: str | None = Query(default=None),
    service: InvoiceService = Depends(_get_invoice_service),
    session: AsyncSession = Depends(get_db_session),
) -> PaginatedResponse[InvoiceResponse]:
    """GET /api/v1/invoices"""
    items, total = await service.list_invoices(
        skip=skip, limit=limit,
        invoice_number=invoice_number,
        vendor_name=vendor_name,
        customer_name=customer_name,
        invoice_status=invoice_status,
        vendor_id=vendor_id,
        entity_id=entity_id,
    )
    # Collect all unique product IDs across all invoice lines
    all_product_ids = [
        line.product_master_id
        for entity, _, _ in items
        for line in entity.lines
        if line.product_master_id
    ]
    lookup = await _build_product_lookup(all_product_ids, session)
    return PaginatedResponse[InvoiceResponse](
        items=[
            InvoiceResponse.from_entity(entity, v_name, c_name, product_lookup=lookup)
            for entity, v_name, c_name in items
        ],
        total=total,
        skip=skip,
        limit=limit,
    )


@router.get(
    "/{invoice_id}",
    response_model=InvoiceResponse,
    summary="Get an invoice by ID",
    dependencies=[Depends(require_api_permission(_RESOURCE, "READ"))],
)
async def get_invoice(
    invoice_id: UUID,
    service: InvoiceService = Depends(_get_invoice_service),
    session: AsyncSession = Depends(get_db_session),
) -> InvoiceResponse:
    """GET /api/v1/invoices/{invoice_id}"""
    try:
        invoice = await service.get_invoice(invoice_id)
        product_ids = [l.product_master_id for l in invoice.lines if l.product_master_id]
        lookup = await _build_product_lookup(product_ids, session)
        return InvoiceResponse.from_entity(invoice, product_lookup=lookup)
    except (MasterValidationError, MasterConflictError, MasterNotFoundError) as exc:
        raise _to_http_exception(exc)


@router.patch(
    "/{invoice_id}",
    response_model=InvoiceResponse,
    summary="Update an invoice header (partial)",
    dependencies=[Depends(require_api_permission(_RESOURCE, "UPDATE"))],
)
async def update_invoice(
    invoice_id: UUID,
    request: UpdateInvoiceRequest,
    current_user: User = Depends(get_current_active_user),
    service: InvoiceService = Depends(_get_invoice_service),
    session: AsyncSession = Depends(get_db_session),
) -> InvoiceResponse:
    """PATCH /api/v1/invoices/{invoice_id}"""
    try:
        invoice = await service.update_invoice(
            invoice_id=invoice_id,
            patch=_to_update_input(request),
            actor=current_user,
        )
        product_ids = [l.product_master_id for l in invoice.lines if l.product_master_id]
        lookup = await _build_product_lookup(product_ids, session)
        return InvoiceResponse.from_entity(invoice, product_lookup=lookup)
    except (MasterValidationError, MasterConflictError, MasterNotFoundError) as exc:
        raise _to_http_exception(exc)


@router.delete(
    "/{invoice_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete an invoice (cascades its lines)",
    dependencies=[Depends(require_api_permission(_RESOURCE, "DELETE"))],
)
async def delete_invoice(
    invoice_id: UUID,
    current_user: User = Depends(get_current_active_user),
    service: InvoiceService = Depends(_get_invoice_service),
) -> Response:
    """DELETE /api/v1/invoices/{invoice_id}"""
    try:
        await service.delete_invoice(invoice_id, actor=current_user)
        return Response(status_code=status.HTTP_204_NO_CONTENT)
    except (MasterValidationError, MasterConflictError, MasterNotFoundError) as exc:
        raise _to_http_exception(exc)


@router.post(
    "/{invoice_id}/sap-payment",
    response_model=InvoiceResponse,
    summary="Record an SAP payment confirmation",
    dependencies=[Depends(require_api_permission(_RESOURCE, "UPDATE"))],
)
async def record_sap_payment(
    invoice_id: UUID,
    request: SapPaymentRequest,
    current_user: User = Depends(get_current_active_user),
    service: InvoiceService = Depends(_get_invoice_service),
    session: AsyncSession = Depends(get_db_session),
) -> InvoiceResponse:
    """POST /api/v1/invoices/{invoice_id}/sap-payment — sets Status Payment Cleared (Req 17.1)."""
    try:
        invoice = await service.record_sap_payment(
            data=SapPaymentInput(
                payment_clearing_date=request.payment_clearing_date,
                sap_clearing_document_no=request.sap_clearing_document_no,
                invoice_id=invoice_id,
                invoice_number=request.invoice_number,
            ),
            actor=current_user,
        )
        product_ids = [l.product_master_id for l in invoice.lines if l.product_master_id]
        lookup = await _build_product_lookup(product_ids, session)
        return InvoiceResponse.from_entity(invoice, product_lookup=lookup)
    except (MasterValidationError, MasterConflictError, MasterNotFoundError) as exc:
        raise _to_http_exception(exc)


@router.post(
    "/{invoice_id}/settle",
    response_model=InvoiceResponse,
    summary="Mark an invoice Settled (final claim approval)",
    dependencies=[Depends(require_api_permission(_RESOURCE, "UPDATE"))],
)
async def mark_settled(
    invoice_id: UUID,
    current_user: User = Depends(get_current_active_user),
    service: InvoiceService = Depends(_get_invoice_service),
    session: AsyncSession = Depends(get_db_session),
) -> InvoiceResponse:
    """POST /api/v1/invoices/{invoice_id}/settle — sets Status Settled (Req 17.2)."""
    try:
        invoice = await service.mark_settled(invoice_id, actor=current_user)
        product_ids = [l.product_master_id for l in invoice.lines if l.product_master_id]
        lookup = await _build_product_lookup(product_ids, session)
        return InvoiceResponse.from_entity(invoice, product_lookup=lookup)
    except (MasterValidationError, MasterConflictError, MasterNotFoundError) as exc:
        raise _to_http_exception(exc)
