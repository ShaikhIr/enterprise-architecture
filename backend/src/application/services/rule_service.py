"""
Rule Application Service.
Orchestrates rule master CRUD and keeps each rule aligned with its parent
legislation's jurisdiction.
"""


from src.api.v1.schemas.rule_schema import (
    RuleCreate,
    RuleListResponse,
    RuleResponse,
    RuleUpdate,
)
from src.domain.entities.legislation import Legislation
from src.domain.entities.rule import Rule
from src.domain.entities.user import User
from src.domain.exceptions.domain_exceptions import (
    BusinessRuleViolationError,
    DuplicateEntityError,
    EntityNotFoundError,
)
from src.domain.repositories.country_repository import ICountryRepository
from src.domain.repositories.legislation_repository import ILegislationRepository
from src.domain.repositories.rule_repository import IRuleRepository
from src.domain.repositories.state_repository import IStateRepository

ENTITY = "Rule"


class RuleService:
    """
    Application service for the Rule master.

    Responsibilities:
    - Validate legislation, country and state references
    - Ensure the rule's jurisdiction matches its parent legislation
    - Enforce unique code
    """

    def __init__(
        self,
        rule_repo: IRuleRepository,
        legislation_repo: ILegislationRepository,
        state_repo: IStateRepository,
        country_repo: ICountryRepository,
    ) -> None:
        self._repo = rule_repo
        self._legislation_repo = legislation_repo
        self._state_repo = state_repo
        self._country_repo = country_repo

    # ─── List ───

    async def list_rules(
        self,
        skip: int = 0,
        limit: int = 100,
        search: str | None = None,
        is_active: bool | None = None,
        country_id: int | None = None,
        state_id: int | None = None,
        legislation_id: int | None = None,
    ) -> RuleListResponse:
        """Get a paginated page of rules with optional filters."""
        rules = await self._repo.list_all(
            skip=skip,
            limit=limit,
            search=search,
            is_active=is_active,
            country_id=country_id,
            state_id=state_id,
            legislation_id=legislation_id,
        )
        total = await self._repo.count(
            search=search,
            is_active=is_active,
            country_id=country_id,
            state_id=state_id,
            legislation_id=legislation_id,
        )
        return RuleListResponse(
            rules=[self._to_response(r) for r in rules],
            total=total,
            skip=skip,
            limit=limit,
        )

    # ─── Get ───

    async def get_rule(self, rule_id: int) -> RuleResponse:
        """Get a single rule. Raises EntityNotFoundError if missing."""
        return self._to_response(await self._require(rule_id))

    # ─── Create ───

    async def create_rule(self, request: RuleCreate, actor: User) -> RuleResponse:
        """Create a rule under an existing legislation."""
        legislation = await self._require_legislation(request.legislation_id)
        await self._require_country(request.country_id)
        await self._require_state(request.state_id)
        self._assert_matches_legislation(
            legislation, request.country_id, request.state_id
        )

        if await self._repo.exists_by_code(request.code):
            raise DuplicateEntityError(ENTITY, "code", request.code)

        rule = Rule(
            code=request.code,
            name=request.name,
            description=request.description,
            legislation_id=request.legislation_id,
            state_id=request.state_id,
            country_id=request.country_id,
            rule_number=request.rule_number,
            effective_date=request.effective_date,
            is_active=request.is_active,
            created_by=actor.username,
            modified_by=actor.username,
        )
        created = await self._repo.create(rule)
        return self._to_response(created)

    # ─── Update ───

    async def update_rule(
        self, rule_id: int, request: RuleUpdate, actor: User
    ) -> RuleResponse:
        """Apply a partial update to a rule."""
        rule = await self._require(rule_id)
        fields_set = request.model_fields_set

        if request.legislation_id is not None:
            rule.legislation_id = request.legislation_id
        if request.country_id is not None:
            await self._require_country(request.country_id)
            rule.country_id = request.country_id
        if "state_id" in fields_set:
            await self._require_state(request.state_id)
            rule.state_id = request.state_id

        legislation = await self._require_legislation(rule.legislation_id)
        self._assert_matches_legislation(legislation, rule.country_id, rule.state_id)

        if request.code is not None and request.code != rule.code:
            if await self._repo.exists_by_code(request.code, exclude_id=rule_id):
                raise DuplicateEntityError(ENTITY, "code", request.code)
            rule.code = request.code

        if request.name is not None:
            rule.name = request.name
        if request.description is not None:
            rule.description = request.description
        if request.rule_number is not None:
            rule.rule_number = request.rule_number
        if request.effective_date is not None:
            rule.effective_date = request.effective_date
        if request.is_active is not None:
            rule.is_active = request.is_active

        rule.mark_modified(actor.username)
        return self._to_response(await self._repo.update(rule))

    # ─── Delete ───

    async def delete_rule(self, rule_id: int) -> None:
        """Delete a rule."""
        await self._require(rule_id)
        await self._repo.delete(rule_id)

    # ─── Internals ───

    async def _require(self, rule_id: int) -> Rule:
        rule = await self._repo.get_by_id(rule_id)
        if rule is None:
            raise EntityNotFoundError(ENTITY, rule_id)
        return rule

    async def _require_legislation(self, legislation_id: int | None) -> Legislation:
        legislation = (
            await self._legislation_repo.get_by_id(legislation_id)
            if legislation_id
            else None
        )
        if legislation is None:
            raise EntityNotFoundError("Legislation", legislation_id)
        return legislation

    async def _require_country(self, country_id: int) -> None:
        if await self._country_repo.get_by_id(country_id) is None:
            raise EntityNotFoundError("Country", country_id)

    async def _require_state(self, state_id: int | None) -> None:
        if state_id is None:
            return
        if await self._state_repo.get_by_id(state_id) is None:
            raise EntityNotFoundError("State", state_id)

    @staticmethod
    def _assert_matches_legislation(
        legislation: Legislation,
        country_id: int | None,
        state_id: int | None,
    ) -> None:
        """A rule must sit in the same jurisdiction as its parent legislation."""
        if legislation.country_id != country_id:
            raise BusinessRuleViolationError(
                "Rule country must match the parent legislation's country"
            )
        if legislation.state_id is not None and legislation.state_id != state_id:
            raise BusinessRuleViolationError(
                "Rule state must match the parent legislation's state"
            )

    @staticmethod
    def _to_response(rule: Rule) -> RuleResponse:
        """Map domain entity to API response."""
        return RuleResponse.model_validate(rule)
