"""
State Application Service.
Orchestrates state master CRUD and validates the parent country reference.
"""

from uuid import UUID, uuid4

from src.api.v1.schemas.state_schema import (
    StateCreate,
    StateListResponse,
    StateResponse,
    StateUpdate,
)
from src.domain.entities.state import State
from src.domain.entities.user import User
from src.domain.exceptions.domain_exceptions import (
    BusinessRuleViolationError,
    DuplicateEntityError,
    EntityNotFoundError,
)
from src.domain.repositories.country_repository import ICountryRepository
from src.domain.repositories.state_repository import IStateRepository

ENTITY = "State"


class StateService:
    """
    Application service for the State master.

    Responsibilities:
    - Validate the parent country exists
    - Enforce unique code globally and unique name within a country
    - Block deletion while dependent records exist
    """

    def __init__(
        self, state_repo: IStateRepository, country_repo: ICountryRepository
    ) -> None:
        self._repo = state_repo
        self._country_repo = country_repo

    # ─── List ───

    async def list_states(
        self,
        skip: int = 0,
        limit: int = 100,
        search: str | None = None,
        is_active: bool | None = None,
        country_id: UUID | None = None,
    ) -> StateListResponse:
        """Get a paginated page of states, optionally filtered by country."""
        states = await self._repo.list_all(
            skip=skip,
            limit=limit,
            search=search,
            is_active=is_active,
            country_id=country_id,
        )
        total = await self._repo.count(
            search=search, is_active=is_active, country_id=country_id
        )
        return StateListResponse(
            states=[self._to_response(s) for s in states],
            total=total,
            skip=skip,
            limit=limit,
        )

    # ─── Get ───

    async def get_state(self, state_id: UUID) -> StateResponse:
        """Get a single state. Raises EntityNotFoundError if missing."""
        return self._to_response(await self._require(state_id))

    # ─── Create ───

    async def create_state(self, request: StateCreate, actor: User) -> StateResponse:
        """Create a state under an existing country."""
        await self._require_country(request.country_id)

        if await self._repo.exists_by_code(request.code):
            raise DuplicateEntityError(ENTITY, "code", request.code)
        if await self._repo.exists_by_name(request.name, request.country_id):
            raise DuplicateEntityError(ENTITY, "name", request.name)

        state = State(
            id=uuid4(),
            code=request.code,
            name=request.name,
            country_id=request.country_id,
            is_union_territory=request.is_union_territory,
            is_active=request.is_active,
            created_by=actor.username,
            modified_by=actor.username,
        )
        created = await self._repo.create(state)
        return self._to_response(created)

    # ─── Update ───

    async def update_state(
        self, state_id: UUID, request: StateUpdate, actor: User
    ) -> StateResponse:
        """Apply a partial update to a state."""
        state = await self._require(state_id)

        country_changed = False
        if request.country_id is not None and request.country_id != state.country_id:
            await self._require_country(request.country_id)
            state.country_id = request.country_id
            country_changed = True

        if request.code is not None and request.code != state.code:
            if await self._repo.exists_by_code(request.code, exclude_id=state_id):
                raise DuplicateEntityError(ENTITY, "code", request.code)
            state.code = request.code

        if request.name is not None and request.name != state.name:
            if await self._repo.exists_by_name(
                request.name, state.country_id, exclude_id=state_id
            ):
                raise DuplicateEntityError(ENTITY, "name", request.name)
            state.name = request.name
        elif country_changed:
            # Country changed but the name itself was not: the existing name
            # must still be unique within the new country.
            if await self._repo.exists_by_name(
                state.name, state.country_id, exclude_id=state_id
            ):
                raise DuplicateEntityError(ENTITY, "name", state.name)

        if request.is_union_territory is not None:
            state.is_union_territory = request.is_union_territory
        if request.is_active is not None:
            state.is_active = request.is_active

        state.mark_modified(actor.username)
        return self._to_response(await self._repo.update(state))

    # ─── Delete ───

    async def delete_state(self, state_id: UUID) -> None:
        """Delete a state, refusing while categories/legislations/rules reference it."""
        await self._require(state_id)
        if await self._repo.has_dependents(state_id):
            raise BusinessRuleViolationError(
                "State is referenced by categories of law, legislations or rules. "
                "Deactivate it instead of deleting."
            )
        await self._repo.delete(state_id)

    # ─── Internals ───

    async def _require(self, state_id: UUID) -> State:
        state = await self._repo.get_by_id(state_id)
        if state is None:
            raise EntityNotFoundError(ENTITY, state_id)
        return state

    async def _require_country(self, country_id: UUID) -> None:
        if await self._country_repo.get_by_id(country_id) is None:
            raise EntityNotFoundError("Country", country_id)

    @staticmethod
    def _to_response(state: State) -> StateResponse:
        """Map domain entity to API response."""
        return StateResponse.model_validate(state)
