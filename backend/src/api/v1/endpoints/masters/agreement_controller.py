"""
Agreement Master API endpoints.

Thin controller mirroring the sibling master controllers
(``product_master_controller.py``, ``customer_controller.py``): a
``_get_agreement_service`` dependency factory, ``require_api_permission`` +
``get_current_active_user`` on each route, pagination bounds enforced at the
boundary, an optional ``vendor_id`` list filter (Req 11.10 / 20.4), a renewal
route, and master-exception-to-HTTP mapping
(``MasterValidationError`` → 422, ``MasterConflictError`` → 409,
``MasterNotFoundError`` → 404).

The create / update / renew routes accept ``multipart/form-data`` so an
Agreement Document (PDF/JPEG/PNG, ≤ 10 MB — Req 11.9) can be uploaded alongside
the structured fields. The controller reads the uploaded file's content type and
size into an :class:`AgreementDocumentInput` for the service to validate; the
persisted storage reference (S3 upload) is wired by a later task and defaults to
the uploaded file name here.

This module deliberately does **not** register its router in ``router.py`` —
that wiring is task 15.2.

Requirements: 11.10, 20.2 (authentication), 20.3 (RBAC), 20.4 (vendor scoping).
"""

from __future__ import annotations

from typing import NoReturn
from uuid import UUID

from fastapi import (
    APIRouter,
    Depends,
    File,
    HTTPException,
    Query,
    Response,
    UploadFile,
    status,
)
from sqlalchemy.ext.asyncio import AsyncSession

from src.api.v1.dependencies import get_current_active_user
from src.api.v1.schemas.masters.agreement import (
    AgreementCreateRequest,
    AgreementRenewRequest,
    AgreementResponse,
    AgreementUpdateRequest,
)
from src.api.v1.schemas.masters.common import PaginatedResponse
from src.application.exceptions.application_exceptions import (
    MasterConflictError,
    MasterError,
    MasterNotFoundError,
    MasterValidationError,
)
from src.application.services.masters.agreement_service import (
    UNSET,
    AgreementCreateInput,
    AgreementDocumentInput,
    AgreementRenewalInput,
    AgreementService,
    AgreementUpdateInput,
)
from src.domain.entities.user import User
from src.infrastructure.database.repositories.masters.agreement_repository_impl import (
    AgreementRepositoryImpl,
)
from src.infrastructure.database.repositories.masters.product_repository_impl import (
    ProductRepositoryImpl,
)
from src.infrastructure.database.repositories.masters.vendor_repository_impl import (
    VendorRepositoryImpl,
)
from src.infrastructure.database.session import get_db_session
from src.infrastructure.security.permission_manager import require_api_permission

router = APIRouter(prefix="/agreements", tags=["Agreements"])

_RESOURCE = "agreements"


def _get_agreement_service(
    session: AsyncSession = Depends(get_db_session),
) -> AgreementService:
    """FastAPI dependency — build AgreementService with injected dependencies."""
    return AgreementService(
        session=session,
        agreement_repo=AgreementRepositoryImpl(session),
        vendor_repo=VendorRepositoryImpl(session),
        product_repo=ProductRepositoryImpl(session),
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
            status_code=status.HTTP_409_CONFLICT, detail=exc.detail
        )
    if isinstance(exc, MasterNotFoundError):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)
        )
    raise exc  # pragma: no cover - defensive: unknown master error


async def _build_document_input(
    file: UploadFile | None,
) -> AgreementDocumentInput | None:
    """Adapt an uploaded file to the service's document input.

    Reads the file to determine its size (bytes) and reports the declared
    content type so the service can enforce the type/size rules (Req 11.9). The
    uploaded file name is recorded as the storage reference placeholder; the
    actual object-store upload is wired by a later task.
    """
    if file is None:
        return None
    contents = await file.read()
    return AgreementDocumentInput(
        content_type=file.content_type or "",
        size_bytes=len(contents),
        storage_ref=file.filename,
    )


@router.get(
    "",
    response_model=PaginatedResponse[AgreementResponse],
    summary="List agreements (paginated, optional vendor filter)",
    dependencies=[Depends(require_api_permission(_RESOURCE, "READ"))],
)
async def list_agreements(
    skip: int = Query(0, ge=0),
    limit: int = Query(20, ge=1, le=1000),
    vendor_id: UUID | None = Query(default=None),
    service: AgreementService = Depends(_get_agreement_service),
) -> PaginatedResponse[AgreementResponse]:
    """GET /api/v1/agreements — ``vendor_id`` scopes results to one Vendor (Req 11.10)."""
    items, total = await service.list_agreements(
        skip=skip, limit=limit, vendor_id=vendor_id
    )
    return PaginatedResponse[AgreementResponse](
        items=[
            AgreementResponse.from_entity(entity, vendor_name, child_code, product_name)
            for entity, vendor_name, child_code, product_name in items
        ],
        total=total,
        skip=skip,
        limit=limit,
    )


