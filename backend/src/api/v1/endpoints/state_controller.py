"""
State master API endpoints.
Thin controller — delegates all business logic to StateService.
"""


from fastapi import APIRouter, Depends, Query, status

from src.api.v1.dependencies import (
    get_country_repository,
    get_current_active_user,
    get_state_repository,
)
from src.api.v1.schemas.state_schema import (
    StateCreate,
    StateListResponse,
    StateResponse,
    StateUpdate,
)
from src.application.services.state_service import StateService
from src.domain.entities.user import User
from src.domain.repositories.country_repository import ICountryRepository
from src.domain.repositories.state_repository import IStateRepository
from src.infrastructure.security.permission_manager import require_api_permission

router = APIRouter(prefix="/masters/states", tags=["Masters - States"])

RESOURCE = "states"


def _get_state_service(
    state_repo: IStateRepository = Depends(get_state_repository),
    country_repo: ICountryRepository = Depends(get_country_repository),
) -> StateService:
    """FastAPI dependency — creates StateService with injected dependencies."""
    return StateService(state_repo=state_repo, country_repo=country_repo)


@router.get(
    "",
    response_model=StateListResponse,
    summary="List states",
    dependencies=[Depends(require_api_permission(RESOURCE, "READ"))],
)
async def list_states(
    skip: int = Query(default=0, ge=0),
    limit: int = Query(default=100, ge=1, le=500),
    search: str | None = Query(default=None, description="Match code or name"),
    is_active: bool | None = Query(default=None),
    country_id: int | None = Query(default=None, description="Filter by country"),
    service: StateService = Depends(_get_state_service),
) -> StateListResponse:
    """GET /api/v1/masters/states"""
    return await service.list_states(
        skip=skip,
        limit=limit,
        search=search,
        is_active=is_active,
        country_id=country_id,
    )


@router.post(
    "",
    response_model=StateResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create a state",
    dependencies=[Depends(require_api_permission(RESOURCE, "CREATE"))],
)
async def create_state(
    request: StateCreate,
    current_user: User = Depends(get_current_active_user),
    service: StateService = Depends(_get_state_service),
) -> StateResponse:
    """POST /api/v1/masters/states"""
    return await service.create_state(request=request, actor=current_user)


@router.get(
    "/{state_id}",
    response_model=StateResponse,
    summary="Get state by ID",
    dependencies=[Depends(require_api_permission(RESOURCE, "READ"))],
)
async def get_state(
    state_id: int,
    service: StateService = Depends(_get_state_service),
) -> StateResponse:
    """GET /api/v1/masters/states/{state_id}"""
    return await service.get_state(state_id)


@router.patch(
    "/{state_id}",
    response_model=StateResponse,
    summary="Update a state",
    dependencies=[Depends(require_api_permission(RESOURCE, "UPDATE"))],
)
async def update_state(
    state_id: int,
    request: StateUpdate,
    current_user: User = Depends(get_current_active_user),
    service: StateService = Depends(_get_state_service),
) -> StateResponse:
    """PATCH /api/v1/masters/states/{state_id}"""
    return await service.update_state(
        state_id=state_id, request=request, actor=current_user
    )


@router.delete(
    "/{state_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete a state",
    dependencies=[Depends(require_api_permission(RESOURCE, "DELETE"))],
)
async def delete_state(
    state_id: int,
    service: StateService = Depends(_get_state_service),
) -> None:
    """DELETE /api/v1/masters/states/{state_id}"""
    await service.delete_state(state_id)
