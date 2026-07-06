"""
Employee Import API endpoint.
Thin controller — delegates all logic to EmployeeImportService.
"""

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from src.api.v1.dependencies import get_current_active_user
from src.application.services.employee_import_service import EmployeeImportService
from src.domain.entities.user import User
from src.infrastructure.database.session import get_db_session
from src.infrastructure.security.permission_manager import require_permission

router = APIRouter(prefix="/users", tags=["Users"])


# ─── Schemas ───


class ImportEmployeesRequest(BaseModel):
    """Request body for importing employees from Darwin AD."""

    employee_ids: list[str] = Field(..., description="List of employee IDs to import")


class ImportResultItem(BaseModel):
    """Result for a single employee import."""

    employee_id: str
    status: str
    message: str = ""


class ImportEmployeesResponse(BaseModel):
    """Response for the import operation."""

    total: int
    created: int
    updated: int
    failed: int
    results: list[ImportResultItem]


# ─── Dependency Factory ───


def _get_employee_import_service(
    session: AsyncSession = Depends(get_db_session),
) -> EmployeeImportService:
    return EmployeeImportService(session=session)


# ─── Endpoint ───


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
    """POST /api/v1/users/import-employees"""
    try:
        summary = await service.import_employees(
            employee_ids=request.employee_ids,
            actor=current_user,
        )
    except ValueError as e:
        raise HTTPException(status_code=502, detail=str(e))

    return ImportEmployeesResponse(
        total=summary.total,
        created=summary.created,
        updated=summary.updated,
        failed=summary.failed,
        results=[
            ImportResultItem(
                employee_id=r.employee_id,
                status=r.status,
                message=r.message,
            )
            for r in summary.results
        ],
    )
