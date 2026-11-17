"""
Country Application Service.
Orchestrates country master CRUD. Controllers delegate here; this layer
calls the repository and enforces master data business rules.
"""


from src.api.v1.schemas.country_schema import (
    CountryCreate,
    CountryListResponse,
    CountryResponse,
    CountryUpdate,
)
from src.domain.entities.country import Country
from src.domain.entities.user import User
from src.domain.exceptions.domain_exceptions import (
    BusinessRuleViolationError,
    DuplicateEntityError,
    EntityNotFoundError,
)
from src.domain.repositories.country_repository import ICountryRepository

ENTITY = "Country"


class CountryService:
    """
    Application service for the Country master.

    Responsibilities:
    - Enforce unique code and name
    - Block deletion while dependent records exist
    - Map domain entities to API responses
    """

    def __init__(self, country_repo: ICountryRepository) -> None:
        self._repo = country_repo

    # ─── List ───

    async def list_countries(
        self,
        skip: int = 0,
        limit: int = 100,
        search: str | None = None,
        is_active: bool | None = None,
    ) -> CountryListResponse:
        """Get a paginated page of countries plus the total match count."""
        countries = await self._repo.list_all(
            skip=skip, limit=limit, search=search, is_active=is_active
        )
        total = await self._repo.count(search=search, is_active=is_active)
        return CountryListResponse(
            countries=[self._to_response(c) for c in countries],
            total=total,
            skip=skip,
            limit=limit,
        )

    # ─── Get ───

    async def get_country(self, country_id: int) -> CountryResponse:
        """Get a single country. Raises EntityNotFoundError if missing."""
        return self._to_response(await self._require(country_id))

    # ─── Create ───

    async def create_country(
        self, request: CountryCreate, actor: User
    ) -> CountryResponse:
        """Create a country after checking code and name uniqueness."""
        if await self._repo.exists_by_code(request.code):
            raise DuplicateEntityError(ENTITY, "code", request.code)
        if await self._repo.exists_by_name(request.name):
            raise DuplicateEntityError(ENTITY, "name", request.name)

        country = Country(
            code=request.code,
            name=request.name,
            iso3_code=request.iso3_code,
            dial_code=request.dial_code,
            currency_code=request.currency_code,
            is_active=request.is_active,
            created_by=actor.username,
            modified_by=actor.username,
        )
        created = await self._repo.create(country)
        return self._to_response(created)

    # ─── Update ───

    async def update_country(
        self, country_id: int, request: CountryUpdate, actor: User
    ) -> CountryResponse:
        """Apply a partial update to a country."""
        country = await self._require(country_id)

        if request.code is not None and request.code != country.code:
            if await self._repo.exists_by_code(request.code, exclude_id=country_id):
                raise DuplicateEntityError(ENTITY, "code", request.code)
            country.code = request.code

        if request.name is not None and request.name != country.name:
            if await self._repo.exists_by_name(request.name, exclude_id=country_id):
                raise DuplicateEntityError(ENTITY, "name", request.name)
            country.name = request.name

        if request.iso3_code is not None:
            country.iso3_code = request.iso3_code
        if request.dial_code is not None:
            country.dial_code = request.dial_code
        if request.currency_code is not None:
            country.currency_code = request.currency_code
        if request.is_active is not None:
            country.is_active = request.is_active

        country.mark_modified(actor.username)
        return self._to_response(await self._repo.update(country))

    # ─── Delete ───

    async def delete_country(self, country_id: int) -> None:
        """Delete a country, refusing while states/legislations/rules reference it."""
        await self._require(country_id)
        if await self._repo.has_dependents(country_id):
            raise BusinessRuleViolationError(
                "Country is referenced by states, legislations or rules. "
                "Deactivate it instead of deleting."
            )
        await self._repo.delete(country_id)

    # ─── Internals ───

    async def _require(self, country_id: int) -> Country:
        country = await self._repo.get_by_id(country_id)
        if country is None:
            raise EntityNotFoundError(ENTITY, country_id)
        return country

    @staticmethod
    def _to_response(country: Country) -> CountryResponse:
        """Map domain entity to API response."""
        return CountryResponse.model_validate(country)
