# Feature: lacm-masters, Property 2: Entity required-field and length validation.
"""Property-based test for Entity required-field and length validation.

Property 2: Entity required-field and length validation.

**Validates: Requirements 1.2**

For any create- or update-Entity request whose Entity Name is missing, empty,
or whitespace-only, or whose Entity Name exceeds 255 characters, Short Code
exceeds 50 characters, or Company Code exceeds 50 characters, the
:class:`EntityService` rejects the request with a
:class:`MasterValidationError` identifying the offending field and persists /
modifies no record.

The service is exercised against a real in-memory implementation of
``IEntityRepository`` (a fake, not a mock), so the property validates the actual
service logic end-to-end through the port. Each Hypothesis example drives the
async service via ``asyncio.run`` so examples remain isolated.
"""

from __future__ import annotations

import asyncio
import string
from dataclasses import replace
from uuid import UUID, uuid4

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from src.application.exceptions.application_exceptions import MasterValidationError
from src.application.services.masters.entity_service import (
    EntityCreateInput,
    EntityService,
    EntityUpdateInput,
)
from src.domain.entities.masters.entity import EntityEntity
from src.domain.entities.user import User
from src.domain.repositories.masters.entity_repository import IEntityRepository

# Per Requirement 1.2 the field length ceilings under test.
_MAX_ENTITY_NAME_LEN = 255
_MAX_SHORT_CODE_LEN = 50
_MAX_COMPANY_CODE_LEN = 50


class FakeEntityRepository(IEntityRepository):
    """In-memory ``IEntityRepository`` for testing the service in isolation."""

    def __init__(self) -> None:
        self._store: dict[UUID, EntityEntity] = {}

    async def get_by_id(self, entity_id: UUID) -> EntityEntity | None:
        return self._store.get(entity_id)

    async def create(self, entity: EntityEntity) -> EntityEntity:
        self._store[entity.id] = entity
        return entity

    async def update(self, entity: EntityEntity) -> EntityEntity:
        self._store[entity.id] = entity
        return entity

    async def delete(self, entity_id: UUID) -> None:
        self._store.pop(entity_id, None)

    async def list(
        self,
        skip: int = 0,
        limit: int = 20,
        search: str | None = None,
        is_active: bool | None = None,
    ) -> tuple[list[EntityEntity], int]:
        items = list(self._store.values())
        return items[skip : skip + limit], len(items)

    async def list_active(self) -> list[EntityEntity]:
        return [e for e in self._store.values() if e.is_active]

    async def get_by_name(self, entity_name: str) -> EntityEntity | None:
        target = entity_name.strip().lower()
        for e in self._store.values():
            if e.entity_name.strip().lower() == target:
                return e
        return None

    async def get_by_company_code(self, company_code: str) -> EntityEntity | None:
        target = company_code.strip().lower()
        for e in self._store.values():
            if e.company_code and e.company_code.strip().lower() == target:
                return e
        return None

    async def exists_by_name(
        self, entity_name: str, exclude_id: UUID | None = None
    ) -> bool:
        target = entity_name.strip().lower()
        return any(
            e.entity_name.strip().lower() == target and e.id != exclude_id
            for e in self._store.values()
        )

    async def exists_by_company_code(
        self, company_code: str, exclude_id: UUID | None = None
    ) -> bool:
        target = company_code.strip().lower()
        return any(
            e.company_code is not None
            and e.company_code.strip().lower() == target
            and e.id != exclude_id
            for e in self._store.values()
        )


def _actor() -> User:
    return User(id=uuid4(), username="tester", is_active=True)


# ─── Strategies ───

# Valid baseline values comfortably within every length limit, used for the
# fields that are NOT the subject of a given example so that the rejection is
# attributable to exactly one field.
_VALID_NAME = "Valid Entity Name"
_VALID_SHORT_CODE = "VSC"
_VALID_COMPANY_CODE = "VC001"

_non_whitespace = st.text(
    alphabet=string.ascii_letters + string.digits, min_size=1
)


def _too_long(min_len: int) -> st.SearchStrategy[str]:
    """Strings strictly longer than ``min_len - 1`` (i.e. length ≥ ``min_len``)."""
    return st.text(
        alphabet=string.ascii_letters + string.digits,
        min_size=min_len,
        max_size=min_len + 40,
    )


