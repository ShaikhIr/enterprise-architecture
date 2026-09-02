"""
Category of Law Application Service.
Orchestrates category master CRUD and validates the optional state reference.
"""


from src.api.v1.schemas.category_of_law_schema import (
    CategoryOfLawCreate,
    CategoryOfLawListResponse,
    CategoryOfLawResponse,
    CategoryOfLawUpdate,
)
from src.domain.entities.category_of_law import CategoryOfLaw
from src.domain.entities.user import User
from src.domain.exceptions.domain_exceptions import (
    BusinessRuleViolationError,
    DuplicateEntityError,
    EntityNotFoundError,
)
from src.domain.repositories.category_of_law_repository import ICategoryOfLawRepository
from src.domain.repositories.state_repository import IStateRepository

ENTITY = "CategoryOfLaw"


class CategoryOfLawService:
    """
    Application service for the CategoryOfLaw master.

    Responsibilities:
    - Validate the state reference when the category is state specific
    - Enforce unique code globally and unique name within a state scope
    - Block deletion while legislations reference the category
    """

    def __init__(
        self,
        category_repo: ICategoryOfLawRepository,
        state_repo: IStateRepository,
    ) -> None:
        self._repo = category_repo
        self._state_repo = state_repo

    # ─── List ───

    async def list_categories(
        self,
        skip: int = 0,
        limit: int = 100,
        search: str | None = None,
        is_active: bool | None = None,
        state_id: int | None = None,
    ) -> CategoryOfLawListResponse:
        """Get a paginated page of categories, optionally filtered by state."""
        categories = await self._repo.list_all(
            skip=skip,
            limit=limit,
            search=search,
            is_active=is_active,
            state_id=state_id,
        )
        total = await self._repo.count(
            search=search, is_active=is_active, state_id=state_id
        )
        return CategoryOfLawListResponse(
            categories_of_law=[self._to_response(c) for c in categories],
            total=total,
            skip=skip,
            limit=limit,
        )

    # ─── Get ───

    async def get_category(self, category_id: int) -> CategoryOfLawResponse:
        """Get a single category. Raises EntityNotFoundError if missing."""
        return self._to_response(await self._require(category_id))

    # ─── Create ───

    async def create_category(
        self, request: CategoryOfLawCreate, actor: User
    ) -> CategoryOfLawResponse:
        """Create a category of law, optionally scoped to a state."""
        if request.state_id is not None:
            await self._require_state(request.state_id)

        if await self._repo.exists_by_code(request.code):
            raise DuplicateEntityError(ENTITY, "code", request.code)
        if await self._repo.exists_by_name(request.name, request.state_id):
            raise DuplicateEntityError(ENTITY, "name", request.name)

        category = CategoryOfLaw(
            code=request.code,
            name=request.name,
            description=request.description,
            state_id=request.state_id,
            is_active=request.is_active,
            created_by=actor.username,
            modified_by=actor.username,
        )
        created = await self._repo.create(category)
        return self._to_response(created)

    # ─── Update ───

    async def update_category(
        self, category_id: int, request: CategoryOfLawUpdate, actor: User
    ) -> CategoryOfLawResponse:
        """Apply a partial update to a category of law."""
        category = await self._require(category_id)
        fields_set = request.model_fields_set

        if "state_id" in fields_set and request.state_id != category.state_id:
            if request.state_id is not None:
                await self._require_state(request.state_id)
            category.state_id = request.state_id

        if request.code is not None and request.code != category.code:
            if await self._repo.exists_by_code(request.code, exclude_id=category_id):
                raise DuplicateEntityError(ENTITY, "code", request.code)
            category.code = request.code

        if request.name is not None and request.name != category.name:
            if await self._repo.exists_by_name(
                request.name, category.state_id, exclude_id=category_id
            ):
                raise DuplicateEntityError(ENTITY, "name", request.name)
            category.name = request.name

        if request.description is not None:
            category.description = request.description
        if request.is_active is not None:
            category.is_active = request.is_active

        category.mark_modified(actor.username)
        return self._to_response(await self._repo.update(category))

    # ─── Delete ───

    async def delete_category(self, category_id: int) -> None:
        """Delete a category, refusing while legislations reference it."""
        await self._require(category_id)
        if await self._repo.has_dependents(category_id):
            raise BusinessRuleViolationError(
                "Category of law is referenced by legislations. "
                "Deactivate it instead of deleting."
            )
        await self._repo.delete(category_id)

    # ─── Internals ───

    async def _require(self, category_id: int) -> CategoryOfLaw:
        category = await self._repo.get_by_id(category_id)
        if category is None:
            raise EntityNotFoundError(ENTITY, category_id)
        return category

    async def _require_state(self, state_id: int) -> None:
        if await self._state_repo.get_by_id(state_id) is None:
            raise EntityNotFoundError("State", state_id)

    @staticmethod
    def _to_response(category: CategoryOfLaw) -> CategoryOfLawResponse:
        """Map domain entity to API response."""
        return CategoryOfLawResponse.model_validate(category)
