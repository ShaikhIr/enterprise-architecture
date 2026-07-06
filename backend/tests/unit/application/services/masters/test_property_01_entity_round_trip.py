# Feature: lacm-masters, Property 1: Entity create/read round-trip with defaults.
"""Property-based test for the Entity create/read round-trip.

Property 1: Entity create/read round-trip with defaults.

**Validates: Requirements 1.5, 1.6**

For any valid Entity input (a unique, trimmed/case-insensitive Entity Name and,
where supplied, a unique Company Code), creating the Entity and then reading it
back returns a record whose supplied fields equal the input and whose
``is_active`` is ``true`` (Requirement 1.5 — default active on create;
Requirement 1.6 — read-by-id returns the stored record).

The service is exercised end-to-end through a real in-memory implementation of
``IEntityRepository`` (not a mock). A fresh service/repository pair is built per
generated example so that single-create uniqueness always holds and no state
leaks between examples. The async service is driven with ``asyncio.run`` because
each Hypothesis example is independent.
"""

from __future__ import annotations

import asyncio
from uuid import UUID, uuid4

from hypothesis import given, settings
from hypothesis import strategies as st

from src.application.services.masters.entity_service import (
    EntityCreateInput,
    EntityService,
)
from src.domain.entities.masters.entity import EntityEntity
from src.domain.entities.user import User
from src.domain.repositories.masters.entity_repository import IEntityRepository

_MAX_ENTITY_NAME_LEN = 255
_MAX_CODE_LEN = 50


class _InMemoryEntityRepository(IEntityRepository):
    """Minimal real ``IEntityRepository`` backed by a dict, for the round-trip."""

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
        total = len(items)
        return items[skip : skip + limit], total

    async def list_active(self) -> list[EntityEntity]:
        return [e for e in self._store.values() if e.is_active]

    async def get_by_name(self, entity_name: str) -> EntityEntity | None:
        target = entity_name.strip().lower()
        return next(
            (e for e in self._store.values()
             if e.entity_name.strip().lower() == target),
            None,
        )

    async def get_by_company_code(self, company_code: str) -> EntityEntity | None:
        target = company_code.strip().lower()
        return next(
            (e for e in self._store.values()
             if e.company_code and e.company_code.strip().lower() == target),
            None,
        )

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


# A valid Entity Name: non-empty/whitespace after trimming, within the length cap.
_entity_names = st.text(min_size=1, max_size=_MAX_ENTITY_NAME_LEN).filter(
    lambda s: s.strip() != ""
)
# Optional codes: absent (None) or any string up to the length cap (incl. empty).
_optional_codes = st.none() | st.text(max_size=_MAX_CODE_LEN)


@settings(max_examples=20)
@given(
    entity_name=_entity_names,
    short_code=_optional_codes,
    company_code=_optional_codes,
)
def test_entity_create_read_round_trip_defaults_active(
    entity_name: str,
    short_code: str | None,
    company_code: str | None,
) -> None:
    """Creating then reading an Entity preserves supplied fields and defaults active.

    The input omits ``is_active`` so the service must apply the default of
    ``true`` (Req 1.5). Reading the created Entity by id must return the stored
    record (Req 1.6) with each supplied field equal to the input.
    """

    async def scenario() -> EntityEntity:
        repo = _InMemoryEntityRepository()
        service = EntityService(session=None, entity_repo=repo)  # type: ignore[arg-type]
        actor = User(id=uuid4(), username="admin", is_active=True)

        created = await service.create_entity(
            EntityCreateInput(
                entity_name=entity_name,
                short_code=short_code,
                company_code=company_code,
            ),
            actor,
        )
        # Read it back by its generated id (Req 1.6).
        return await service.get_entity(created.id)

    fetched = asyncio.run(scenario())

    # Supplied fields round-trip exactly.
    assert fetched.entity_name == entity_name
    assert fetched.short_code == short_code
    assert fetched.company_code == company_code
    # is_active defaults to true on create (Req 1.5).
    assert fetched.is_active is True