@router.post(
    "",
    response_model=AgreementResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create an agreement",
    dependencies=[Depends(require_api_permission(_RESOURCE, "CREATE"))],
)
async def create_agreement(
    request: AgreementCreateRequest = Depends(AgreementCreateRequest.as_form),
    document: UploadFile | None = File(default=None),
    current_user: User = Depends(get_current_active_user),
    service: AgreementService = Depends(_get_agreement_service),
) -> AgreementResponse:
    """POST /api/v1/agreements (multipart/form-data)"""
    try:
        agreement = await service.create_agreement(
            AgreementCreateInput(
                vendor_id=request.vendor_id,
                product_detail_id=request.product_detail_id,
                from_date=request.from_date,
                to_date=request.to_date,
                slab_in_days=request.slab_in_days,
                reduction_percent=request.reduction_percent,
                max_commission_percent=request.max_commission_percent,
                min_commission_percent=request.min_commission_percent,
                credit_days=request.credit_days,
                document=await _build_document_input(document),
            ),
            actor=current_user,
        )
    except MasterError as exc:
        _raise_http(exc)
    return AgreementResponse.from_entity(agreement)


@router.get(
    "/{agreement_id}",
    response_model=AgreementResponse,
    summary="Get an agreement by ID",
    dependencies=[Depends(require_api_permission(_RESOURCE, "READ"))],
)
async def get_agreement(
    agreement_id: UUID,
    service: AgreementService = Depends(_get_agreement_service),
) -> AgreementResponse:
    """GET /api/v1/agreements/{agreement_id}"""
    try:
        agreement = await service.get_agreement(agreement_id)
    except MasterError as exc:
        _raise_http(exc)
    return AgreementResponse.from_entity(agreement)


@router.patch(
    "/{agreement_id}",
    response_model=AgreementResponse,
    summary="Update an agreement (partial)",
    dependencies=[Depends(require_api_permission(_RESOURCE, "UPDATE"))],
)
async def update_agreement(
    agreement_id: UUID,
    request: AgreementUpdateRequest = Depends(AgreementUpdateRequest.as_form),
    document: UploadFile | None = File(default=None),
    current_user: User = Depends(get_current_active_user),
    service: AgreementService = Depends(_get_agreement_service),
) -> AgreementResponse:
    """PATCH /api/v1/agreements/{agreement_id} (multipart) — only supplied fields apply."""
    try:
        agreement = await service.update_agreement(
            agreement_id,
            _to_update_input(request, await _build_document_input(document)),
            actor=current_user,
        )
    except MasterError as exc:
        _raise_http(exc)
    return AgreementResponse.from_entity(agreement)


@router.post(
    "/{agreement_id}/renew",
    response_model=AgreementResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Renew an agreement",
    dependencies=[Depends(require_api_permission(_RESOURCE, "CREATE"))],
)
async def renew_agreement(
    agreement_id: UUID,
    request: AgreementRenewRequest = Depends(AgreementRenewRequest.as_form),
    document: UploadFile | None = File(default=None),
    current_user: User = Depends(get_current_active_user),
    service: AgreementService = Depends(_get_agreement_service),
) -> AgreementResponse:
    """POST /api/v1/agreements/{agreement_id}/renew (multipart) — marks prior Renewed."""
    try:
        agreement = await service.renew_agreement(
            agreement_id,
            AgreementRenewalInput(
                from_date=request.from_date,
                to_date=request.to_date,
                vendor_id=request.vendor_id,
                product_detail_id=request.product_detail_id,
                slab_in_days=request.slab_in_days,
                reduction_percent=request.reduction_percent,
                max_commission_percent=request.max_commission_percent,
                min_commission_percent=request.min_commission_percent,
                credit_days=request.credit_days,
                document=await _build_document_input(document),
            ),
            actor=current_user,
        )
    except MasterError as exc:
        _raise_http(exc)
    return AgreementResponse.from_entity(agreement)


@router.delete(
    "/{agreement_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete an agreement",
    dependencies=[Depends(require_api_permission(_RESOURCE, "DELETE"))],
)
async def delete_agreement(
    agreement_id: UUID,
    current_user: User = Depends(get_current_active_user),
    service: AgreementService = Depends(_get_agreement_service),
) -> Response:
    """DELETE /api/v1/agreements/{agreement_id}"""
    try:
        await service.delete_agreement(agreement_id, actor=current_user)
        return Response(status_code=status.HTTP_204_NO_CONTENT)
    except MasterError as exc:
        _raise_http(exc)


def _to_update_input(
    request: AgreementUpdateRequest,
    document: AgreementDocumentInput | None,
) -> AgreementUpdateInput:
    """Map a partial-update request to a service ``AgreementUpdateInput``.

    A form field omitted from the request arrives as ``None`` and is mapped to
    the ``UNSET`` sentinel so the service leaves it unchanged. None of the
    Agreement scalar fields are nullable, so ``None`` unambiguously means "not
    supplied". When a document file is uploaded the new reference is applied;
    when none is uploaded the existing document is left untouched (``UNSET``).
    """

    def or_unset(value: object) -> object:
        return UNSET if value is None else value

    return AgreementUpdateInput(
        vendor_id=or_unset(request.vendor_id),
        product_detail_id=or_unset(request.product_detail_id),
        from_date=or_unset(request.from_date),
        to_date=or_unset(request.to_date),
        slab_in_days=or_unset(request.slab_in_days),
        reduction_percent=or_unset(request.reduction_percent),
        max_commission_percent=or_unset(request.max_commission_percent),
        min_commission_percent=or_unset(request.min_commission_percent),
        credit_days=or_unset(request.credit_days),
        document=UNSET if document is None else document,
    )
