"""
Country master API endpoints.
Thin controller — delegates all business logic to CountryService.
"""


from fastapi import APIRouter, Depends, Query, status

from src.api.v1.dependencies import get_country_repository, get_current_active_user
from src.api.v1.schemas.country_schema import (
    CountryCreate,
    CountryListResponse,
    CountryResponse,
    CountryUpdate,
)
from src.application.services.country_service import CountryService
from src.domain.entities.user import User
from src.domain.repositories.country_repository import ICountryRepository
from src.infrastructure.security.permission_manager import require_api_permission

router = APIRouter(prefix="/masters/countries", tags=["Masters - Countries"])

RESOURCE = "countries"


def _get_country_service(
    country_repo: ICountryRepository = Depends(get_country_repository),
) -> CountryService:
    """FastAPI dependency — creates CountryService with injected dependencies."""
    return CountryService(country_repo=country_repo)


@router.get(
    "",
    response_model=CountryListResponse,
    summary="List countries",
    dependencies=[Depends(require_api_permission(RESOURCE, "READ"))],
)
async def list_countries(
    skip: int = Query(default=0, ge=0),
    limit: int = Query(default=100, ge=1, le=500),
    search: str | None = Query(default=None, description="Match code, name or ISO3"),
    is_active: bool | None = Query(default=None),
    service: CountryService = Depends(_get_country_service),
) -> CountryListResponse:
    """GET /api/v1/masters/countries"""
    return await service.list_countries(
        skip=skip, limit=limit, search=search, is_active=is_active
    )


@router.post(
    "",
    response_model=CountryResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create a country",
    dependencies=[Depends(require_api_permission(RESOURCE, "CREATE"))],
)
async def create_country(
    request: CountryCreate,
    current_user: User = Depends(get_current_active_user),
    service: CountryService = Depends(_get_country_service),
) -> CountryResponse:
    """POST /api/v1/masters/countries"""
    return await service.create_country(request=request, actor=current_user)


@router.get(
    "/{country_id}",
    response_model=CountryResponse,
    summary="Get country by ID",
    dependencies=[Depends(require_api_permission(RESOURCE, "READ"))],
)
async def get_country(
    country_id: int,
    service: CountryService = Depends(_get_country_service),
) -> CountryResponse:
    """GET /api/v1/masters/countries/{country_id}"""
    return await service.get_country(country_id)


@router.patch(
    "/{country_id}",
    response_model=CountryResponse,
    summary="Update a country",
    dependencies=[Depends(require_api_permission(RESOURCE, "UPDATE"))],
)
async def update_country(
    country_id: int,
    request: CountryUpdate,
    current_user: User = Depends(get_current_active_user),
    service: CountryService = Depends(_get_country_service),
) -> CountryResponse:
    """PATCH /api/v1/masters/countries/{country_id}"""
    return await service.update_country(
        country_id=country_id, request=request, actor=current_user
    )


@router.delete(
    "/{country_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete a country",
    dependencies=[Depends(require_api_permission(RESOURCE, "DELETE"))],
)
async def delete_country(
    country_id: int,
    service: CountryService = Depends(_get_country_service),
) -> None:
    """DELETE /api/v1/masters/countries/{country_id}"""
    await service.delete_country(country_id)
