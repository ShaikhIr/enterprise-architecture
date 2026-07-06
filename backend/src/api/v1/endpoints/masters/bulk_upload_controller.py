"""
Bulk Upload API endpoint.

Thin controller mirroring the sibling master controllers: a
``_get_bulk_upload_service`` dependency factory, ``require_api_permission`` +
``get_current_active_user`` on the route, and master-exception-to-HTTP mapping.

A single ``multipart/form-data`` route accepts the uploaded file and routes by
``entity_type`` (path parameter). All parsing, per-row validation, business-code
resolution, and the savepoint-per-row processing live in
:class:`~src.application.services.masters.bulk_upload_service.BulkUploadService`
(task 14.1); this controller only adapts the request and the returned
:class:`BulkUploadReport` to the API response schema.

Exception mapping (per design):
* ``MasterValidationError`` -> 422 Unprocessable Entity
  (unparseable file or unknown ``entity_type`` — whole-file rejection, Req 19.2)
* ``MasterConflictError``   -> 409 Conflict
* ``MasterNotFoundError``   -> 404 Not Found

NOTE: This router is aggregated into ``api_v1_router`` in ``router.py``.

Requirements: 20.2 (authentication), 20.3 (RBAC).
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile, status
from sqlalchemy.ext.asyncio import AsyncSession

from src.api.v1.dependencies import get_current_active_user, get_user_repository
from src.api.v1.schemas.masters.bulk_upload import BulkUploadReportResponse
from src.application.exceptions.application_exceptions import (
    MasterConflictError,
    MasterNotFoundError,
    MasterValidationError,
)
from src.application.services.masters.agreement_service import AgreementService
from src.application.services.masters.bulk_upload_service import BulkUploadService
from src.application.services.masters.customer_service import CustomerService
from src.application.services.masters.mapping_service import MappingService
from src.application.services.masters.product_service import ProductService
from src.application.services.masters.vendor_service import VendorService
from src.domain.entities.user import User
from src.domain.repositories.user_repository import IUserRepository
from src.infrastructure.database.repositories.masters.agreement_repository_impl import (
    AgreementRepositoryImpl,
)
from src.infrastructure.database.repositories.masters.customer_repository_impl import (
    CustomerRepositoryImpl,
)
from src.infrastructure.database.repositories.masters.mapping_repository_impl import (
    MappingRepositoryImpl,
)
from src.infrastructure.database.repositories.masters.product_repository_impl import (
    ProductRepositoryImpl,
)
from src.infrastructure.database.repositories.masters.vendor_repository_impl import (
    VendorRepositoryImpl,
)
from src.infrastructure.database.session import get_db_session
from src.infrastructure.security.permission_manager import require_api_permission

router = APIRouter(prefix="/bulk-uploads", tags=["Bulk Upload"])

_RESOURCE = "bulk_uploads"


def _get_bulk_upload_service(
    session: AsyncSession = Depends(get_db_session),
    user_repo: IUserRepository = Depends(get_user_repository),
) -> BulkUploadService:
    """FastAPI dependency — build BulkUploadService with injected dependencies.

    Composes the five master services (each delegating its own field
    validation, uniqueness, and default rules) plus the vendor/customer/product
    repositories used for Business-Code → UUID resolution.
    """
    vendor_repo = VendorRepositoryImpl(session)
    customer_repo = CustomerRepositoryImpl(session)
    product_repo = ProductRepositoryImpl(session)
    return BulkUploadService(
        session=session,
        vendor_service=VendorService(
            session=session, vendor_repo=vendor_repo, user_repo=user_repo
        ),
        customer_service=CustomerService(
            session=session, customer_repo=customer_repo
        ),
        product_service=ProductService(session=session, product_repo=product_repo),
        agreement_service=AgreementService(
            session=session,
            agreement_repo=AgreementRepositoryImpl(session),
            vendor_repo=vendor_repo,
            product_repo=product_repo,
        ),
        mapping_service=MappingService(
            session=session,
            mapping_repo=MappingRepositoryImpl(session),
            vendor_repo=vendor_repo,
            customer_repo=customer_repo,
        ),
        vendor_repo=vendor_repo,
        customer_repo=customer_repo,
        product_repo=product_repo,
    )


def _to_http_exception(exc: Exception) -> HTTPException:
    """Translate a master application exception into an ``HTTPException``.

    Both an unparseable file and an unknown ``entity_type`` surface as
    ``MasterValidationError`` from the service and map to 422 (Req 19.2).
    """
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
    "/{entity_type}",
    response_model=BulkUploadReportResponse,
    summary="Bulk-upload a master file for the given entity type",
    dependencies=[Depends(require_api_permission(_RESOURCE, "CREATE"))],
)
async def bulk_upload(
    entity_type: str,
    file: UploadFile = File(...),
    current_user: User = Depends(get_current_active_user),
    service: BulkUploadService = Depends(_get_bulk_upload_service),
) -> BulkUploadReportResponse:
    """POST /api/v1/bulk-uploads/{entity_type} (multipart/form-data).

    Routes by ``entity_type`` (vendor, customer, product_master,
    product_detail, agreement, mapping). An unknown type or an unparseable file
    is rejected with 422 and nothing is stored (Req 19.2); otherwise a per-row
    accounting report is returned (Req 19.6).
    """
    try:
        report = await service.process(
            entity_type=entity_type, file=file, actor=current_user
        )
    except (MasterValidationError, MasterConflictError, MasterNotFoundError) as exc:
        raise _to_http_exception(exc)
    return BulkUploadReportResponse.from_report(report)