# Missing / empty / whitespace-only Entity Name values (Requirement 1.2).
_blank_names = st.one_of(
    st.none(),
    st.just(""),
    st.text(alphabet=" \t\n\r\f\v", min_size=1, max_size=8),
)


@st.composite
def invalid_field_cases(draw: st.DrawFn) -> tuple[str, object]:
    """Produce ``(field, invalid_value)`` for exactly one invalid field.

    Covers every rejection trigger named in Requirement 1.2:
      * ``entity_name`` missing/empty/whitespace-only, or longer than 255 chars,
      * ``short_code`` longer than 50 chars,
      * ``company_code`` longer than 50 chars.
    """
    field = draw(st.sampled_from(["entity_name", "short_code", "company_code"]))
    if field == "entity_name":
        invalid = draw(
            st.one_of(_blank_names, _too_long(_MAX_ENTITY_NAME_LEN + 1))
        )
    elif field == "short_code":
        invalid = draw(_too_long(_MAX_SHORT_CODE_LEN + 1))
    else:
        invalid = draw(_too_long(_MAX_COMPANY_CODE_LEN + 1))
    return field, invalid


def _create_input(field: str, invalid: object) -> EntityCreateInput:
    """Build a create payload with ``field`` invalid and all others valid."""
    name: object = _VALID_NAME
    short: object = _VALID_SHORT_CODE
    company: object = _VALID_COMPANY_CODE
    if field == "entity_name":
        name = invalid
    elif field == "short_code":
        short = invalid
    else:
        company = invalid
    return EntityCreateInput(
        entity_name=name,  # type: ignore[arg-type]
        short_code=short,  # type: ignore[arg-type]
        company_code=company,  # type: ignore[arg-type]
    )


def _update_patch(field: str, invalid: object) -> EntityUpdateInput:
    """Build a partial-update patch supplying only the invalid ``field``."""
    if field == "entity_name":
        return EntityUpdateInput(entity_name=invalid)  # type: ignore[arg-type]
    if field == "short_code":
        return EntityUpdateInput(short_code=invalid)  # type: ignore[arg-type]
    return EntityUpdateInput(company_code=invalid)  # type: ignore[arg-type]


async def _assert_create_rejected(field: str, invalid: object) -> None:
    repo = FakeEntityRepository()
    service = EntityService(session=None, entity_repo=repo)  # type: ignore[arg-type]

    with pytest.raises(MasterValidationError) as exc:
        await service.create_entity(_create_input(field, invalid), _actor())

    # The error names the offending field...
    assert exc.value.field == field
    # ...and nothing was persisted.
    assert repo._store == {}


async def _assert_update_rejected(field: str, invalid: object) -> None:
    repo = FakeEntityRepository()
    service = EntityService(session=None, entity_repo=repo)  # type: ignore[arg-type]

    # Seed a single valid Entity to attempt to (illegally) modify.
    seeded = await service.create_entity(
        EntityCreateInput(
            entity_name=_VALID_NAME,
            short_code=_VALID_SHORT_CODE,
            company_code=_VALID_COMPANY_CODE,
        ),
        _actor(),
    )
    snapshot = replace(seeded)

    with pytest.raises(MasterValidationError) as exc:
        await service.update_entity(seeded.id, _update_patch(field, invalid), _actor())

    # The error names the offending field...
    assert exc.value.field == field
    # ...and the stored record is untouched.
    assert len(repo._store) == 1
    stored = repo._store[seeded.id]
    assert stored.entity_name == snapshot.entity_name
    assert stored.short_code == snapshot.short_code
    assert stored.company_code == snapshot.company_code
    assert stored.is_active == snapshot.is_active


@settings(max_examples=20)
@given(case=invalid_field_cases())
def test_entity_required_field_and_length_validation(
    case: tuple[str, object],
) -> None:
    """Invalid required-field / length inputs are rejected and persist nothing.

    For both the create and the partial-update paths, an input that violates a
    Requirement 1.2 rule on exactly one field must raise a
    ``MasterValidationError`` identifying that field and must leave the store
    unchanged (no create persisted; no existing record modified).
    """
    field, invalid = case
    asyncio.run(_assert_create_rejected(field, invalid))
    asyncio.run(_assert_update_rejected(field, invalid))
