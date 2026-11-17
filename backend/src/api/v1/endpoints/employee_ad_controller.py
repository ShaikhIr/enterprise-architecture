"""
Employee AD Service endpoints.
Proxies requests to the Darwin AD integrator service.

Endpoints (matching Darwin OpenAPI spec):
  - GET  /health                — Check Darwin service reachability
  - POST /validate-credentials  — Validate employee AD credentials
  - POST /selected-employees    — Fetch employees by IDs
  - GET  /employees             — Get all employees
  - GET  /hierarchy             — Get hierarchy data

Protected: the `services.employee_ad` permission is required.
"""

from typing import Any, NoReturn

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field

from src.api.v1.dependencies import (
    get_client_ip,
    get_directory_credential_check_service,
    get_employee_ad_client,
)
from src.application.services.directory_credential_check_service import (
    DirectoryCredentialCheckService,
)
from src.application.services.login_throttle_service import LoginThrottledError
from src.infrastructure.external.employee_ad.employee_ad_client import (
    EmployeeADAuthError,
    EmployeeADClient,
    EmployeeADError,
    EmployeeADUnavailableError,
)
from src.infrastructure.security.permission_manager import require_permission

router = APIRouter(
    prefix="/services/employee-ad",
    tags=["Employee AD Service"],
    dependencies=[Depends(require_permission("services.employee_ad"))],
)


class ValidateCredentialsRequest(BaseModel):
    """Request body for credential validation."""

    employee_id: str = Field(..., description="Employee ID to validate")
    password: str = Field(..., description="Employee password")


class GetSelectedEmployeesRequest(BaseModel):
    """Request body for fetching selected employees."""

    employee_ids: list[str] = Field(..., description="List of employee IDs to fetch")


def _raise_for_darwin_error(exc: EmployeeADError) -> NoReturn:
    """Map Darwin client exceptions to HTTP responses."""
    if isinstance(exc, EmployeeADAuthError):
        raise HTTPException(status_code=401, detail=exc.detail)
    if isinstance(exc, EmployeeADUnavailableError):
        raise HTTPException(status_code=503, detail=exc.detail)
    raise HTTPException(status_code=502, detail=exc.detail)


@router.get("/health", summary="Check Employee AD service reachability")
async def check_health(
    client: EmployeeADClient = Depends(get_employee_ad_client),
) -> dict[str, Any]:
    """
    Verify whether the Darwin AD service is reachable.
    """
    result = await client.health_check()
    return {
        "service": "Employee AD (Darwin)",
        "configured": client.is_configured,
        "base_url": client.base_url,
        **result,
    }


@router.post("/validate-credentials", summary="Validate employee AD credentials")
async def validate_credentials(
    request: ValidateCredentialsRequest,
    service: DirectoryCredentialCheckService = Depends(get_directory_credential_check_service),
    client_ip: str = Depends(get_client_ip),
) -> dict[str, Any]:
    """
    POST /validatecredentials — Validate employee AD credentials via Darwin.

    Throttled like the login form (separate budget): repeated wrong guesses at one employee id
    from one address are refused with 429 before Darwin is asked, with Retry-After.
    """
    try:
        result = await service.check(
            request.employee_id, request.password, client_ip=client_ip
        )
        return {
            "is_success": result.is_success,
            "is_valid_user": result.is_valid_user,
            "raw_response": result.raw_response,
        }
    except LoginThrottledError as exc:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Too many attempts. Please try again later.",
            headers={"Retry-After": str(exc.retry_after_seconds)},
        ) from exc
    except EmployeeADError as exc:
        _raise_for_darwin_error(exc)


@router.post("/selected-employees", summary="Get selected employees by IDs")
async def get_selected_employees(
    request: GetSelectedEmployeesRequest,
    client: EmployeeADClient = Depends(get_employee_ad_client),
) -> dict[str, Any]:
    """
    POST /getselectedemployees — Fetch employee records by IDs (multipart/form-data to Darwin).
    """
    try:
        data = await client.get_selected_employees(request.employee_ids)
        return data
    except EmployeeADError as exc:
        _raise_for_darwin_error(exc)


@router.get("/employees", summary="Get all employees")
async def get_employees(
    client: EmployeeADClient = Depends(get_employee_ad_client),
) -> dict[str, Any]:
    """
    GET /getemployees — Fetch all employee records from Darwin.
    """
    try:
        data = await client.get_employees()
        return data
    except EmployeeADError as exc:
        _raise_for_darwin_error(exc)


@router.get("/hierarchy", summary="Get hierarchy data")
async def get_hierarchy_data(
    client: EmployeeADClient = Depends(get_employee_ad_client),
) -> dict[str, Any]:
    """
    GET /getHierarchyData — Fetch hierarchy data from Darwin.
    """
    try:
        data = await client.get_hierarchy_data()
        return data
    except EmployeeADError as exc:
        _raise_for_darwin_error(exc)
