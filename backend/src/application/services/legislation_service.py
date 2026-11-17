"""
Legislation Application Service.
Orchestrates legislation master CRUD and keeps the jurisdiction chain
(country -> state -> category of law) consistent.
"""


from src.api.v1.schemas.legislation_schema import (
    LegislationCreate,
    LegislationListResponse,
    LegislationResponse,
    LegislationUpdate,
)
from src.domain.entities.legislation import Legislation
from src.domain.entities.user import User
from src.domain.exceptions.domain_exceptions import (
    BusinessRuleViolationError,
    DuplicateEntityError,
    EntityNotFoundError,
)
from src.domain.repositories.category_of_law_repository import ICategoryOfLawRepository
from src.domain.repositories.country_repository import ICountryRepository
from src.domain.repositories.legislation_repository import ILegislationRepository
from src.domain.repositories.state_repository import IStateRepository

ENTITY = "Legislation"


class LegislationService:
    """
    Application service for the Legislation master.

    Responsibilities:
    - Validate country, state and category references
    - Ensure a supplied state actually belongs to the supplied country
    - Enforce unique code
    - Block deletion while rules reference the legislation
    """

    def __init__(
        self,
        legislation_repo: ILegislationRepository,
        category_repo: ICategoryOfLawRepository,
        state_repo: IStateRepository,
        country_repo: ICountryRepository,
    ) -> None:
        self._repo = legislation_repo
        self._category_repo = category_repo
        self._state_repo = state_repo
        self._country_repo = country_repo

    # ─── List ───

    async def list_legislations(
        self,
        skip: int = 0,
        limit: int = 100,
        search: str | None = None,
        is_active: bool | None = None,
        country_id: int | None = None,
        state_id: int | None = None,
        category_of_law_id: int | None = None,
    ) -> LegislationListResponse:
        """Get a paginated page of legislations with optional filters."""
        legislations = await self._repo.list_all(
            skip=skip,
            limit=limit,
            search=search,
            is_active=is_active,
            country_id=country_id,
            state_id=state_id,
            category_of_law_id=category_of_law_id,
        )
        total = await self._repo.count(
            search=search,
            is_active=is_active,
            country_id=country_id,
            state_id=state_id,
            category_of_law_id=category_of_law_id,
        )
        return LegislationListResponse(
            legislations=[self._to_response(item) for item in legislations],
            total=total,
            skip=skip,
            limit=limit,
        )

    # ─── Get ───

    async def get_legislation(self, legislation_id: int) -> LegislationResponse:
        """Get a single legislation. Raises EntityNotFoundError if missing."""
        return self._to_response(await self._require(legislation_id))

    # ─── Create ───

    async def create_legislation(
        self, request: LegislationCreate, actor: User
    ) -> LegislationResponse:
        """Create a legislation after validating its jurisdiction chain."""
        await self._require_country(request.country_id)
        await self._require_category(request.category_of_law_id)
        await self._require_state_in_country(request.state_id, request.country_id)

        if await self._repo.exists_by_code(request.code):
            raise DuplicateEntityError(ENTITY, "code", request.code)

        legislation = Legislation(
            code=request.code,
            name=request.name,
            description=request.description,
            category_of_law_id=request.category_of_law_id,
            state_id=request.state_id,
            country_id=request.country_id,
            legislation_number=request.legislation_number,
            effective_date=request.effective_date,
            is_active=request.is_active,
            created_by=actor.username,
            modified_by=actor.username,
        )
        created = await self._repo.create(legislation)
        return self._to_response(created)

    # ─── Update ───

    async def update_legislation(
        self, legislation_id: int, request: LegislationUpdate, actor: User
    ) -> LegislationResponse:
        """Apply a partial update to a legislation."""
        legislation = await self._require(legislation_id)
        fields_set = request.model_fields_set

        if request.country_id is not None:
            await self._require_country(request.country_id)
            legislation.country_id = request.country_id

        if request.category_of_law_id is not None:
            await self._require_category(request.category_of_law_id)
            legislation.category_of_law_id = request.category_of_law_id

        if "state_id" in fields_set:
            await self._require_state_in_country(
                request.state_id, legislation.country_id
            )
            legislation.state_id = request.state_id
        elif request.country_id is not None:
            # Country changed but state was not supplied: the existing state must
            # still belong to the new country.
            await self._require_state_in_country(
                legislation.state_id, legislation.country_id
            )

        if request.code is not None and request.code != legislation.code:
            if await self._repo.exists_by_code(request.code, exclude_id=legislation_id):
                raise DuplicateEntityError(ENTITY, "code", request.code)
            legislation.code = request.code

        if request.name is not None:
            legislation.name = request.name
        if request.description is not None:
            legislation.description = request.description
        if request.legislation_number is not None:
            legislation.legislation_number = request.legislation_number
        if request.effective_date is not None:
            legislation.effective_date = request.effective_date
        if request.is_active is not None:
            legislation.is_active = request.is_active

        legislation.mark_modified(actor.username)
        return self._to_response(await self._repo.update(legislation))

    # ─── Delete ───

    async def delete_legislation(self, legislation_id: int) -> None:
        """Delete a legislation, refusing while rules reference it."""
        await self._require(legislation_id)
        if await self._repo.has_dependents(legislation_id):
            raise BusinessRuleViolationError(
                "Legislation is referenced by rules. "
                "Deactivate it instead of deleting."
            )
        await self._repo.delete(legislation_id)

    # ─── Internals ───

    async def _require(self, legislation_id: int) -> Legislation:
        legislation = await self._repo.get_by_id(legislation_id)
        if legislation is None:
            raise EntityNotFoundError(ENTITY, legislation_id)
        return legislation

    async def _require_country(self, country_id: int) -> None:
        if await self._country_repo.get_by_id(country_id) is None:
            raise EntityNotFoundError("Country", country_id)

    async def _require_category(self, category_of_law_id: int) -> None:
        if await self._category_repo.get_by_id(category_of_law_id) is None:
            raise EntityNotFoundError("CategoryOfLaw", category_of_law_id)

    async def _require_state_in_country(
        self, state_id: int | None, country_id: int | None
    ) -> None:
        """A central legislation has no state; a state one must match the country."""
        if state_id is None:
            return
        state = await self._state_repo.get_by_id(state_id)
        if state is None:
            raise EntityNotFoundError("State", state_id)
        if state.country_id != country_id:
            raise BusinessRuleViolationError(
                f"State '{state.name}' does not belong to the selected country"
            )

    @staticmethod
    def _to_response(legislation: Legislation) -> LegislationResponse:
        """Map domain entity to API response."""
        return LegislationResponse.model_validate(legislation)
