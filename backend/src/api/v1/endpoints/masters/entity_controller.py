"""
Entity Master API endpoints.

Thin controller mirroring ``user_controller.py``: a ``_get_entity_service``
dependency factory, ``require_api_permission`` + ``get_current_active_user`` on
every route, pagination bounds enforced at the boundary (Req 1.9/1.10), and
master-exception-to-HTTP mapping:

* ``MasterValidationError`` -> 422 Unprocessable Entity
* ``MasterConflictError``   -> 409 Conflict
* ``MasterNotFoundError``   -> 404 Not Found
"""

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from src.api.v1.dependencies import get_current_active_user, get_entity_repository
from src.api.v1.schemas.masters.common import PaginatedResponse
from src.api.v1.schemas.masters.entity import (
    CreateEntityRequest,
    EntityDropdownItemResponse,
    EntityResponse,
    UpdateEntityRequest,
)
from src.application.exceptions.application_exceptions import (
    MasterConflictError,
    MasterError,
    MasterNotFoundError,
    MasterValidationError,
)
from src.application.services.masters.entity_service import (
    UNSET,
    EntityCreateInput,
    EntityService,
    EntityUpdateInput,
)
from src.domain.entities.user import User
from src.domain.repositories.masters.entity_repository import IEntityRepository
from src.infrastructure.database.session import get_db_session
from src.infrastructure.security.permission_manager import require_api_permission

router = APIRouter(prefix="/entities", tags=["Entity Master"])

_RESOURCE = "entities"


def _get_entity_service(
    session: AsyncSession = Depends(get_db_session),
    entity_repo: IEntityRepository = Depends(get_entity_repository),
) -> EntityService:
    """FastAPI dependency — creates EntityService with injected dependencies."""
    return EntityService(session=session, entity_repo=entity_repo)


def _to_http_exception(exc: MasterError) -> HTTPException:
    """Map a master application exception to its HTTP equivalent."""
    if isinstance(exc, MasterValidationError):
        return HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)
        )
    if isinstance(exc, MasterConflictError):
        return HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc))
    if isinstance(exc, MasterNotFoundError):
        return HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc))
    return HTTPException(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(exc)
    )


@router.get(
    "",
    response_model=PaginatedResponse[EntityResponse],
    summary="List entities with pagination, search, and active filter",
    dependencies=[Depends(require_api_permission(_RESOURCE, "READ"))],
)
async def list_entities(
    skip: int = Query(default=0, ge=0),
    limit: int = Query(default=20, ge=1, le=100),
    search: str | None = Query(default=None),
    is_active: bool | None = Query(default=None),
    service: EntityService = Depends(_get_entity_service),
) -> PaginatedResponse[EntityResponse]:
    """GET /api/v1/entities"""
    items, total = await service.list_entities(
        skip=skip, limit=limit, search=search, is_active=is_active
    )
    return PaginatedResponse[EntityResponse](
        items=[EntityResponse.from_entity(e) for e in items],
        total=total,
        skip=skip,
        limit=limit,
    )


@router.get(
    "/dropdown",
    response_model=list[EntityDropdownItemResponse],
    summary="List active entities for dropdowns",
    dependencies=[Depends(require_api_permission(_RESOURCE, "READ"))],
)
async def get_entity_dropdown(
    service: EntityService = Depends(_get_entity_service),
) -> list[EntityDropdownItemResponse]:
    """GET /api/v1/entities/dropdown"""
    items = await service.get_dropdown()
    return [EntityDropdownItemResponse.from_item(i) for i in items]


@router.post(
    "",
    response_model=EntityResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create a new entity",
    dependencies=[Depends(require_api_permission(_RESOURCE, "CREATE"))],
)
async def create_entity(
    request: CreateEntityRequest,
    current_user: User = Depends(get_current_active_user),
    service: EntityService = Depends(_get_entity_service),
) -> EntityResponse:
    """POST /api/v1/entities"""
    try:
        entity = await service.create_entity(
            data=EntityCreateInput(
                entity_name=request.entity_name,
                short_code=request.short_code,
                company_code=request.company_code,
                is_active=request.is_active,
            ),
            actor=current_user,
        )
        return EntityResponse.from_entity(entity)
    except MasterError as exc:
        raise _to_http_exception(exc)


@router.get(
    "/{entity_id}",
    response_model=EntityResponse,
    summary="Get an entity by ID",
    dependencies=[Depends(require_api_permission(_RESOURCE, "READ"))],
)
async def get_entity(
    entity_id: UUID,
    service: EntityService = Depends(_get_entity_service),
) -> EntityResponse:
    """GET /api/v1/entities/{entity_id}"""
    try:
        entity = await service.get_entity(entity_id)
        return EntityResponse.from_entity(entity)
    except MasterError as exc:
        raise _to_http_exception(exc)


@router.patch(
    "/{entity_id}",
    response_model=EntityResponse,
    summary="Partially update an entity",
    dependencies=[Depends(require_api_permission(_RESOURCE, "UPDATE"))],
)
async def update_entity(
    entity_id: UUID,
    request: UpdateEntityRequest,
    current_user: User = Depends(get_current_active_user),
    service: EntityService = Depends(_get_entity_service),
) -> EntityResponse:
    """PATCH /api/v1/entities/{entity_id}"""
    fields_set = request.model_fields_set
    patch = EntityUpdateInput(
        entity_name=request.entity_name if "entity_name" in fields_set else UNSET,
        short_code=request.short_code if "short_code" in fields_set else UNSET,
        company_code=request.company_code if "company_code" in fields_set else UNSET,
        is_active=request.is_active if "is_active" in fields_set else UNSET,
    )
    try:
        entity = await service.update_entity(
            entity_id=entity_id, patch=patch, actor=current_user
        )
        return EntityResponse.from_entity(entity)
    except MasterError as exc:
        raise _to_http_exception(exc)
