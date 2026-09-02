"""
Legislation master API endpoints.
Thin controller — delegates all business logic to LegislationService.
"""


from fastapi import APIRouter, Depends, Query, status

from src.api.v1.dependencies import (
    get_category_of_law_repository,
    get_country_repository,
    get_current_active_user,
    get_legislation_repository,
    get_state_repository,
)
from src.api.v1.schemas.legislation_schema import (
    LegislationCreate,
    LegislationListResponse,
    LegislationResponse,
    LegislationUpdate,
)
from src.application.services.legislation_service import LegislationService
from src.domain.entities.user import User
from src.domain.repositories.category_of_law_repository import ICategoryOfLawRepository
from src.domain.repositories.country_repository import ICountryRepository
from src.domain.repositories.legislation_repository import ILegislationRepository
from src.domain.repositories.state_repository import IStateRepository
from src.infrastructure.security.permission_manager import require_api_permission

router = APIRouter(prefix="/masters/legislations", tags=["Masters - Legislations"])

RESOURCE = "legislations"


def _get_legislation_service(
    legislation_repo: ILegislationRepository = Depends(get_legislation_repository),
    category_repo: ICategoryOfLawRepository = Depends(get_category_of_law_repository),
    state_repo: IStateRepository = Depends(get_state_repository),
    country_repo: ICountryRepository = Depends(get_country_repository),
) -> LegislationService:
    """FastAPI dependency — creates LegislationService with injected dependencies."""
    return LegislationService(
        legislation_repo=legislation_repo,
        category_repo=category_repo,
        state_repo=state_repo,
        country_repo=country_repo,
    )


@router.get(
    "",
    response_model=LegislationListResponse,
    summary="List legislations",
    dependencies=[Depends(require_api_permission(RESOURCE, "READ"))],
)
async def list_legislations(
    skip: int = Query(default=0, ge=0),
    limit: int = Query(default=100, ge=1, le=500),
    search: str | None = Query(
        default=None, description="Match code, name or legislation number"
    ),
    is_active: bool | None = Query(default=None),
    country_id: int | None = Query(default=None, description="Filter by country"),
    state_id: int | None = Query(default=None, description="Filter by state"),
    category_of_law_id: int | None = Query(
        default=None, description="Filter by category of law"
    ),
    service: LegislationService = Depends(_get_legislation_service),
) -> LegislationListResponse:
    """GET /api/v1/masters/legislations"""
    return await service.list_legislations(
        skip=skip,
        limit=limit,
        search=search,
        is_active=is_active,
        country_id=country_id,
        state_id=state_id,
        category_of_law_id=category_of_law_id,
    )


@router.post(
    "",
    response_model=LegislationResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create a legislation",
    dependencies=[Depends(require_api_permission(RESOURCE, "CREATE"))],
)
async def create_legislation(
    request: LegislationCreate,
    current_user: User = Depends(get_current_active_user),
    service: LegislationService = Depends(_get_legislation_service),
) -> LegislationResponse:
    """POST /api/v1/masters/legislations"""
    return await service.create_legislation(request=request, actor=current_user)


@router.get(
    "/{legislation_id}",
    response_model=LegislationResponse,
    summary="Get legislation by ID",
    dependencies=[Depends(require_api_permission(RESOURCE, "READ"))],
)
async def get_legislation(
    legislation_id: int,
    service: LegislationService = Depends(_get_legislation_service),
) -> LegislationResponse:
    """GET /api/v1/masters/legislations/{legislation_id}"""
    return await service.get_legislation(legislation_id)


@router.patch(
    "/{legislation_id}",
    response_model=LegislationResponse,
    summary="Update a legislation",
    dependencies=[Depends(require_api_permission(RESOURCE, "UPDATE"))],
)
async def update_legislation(
    legislation_id: int,
    request: LegislationUpdate,
    current_user: User = Depends(get_current_active_user),
    service: LegislationService = Depends(_get_legislation_service),
) -> LegislationResponse:
    """PATCH /api/v1/masters/legislations/{legislation_id}"""
    return await service.update_legislation(
        legislation_id=legislation_id, request=request, actor=current_user
    )


@router.delete(
    "/{legislation_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete a legislation",
    dependencies=[Depends(require_api_permission(RESOURCE, "DELETE"))],
)
async def delete_legislation(
    legislation_id: int,
    service: LegislationService = Depends(_get_legislation_service),
) -> None:
    """DELETE /api/v1/masters/legislations/{legislation_id}"""
    await service.delete_legislation(legislation_id)
