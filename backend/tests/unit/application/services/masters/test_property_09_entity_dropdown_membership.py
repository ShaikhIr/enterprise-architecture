# Feature: lacm-masters, Property 9: Dropdown contains exactly the active entities.
"""Property-based test for Entity dropdown membership.

Property 9: Dropdown contains exactly the active entities.

**Validates: Requirements 2.1**

For any collection of created Entities — an arbitrary mix of active and
inactive — ``EntityService.get_dropdown`` returns options for exactly the
active entities: every active entity appears exactly once, and no inactive
entity appears (Requirement 2.1 — the dropdown lists only active entities).

The service is exercised end-to-end through a real in-memory implementation of
``IEntityRepository`` (not a mock). A fresh service/repository pair is built per
generated example so no state leaks between examples. Each generated entity gets
an index-derived unique Entity Name and Company Code so that create-time
uniqueness always holds and the only varying dimension is the active flag.
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


class _InMemoryEntityRepository(IEntityRepository):
    """Minimal real ``IEntityRepository`` backed by a dict."""

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


# A list of active flags — one per entity to create. Empty list = no entities.
_active_flags = st.lists(st.booleans(), min_size=0, max_size=30)


@settings(max_examples=20)
@given(active_flags=_active_flags)
def test_dropdown_contains_exactly_active_entities(
    active_flags: list[bool],
) -> None:
    """The dropdown's ids are exactly the ids of the active entities (Req 2.1)."""

    async def scenario() -> tuple[set[UUID], set[UUID]]:
        repo = _InMemoryEntityRepository()
        service = EntityService(session=None, entity_repo=repo)  # type: ignore[arg-type]
        actor = User(id=uuid4(), username="admin", is_active=True)

        expected_active_ids: set[UUID] = set()
        for i, is_active in enumerate(active_flags):
            created = await service.create_entity(
                EntityCreateInput(
                    entity_name=f"Entity {i}",
                    short_code=f"E{i}",
                    company_code=f"C{i:04d}",
                    is_active=is_active,
                ),
                actor,
            )
            if is_active:
                expected_active_ids.add(created.id)

        dropdown_ids = {item.id for item in await service.get_dropdown()}
        return dropdown_ids, expected_active_ids

    dropdown_ids, expected_active_ids = asyncio.run(scenario())

    # The dropdown contains exactly the active entities — no more, no fewer.
    assert dropdown_ids == expected_active_ids
    # No duplicates: one option per active entity.
    assert len(dropdown_ids) == sum(1 for f in active_flags if f)
