"""
Category of Law master API endpoints.
Thin controller — delegates all business logic to CategoryOfLawService.
"""

from uuid import UUID

from fastapi import APIRouter, Depends, Query, status

from src.api.v1.dependencies import (
    get_category_of_law_repository,
    get_current_active_user,
    get_state_repository,
)
from src.api.v1.schemas.category_of_law_schema import (
    CategoryOfLawCreate,
    CategoryOfLawListResponse,
    CategoryOfLawResponse,
    CategoryOfLawUpdate,
)
from src.application.services.category_of_law_service import CategoryOfLawService
from src.domain.entities.user import User
from src.domain.repositories.category_of_law_repository import ICategoryOfLawRepository
from src.domain.repositories.state_repository import IStateRepository
from src.infrastructure.security.permission_manager import require_api_permission

router = APIRouter(
    prefix="/masters/categories-of-law", tags=["Masters - Categories of Law"]
)

RESOURCE = "categories_of_law"


def _get_category_service(
    category_repo: ICategoryOfLawRepository = Depends(get_category_of_law_repository),
    state_repo: IStateRepository = Depends(get_state_repository),
) -> CategoryOfLawService:
    """FastAPI dependency — creates CategoryOfLawService with injected dependencies."""
    return CategoryOfLawService(category_repo=category_repo, state_repo=state_repo)


@router.get(
    "",
    response_model=CategoryOfLawListResponse,
    summary="List categories of law",
    dependencies=[Depends(require_api_permission(RESOURCE, "READ"))],
)
async def list_categories_of_law(
    skip: int = Query(default=0, ge=0),
    limit: int = Query(default=100, ge=1, le=500),
    search: str | None = Query(default=None, description="Match code or name"),
    is_active: bool | None = Query(default=None),
    state_id: UUID | None = Query(default=None, description="Filter by state"),
    service: CategoryOfLawService = Depends(_get_category_service),
) -> CategoryOfLawListResponse:
    """GET /api/v1/masters/categories-of-law"""
    return await service.list_categories(
        skip=skip,
        limit=limit,
        search=search,
        is_active=is_active,
        state_id=state_id,
    )


@router.post(
    "",
    response_model=CategoryOfLawResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create a category of law",
    dependencies=[Depends(require_api_permission(RESOURCE, "CREATE"))],
)
async def create_category_of_law(
    request: CategoryOfLawCreate,
    current_user: User = Depends(get_current_active_user),
    service: CategoryOfLawService = Depends(_get_category_service),
) -> CategoryOfLawResponse:
    """POST /api/v1/masters/categories-of-law"""
    return await service.create_category(request=request, actor=current_user)


@router.get(
    "/{category_of_law_id}",
    response_model=CategoryOfLawResponse,
    summary="Get category of law by ID",
    dependencies=[Depends(require_api_permission(RESOURCE, "READ"))],
)
async def get_category_of_law(
    category_of_law_id: UUID,
    service: CategoryOfLawService = Depends(_get_category_service),
) -> CategoryOfLawResponse:
    """GET /api/v1/masters/categories-of-law/{category_of_law_id}"""
    return await service.get_category(category_of_law_id)


@router.patch(
    "/{category_of_law_id}",
    response_model=CategoryOfLawResponse,
    summary="Update a category of law",
    dependencies=[Depends(require_api_permission(RESOURCE, "UPDATE"))],
)
async def update_category_of_law(
    category_of_law_id: UUID,
    request: CategoryOfLawUpdate,
    current_user: User = Depends(get_current_active_user),
    service: CategoryOfLawService = Depends(_get_category_service),
) -> CategoryOfLawResponse:
    """PATCH /api/v1/masters/categories-of-law/{category_of_law_id}"""
    return await service.update_category(
        category_id=category_of_law_id, request=request, actor=current_user
    )


@router.delete(
    "/{category_of_law_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete a category of law",
    dependencies=[Depends(require_api_permission(RESOURCE, "DELETE"))],
)
async def delete_category_of_law(
    category_of_law_id: UUID,
    service: CategoryOfLawService = Depends(_get_category_service),
) -> None:
    """DELETE /api/v1/masters/categories-of-law/{category_of_law_id}"""
    await service.delete_category(category_of_law_id)
