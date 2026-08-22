"""
Rule master API endpoints.
Thin controller — delegates all business logic to RuleService.
"""

from uuid import UUID

from fastapi import APIRouter, Depends, Query, status

from src.api.v1.dependencies import (
    get_country_repository,
    get_current_active_user,
    get_legislation_repository,
    get_rule_repository,
    get_state_repository,
)
from src.api.v1.schemas.rule_schema import (
    RuleCreate,
    RuleListResponse,
    RuleResponse,
    RuleUpdate,
)
from src.application.services.rule_service import RuleService
from src.domain.entities.user import User
from src.domain.repositories.country_repository import ICountryRepository
from src.domain.repositories.legislation_repository import ILegislationRepository
from src.domain.repositories.rule_repository import IRuleRepository
from src.domain.repositories.state_repository import IStateRepository
from src.infrastructure.security.permission_manager import require_api_permission

router = APIRouter(prefix="/masters/rules", tags=["Masters - Rules"])

RESOURCE = "rules"


def _get_rule_service(
    rule_repo: IRuleRepository = Depends(get_rule_repository),
    legislation_repo: ILegislationRepository = Depends(get_legislation_repository),
    state_repo: IStateRepository = Depends(get_state_repository),
    country_repo: ICountryRepository = Depends(get_country_repository),
) -> RuleService:
    """FastAPI dependency — creates RuleService with injected dependencies."""
    return RuleService(
        rule_repo=rule_repo,
        legislation_repo=legislation_repo,
        state_repo=state_repo,
        country_repo=country_repo,
    )


@router.get(
    "",
    response_model=RuleListResponse,
    summary="List rules",
    dependencies=[Depends(require_api_permission(RESOURCE, "READ"))],
)
async def list_rules(
    skip: int = Query(default=0, ge=0),
    limit: int = Query(default=100, ge=1, le=500),
    search: str | None = Query(
        default=None, description="Match code, name or rule number"
    ),
    is_active: bool | None = Query(default=None),
    country_id: UUID | None = Query(default=None, description="Filter by country"),
    state_id: UUID | None = Query(default=None, description="Filter by state"),
    legislation_id: UUID | None = Query(
        default=None, description="Filter by legislation"
    ),
    service: RuleService = Depends(_get_rule_service),
) -> RuleListResponse:
    """GET /api/v1/masters/rules"""
    return await service.list_rules(
        skip=skip,
        limit=limit,
        search=search,
        is_active=is_active,
        country_id=country_id,
        state_id=state_id,
        legislation_id=legislation_id,
    )


@router.post(
    "",
    response_model=RuleResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create a rule",
    dependencies=[Depends(require_api_permission(RESOURCE, "CREATE"))],
)
async def create_rule(
    request: RuleCreate,
    current_user: User = Depends(get_current_active_user),
    service: RuleService = Depends(_get_rule_service),
) -> RuleResponse:
    """POST /api/v1/masters/rules"""
    return await service.create_rule(request=request, actor=current_user)


@router.get(
    "/{rule_id}",
    response_model=RuleResponse,
    summary="Get rule by ID",
    dependencies=[Depends(require_api_permission(RESOURCE, "READ"))],
)
async def get_rule(
    rule_id: UUID,
    service: RuleService = Depends(_get_rule_service),
) -> RuleResponse:
    """GET /api/v1/masters/rules/{rule_id}"""
    return await service.get_rule(rule_id)


@router.patch(
    "/{rule_id}",
    response_model=RuleResponse,
    summary="Update a rule",
    dependencies=[Depends(require_api_permission(RESOURCE, "UPDATE"))],
)
async def update_rule(
    rule_id: UUID,
    request: RuleUpdate,
    current_user: User = Depends(get_current_active_user),
    service: RuleService = Depends(_get_rule_service),
) -> RuleResponse:
    """PATCH /api/v1/masters/rules/{rule_id}"""
    return await service.update_rule(
        rule_id=rule_id, request=request, actor=current_user
    )


@router.delete(
    "/{rule_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete a rule",
    dependencies=[Depends(require_api_permission(RESOURCE, "DELETE"))],
)
async def delete_rule(
    rule_id: UUID,
    service: RuleService = Depends(_get_rule_service),
) -> None:
    """DELETE /api/v1/masters/rules/{rule_id}"""
    await service.delete_rule(rule_id)
