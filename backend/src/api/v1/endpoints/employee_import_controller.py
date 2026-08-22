"""
Employee Import endpoint.

Fetches employees from Darwin AD and upserts them into users + user_details.
All persistence detail lives behind `EmployeeImportService` / `IEmployeeImportWriter` —
this controller only calls Darwin, translates its error, and delegates.
"""

import logging

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from src.api.v1.dependencies import (
    get_current_active_user,
    get_employee_import_writer,
    get_password_hasher,
)
from src.application.ports.employee_import_writer import IEmployeeImportWriter
from src.application.services.employee_import_service import EmployeeImportService
from src.domain.entities.user import User
from src.domain.services.password_hasher import IPasswordHasher
from src.infrastructure.external.employee_ad.employee_ad_client import (
    EmployeeADClient,
    EmployeeADError,
)
from src.infrastructure.security.permission_manager import require_permission

router = APIRouter(prefix="/users", tags=["Users"])
logger = logging.getLogger(__name__)

_ad_client = EmployeeADClient()


class ImportEmployeesRequest(BaseModel):
    """Request body for importing employees from Darwin AD."""

    employee_ids: list[str] = Field(..., description="List of employee IDs to import")


class ImportResult(BaseModel):
    """Result for a single employee import."""

    employee_id: str
    status: str  # "created", "updated", "failed"
    message: str = ""


class ImportEmployeesResponse(BaseModel):
    """Response for the import operation."""

    total: int
    created: int
    updated: int
    failed: int
    results: list[ImportResult]


def _get_employee_import_service(
    writer: IEmployeeImportWriter = Depends(get_employee_import_writer),
    password_hasher: IPasswordHasher = Depends(get_password_hasher),
) -> EmployeeImportService:
    """FastAPI dependency — creates EmployeeImportService with injected dependencies."""
    return EmployeeImportService(writer=writer, password_hasher=password_hasher)


@router.post(
    "/import-employees",
    response_model=ImportEmployeesResponse,
    summary="Import employees from Darwin AD",
    dependencies=[Depends(require_permission("users.import"))],
)
async def import_employees(
    request: ImportEmployeesRequest,
    current_user: User = Depends(get_current_active_user),
    service: EmployeeImportService = Depends(_get_employee_import_service),
) -> ImportEmployeesResponse:
    """
    POST /api/v1/users/import-employees

    Fetch employees from Darwin AD and upsert into users + user_details.

    - New users: created with username=employee_id, password=hash(employee_id)
    - Existing users: password unchanged, user_details updated with latest Darwin data

    One employee failing does not fail the batch — see
    `EmployeeImportWriterImpl.upsert_employee` for the per-record isolation.
    """
    try:
        darwin_response = await _ad_client.get_selected_employees(request.employee_ids)
    except EmployeeADError as exc:
        raise HTTPException(status_code=502, detail=f"Darwin API error: {exc.detail}") from exc

    logger.info(
        "Darwin raw response keys: %s",
        darwin_response.keys() if isinstance(darwin_response, dict) else type(darwin_response),
    )

    result = await service.import_employees(darwin_response, actor=current_user.username)

    return ImportEmployeesResponse(
        total=result.total,
        created=result.created,
        updated=result.updated,
        failed=result.failed,
        results=[ImportResult(**r) for r in result.results],
    )
