# Feature: lacm-masters, Property 8: Active-status filter is exact.
"""Property-based test for the Entity active-status filter.

Property 8: Active-status filter is exact.

**Validates: Requirements 1.12**

Requirement 1.12: WHERE a list request supplies an active-status filter, THE
Entity_Service SHALL return only Entities whose Is Active value matches the
filter.

For any Entity dataset and any active-status filter value, every returned Entity
has ``is_active`` equal to the filter value, and no matching Entity is omitted.
In other words, the set of Entities returned for a given filter is *exactly* the
set of stored Entities whose ``is_active`` equals the filter — neither a spurious
non-matching record nor a missing matching record is tolerated. When the filter
is ``None`` (no filter supplied) every stored Entity is returned.

The service (:class:`EntityService`) is exercised end-to-end through a real
in-memory implementation of ``IEntityRepository`` (not a mock). The in-memory
``list`` faithfully mirrors the production adapter's filter semantics
(``is_active == filter`` and trimmed/case-insensitive substring search), so the
property validates the service's contract through the port. A pagination limit
large enough to span the whole dataset is used so the filter behaviour is
isolated from pagination truncation.
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
    """In-memory ``IEntityRepository`` mirroring the adapter's filter semantics."""

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

        if search is not None and search.strip():
            term = search.strip().lower()

            def _matches(e: EntityEntity) -> bool:
                fields = (e.entity_name, e.short_code, e.company_code)
                return any(
                    f is not None and term in f.strip().lower() for f in fields
                )

            items = [e for e in items if _matches(e)]

        if is_active is not None:
            items = [e for e in items if e.is_active == is_active]

        # Deterministic ordering mirrors the adapter (name, id).
        items.sort(key=lambda e: (e.entity_name, str(e.id)))
        total = len(items)
        return items[skip : skip + limit], total

    async def list_active(self) -> list[EntityEntity]:
        return [e for e in self._store.values() if e.is_active]

    async def get_by_name(self, entity_name: str) -> EntityEntity | None:
        target = entity_name.strip().lower()
        return next(
            (
                e
                for e in self._store.values()
                if e.entity_name.strip().lower() == target
            ),
            None,
        )

    async def get_by_company_code(self, company_code: str) -> EntityEntity | None:
        target = company_code.strip().lower()
        return next(
            (
                e
                for e in self._store.values()
                if e.company_code and e.company_code.strip().lower() == target
            ),
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


def _actor() -> User:
    return User(id=uuid4(), username="admin", is_active=True)


# A dataset is modelled as a list of ``is_active`` flags; each flag becomes one
# Entity with a guaranteed-unique name so creation never trips the uniqueness
# guard. Sizes range from empty up to a modest cap to keep examples fast.
_active_flags = st.lists(st.booleans(), min_size=0, max_size=15)

# The active-status filter under test: True, False, or "no filter".
_filter_values = st.sampled_from([True, False, None])


@settings(max_examples=20)
@given(active_flags=_active_flags, filter_value=_filter_values)
def test_active_status_filter_is_exact(
    active_flags: list[bool], filter_value: bool | None
) -> None:
    """Listing with an active-status filter returns exactly the matching Entities.

    A dataset of Entities with assorted ``is_active`` values is persisted via the
    service, then listed with ``is_active=filter_value`` and a limit spanning the
    whole dataset. The returned set MUST equal the stored Entities whose
    ``is_active`` matches the filter (or the whole set when the filter is
    ``None``): every returned record matches, and no matching record is omitted.
    """

    async def scenario() -> None:
        repo = _InMemoryEntityRepository()
        service = EntityService(session=None, entity_repo=repo)  # type: ignore[arg-type]
        actor = _actor()

        # Persist one Entity per flag with a unique name to satisfy uniqueness.
        expected_active: dict[UUID, bool] = {}
        for index, is_active in enumerate(active_flags):
            created = await service.create_entity(
                EntityCreateInput(
                    entity_name=f"entity-{index}",
                    short_code=None,
                    company_code=None,
                    is_active=is_active,
                ),
                actor,
            )
            expected_active[created.id] = is_active

        # A limit large enough to span the whole dataset isolates the filter
        # from pagination truncation.
        limit = len(active_flags) + 1

        items, total = await service.list_entities(
            skip=0, limit=limit, search=None, is_active=filter_value
        )

        returned_ids = {e.id for e in items}

        # Expected matching set under the filter.
        if filter_value is None:
            expected_ids = set(expected_active)
        else:
            expected_ids = {
                eid
                for eid, active in expected_active.items()
                if active == filter_value
            }

        # Every returned Entity matches the filter (no spurious records).
        if filter_value is not None:
            assert all(e.is_active == filter_value for e in items)

        # Exactness: returned set equals the expected matching set (no omissions,
        # no extras), and the reported total agrees.
        assert returned_ids == expected_ids
        assert total == len(expected_ids)

    asyncio.run(scenario())
