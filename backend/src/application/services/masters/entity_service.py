"""
Entity Master application service.

Orchestrates Entity business rules — create, read, partial update, paginated
list with search and active filter, and the active-only dropdown — delegating
persistence to ``IEntityRepository``.

Design notes / decoupling
--------------------------
The design's service contract is expressed in terms of API response schemas
(``EntityResponse``, ``EntityDropdownItem``, ``PaginatedResponse``). Those
schema/controller files are owned by a sibling task, so to avoid coupling this
service to schemas that may still be in flux, the service is **Pydantic-agnostic**:

* CRUD methods accept primitive arguments / lightweight input dataclasses
  defined in this module (:class:`EntityCreateInput`, :class:`EntityUpdateInput`).
* CRUD methods return the :class:`EntityEntity` domain object.
* ``list_entities`` returns an ``(items, total)`` tuple.
* ``get_dropdown`` returns a list of :class:`EntityDropdownItem` (id + label).

The controller task adapts these to the API request/response schemas.

Partial updates use a dedicated ``UNSET`` sentinel so that "field not supplied"
is distinguished from "field explicitly set to null" — the controller populates
:class:`EntityUpdateInput` from the Pydantic request's ``model_fields_set``.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Final
from uuid import UUID, uuid4

from sqlalchemy.ext.asyncio import AsyncSession

from src.application.exceptions.application_exceptions import (
    MasterConflictError,
    MasterNotFoundError,
    MasterValidationError,
)
from src.domain.entities.masters.entity import EntityEntity
from src.domain.entities.user import User
from src.domain.repositories.masters.entity_repository import IEntityRepository

# ─── Field length limits (per Requirement 1.2) ───
_MAX_ENTITY_NAME_LEN: Final[int] = 255
_MAX_SHORT_CODE_LEN: Final[int] = 50
_MAX_COMPANY_CODE_LEN: Final[int] = 50

# ─── Dropdown formatting (per Requirements 2.3, 2.4) ───
_DROPDOWN_SEPARATOR: Final[str] = " - "
_UNKNOWN: Final[str] = "Unknown"


class _UnsetType:
    """Sentinel marking an update field that was not supplied at all.

    Distinct from ``None``, which represents an explicit request to clear a
    nullable field. Singleton: there is only ever one ``UNSET`` instance.
    """

    _instance: _UnsetType | None = None

    def __new__(cls) -> _UnsetType:
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    def __repr__(self) -> str:  # pragma: no cover - cosmetic
        return "UNSET"

    def __bool__(self) -> bool:  # pragma: no cover - guard against truthiness use
        return False


UNSET: Final[_UnsetType] = _UnsetType()


@dataclass(frozen=True)
class EntityCreateInput:
    """Validated-on-the-way-in payload for creating an Entity.

    ``is_active`` defaults to ``None`` so the service can apply the
    ``is_active=true`` default (Requirement 1.5) when the caller omits it.
    """

    entity_name: str
    short_code: str | None = None
    company_code: str | None = None
    is_active: bool | None = None


@dataclass(frozen=True)
class EntityUpdateInput:
    """Partial-update payload.

    Each field defaults to :data:`UNSET`. Only fields that differ from ``UNSET``
    are applied, leaving all unsupplied fields unchanged (Requirement 1.8). A
    field set to ``None`` (for the nullable ``short_code``/``company_code``)
    explicitly clears that value.
    """

    entity_name: str | _UnsetType = UNSET
    short_code: str | None | _UnsetType = UNSET
    company_code: str | None | _UnsetType = UNSET
    is_active: bool | _UnsetType = UNSET


@dataclass(frozen=True)
class EntityDropdownItem:
    """A single active-entity dropdown option (id + display label)."""

    id: UUID
    label: str


class EntityService:
    """Application service for Entity Master management."""

    def __init__(self, session: AsyncSession, entity_repo: IEntityRepository) -> None:
        self._session = session
        self._entity_repo = entity_repo

    # ─── Create ───

    async def create_entity(
        self, data: EntityCreateInput, actor: User
    ) -> EntityEntity:
        """Validate and persist a new Entity.

        Enforces required/length rules (Req 1.2), trimmed case-insensitive
        Entity Name and Company Code uniqueness (Req 1.3, 1.4), and defaults
        ``is_active`` to ``true`` (Req 1.5). Validation runs before any write,
        so a rejected request persists nothing.
        """
        self._validate_entity_name(data.entity_name)
        self._validate_short_code(data.short_code)
        self._validate_company_code(data.company_code)

        if await self._entity_repo.exists_by_name(data.entity_name):
            raise MasterConflictError(
                f"An Entity with name '{data.entity_name}' already exists"
            )

        if self._has_value(data.company_code):
            assert data.company_code is not None  # narrowed by _has_value
            if await self._entity_repo.exists_by_company_code(data.company_code):
                raise MasterConflictError(
                    f"An Entity with company code '{data.company_code}' "
                    "already exists"
                )

        entity = EntityEntity(
            id=uuid4(),
            entity_name=data.entity_name,
            short_code=data.short_code,
            company_code=data.company_code,
            is_active=True if data.is_active is None else data.is_active,
            created_by=actor.username,
            modified_by=actor.username,
        )
        return await self._entity_repo.create(entity)

    # ─── Read ───

    async def get_entity(self, entity_id: UUID) -> EntityEntity:
        """Return an Entity by ID or raise not-found (Req 1.6, 1.7)."""
        entity = await self._entity_repo.get_by_id(entity_id)
        if entity is None:
            raise MasterNotFoundError("Entity", entity_id)
        return entity

    # ─── Update (partial) ───

    async def update_entity(
        self, entity_id: UUID, patch: EntityUpdateInput, actor: User
    ) -> EntityEntity:
        """Apply a partial update to an existing Entity.

        Only supplied fields are changed; unsupplied fields are left untouched
        (Req 1.8). Re-validates supplied fields and preserves name/company-code
        uniqueness (excluding the record being updated). Unknown ID → not-found
        (Req 1.7).
        """
        entity = await self._entity_repo.get_by_id(entity_id)
        if entity is None:
            raise MasterNotFoundError("Entity", entity_id)

        if not isinstance(patch.entity_name, _UnsetType):
            self._validate_entity_name(patch.entity_name)
            if await self._entity_repo.exists_by_name(
                patch.entity_name, exclude_id=entity_id
            ):
                raise MasterConflictError(
                    f"An Entity with name '{patch.entity_name}' already exists"
                )
            entity.entity_name = patch.entity_name

        if not isinstance(patch.short_code, _UnsetType):
            self._validate_short_code(patch.short_code)
            entity.short_code = patch.short_code

        if not isinstance(patch.company_code, _UnsetType):
            self._validate_company_code(patch.company_code)
            if self._has_value(patch.company_code):
                assert patch.company_code is not None
                if await self._entity_repo.exists_by_company_code(
                    patch.company_code, exclude_id=entity_id
                ):
                    raise MasterConflictError(
                        f"An Entity with company code '{patch.company_code}' "
                        "already exists"
                    )
            entity.company_code = patch.company_code

        if not isinstance(patch.is_active, _UnsetType):
            entity.is_active = patch.is_active

        entity.mark_modified(actor.username)
        return await self._entity_repo.update(entity)

    # ─── List (pagination + search + active filter) ───

    async def list_entities(
        self,
        skip: int = 0,
        limit: int = 20,
        search: str | None = None,
        is_active: bool | None = None,
    ) -> tuple[list[EntityEntity], int]:
        """Return a page of Entities and the total matching count.

        Supports trimmed case-insensitive substring search over Entity Name,
        Short Code, and Company Code (Req 1.11) and an exact active-status
        filter (Req 1.12). Pagination bounds (Req 1.9/1.10) are enforced at the
        controller boundary; this method trusts the validated ``skip``/``limit``.
        """
        return await self._entity_repo.list(
            skip=skip, limit=limit, search=search, is_active=is_active
        )

    # ─── Dropdown ───

    async def get_dropdown(self) -> list[EntityDropdownItem]:
        """Return active entities formatted for a dropdown.

        Includes only ``is_active=true`` entities (Req 2.1); returns an empty
        list when none are active (Req 2.2). Each label is formatted as
        ``"{short_code} - {entity_name}"`` (Req 2.3), substituting ``Unknown``
        for any part that is null, empty, or whitespace-only (Req 2.4).
        """
        active = await self._entity_repo.list_active()
        return [
            EntityDropdownItem(id=e.id, label=self._format_label(e))
            for e in active
        ]

    # ─── Validation helpers ───

    @staticmethod
    def _has_value(value: str | None) -> bool:
        """True when ``value`` is a non-empty, non-whitespace string."""
        return value is not None and value.strip() != ""

    @staticmethod
    def _validate_entity_name(entity_name: object) -> None:
        """Entity Name: required, non-empty/whitespace, ≤ 255 chars (Req 1.2)."""
        if not isinstance(entity_name, str) or entity_name.strip() == "":
            raise MasterValidationError(
                "entity_name", "Entity Name is required and must not be empty"
            )
        if len(entity_name) > _MAX_ENTITY_NAME_LEN:
            raise MasterValidationError(
                "entity_name",
                f"Entity Name must not exceed {_MAX_ENTITY_NAME_LEN} characters",
            )

    @staticmethod
    def _validate_short_code(short_code: str | None) -> None:
        """Short Code: optional, ≤ 50 chars when supplied (Req 1.2)."""
        if short_code is not None and len(short_code) > _MAX_SHORT_CODE_LEN:
            raise MasterValidationError(
                "short_code",
                f"Short Code must not exceed {_MAX_SHORT_CODE_LEN} characters",
            )

    @staticmethod
    def _validate_company_code(company_code: str | None) -> None:
        """Company Code: optional, ≤ 50 chars when supplied (Req 1.2)."""
        if company_code is not None and len(company_code) > _MAX_COMPANY_CODE_LEN:
            raise MasterValidationError(
                "company_code",
                f"Company Code must not exceed {_MAX_COMPANY_CODE_LEN} characters",
            )

    @staticmethod
    def _format_label(entity: EntityEntity) -> str:
        """Build the dropdown label with ``Unknown`` substitution (Req 2.3, 2.4)."""
        short = (
            entity.short_code
            if EntityService._has_value(entity.short_code)
            else _UNKNOWN
        )
        name = (
            entity.entity_name
            if EntityService._has_value(entity.entity_name)
            else _UNKNOWN
        )
        return f"{short}{_DROPDOWN_SEPARATOR}{name}"
