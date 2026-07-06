# Feature: lacm-masters, Property 10: Dropdown label formatting with Unknown substitution.
"""Property-based test for Entity dropdown label formatting.

Property 10: Dropdown label formatting with Unknown substitution.

**Validates: Requirements 2.3, 2.4**

For any active Entity, ``EntityService.get_dropdown`` formats its display label
as ``"{short_code} - {entity_name}"`` (Requirement 2.3), substituting the
literal ``Unknown`` for whichever of Short Code / Entity Name is null, empty, or
whitespace-only (Requirement 2.4).

The service is exercised end-to-end through a real in-memory implementation of
``IEntityRepository`` (not a mock). Entities are seeded directly into the
repository store so the formatting logic can be probed across the full input
space of Short Code / Entity Name — including the empty and whitespace-only
values that the create-time validation would otherwise reject. A fresh
service/repository pair is built per generated example so no state leaks
between examples.
"""

from __future__ import annotations

import asyncio
from uuid import UUID, uuid4

from hypothesis import given, settings
from hypothesis import strategies as st

from src.application.services.masters.entity_service import EntityService
from src.domain.entities.masters.entity import EntityEntity
from src.domain.repositories.masters.entity_repository import IEntityRepository

_SEPARATOR = " - "
_UNKNOWN = "Unknown"


class _InMemoryEntityRepository(IEntityRepository):
    """Minimal real ``IEntityRepository`` backed by a dict."""

    def __init__(self) -> None:
        self._store: dict[UUID, EntityEntity] = {}

    def seed(self, entity: EntityEntity) -> None:
        self._store[entity.id] = entity

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


def _has_value(value: str | None) -> bool:
    """Reference predicate: True for a non-empty, non-whitespace string."""
    return value is not None and value.strip() != ""


def _expected_part(value: str | None) -> str:
    """Reference: the value itself when present, else the ``Unknown`` token."""
    return value if _has_value(value) else _UNKNOWN


# A "maybe missing" string: covers null/empty/whitespace-only (the substitution
# cases) and arbitrary present text (the pass-through case).
_missing = st.sampled_from([None, "", " ", "   ", "\t", "\n", "  \t \n "])
_present = st.text(min_size=1).filter(lambda s: s.strip() != "")
_maybe_string = st.one_of(_missing, _present)

# A list of (short_code, entity_name) pairs — one active entity per pair.
_entity_fields = st.lists(
    st.tuples(_maybe_string, _maybe_string),
    min_size=0,
    max_size=30,
)


@settings(max_examples=20)
@given(fields=_entity_fields)
def test_dropdown_labels_use_short_code_name_format_with_unknown(
    fields: list[tuple[str | None, str | None]],
) -> None:
    """Each dropdown label is ``"{short} - {name}"`` with ``Unknown`` for
    missing parts (Req 2.3, 2.4)."""

    async def scenario() -> tuple[dict[UUID, str], dict[UUID, str]]:
        repo = _InMemoryEntityRepository()
        service = EntityService(session=None, entity_repo=repo)  # type: ignore[arg-type]

        expected: dict[UUID, str] = {}
        for short_code, entity_name in fields:
            entity_id = uuid4()
            repo.seed(
                EntityEntity(
                    id=entity_id,
                    entity_name=entity_name if entity_name is not None else "",
                    short_code=short_code,
                    company_code=None,
                    is_active=True,
                )
            )
            expected[entity_id] = (
                f"{_expected_part(short_code)}"
                f"{_SEPARATOR}"
                f"{_expected_part(entity_name)}"
            )

        actual = {item.id: item.label for item in await service.get_dropdown()}
        return actual, expected

    actual, expected = asyncio.run(scenario())

    # Every active entity is labelled, and each label matches the required format.
    assert actual == expected
    # Sanity: the " - " separator is always present between the two parts.
    for label in actual.values():
        assert _SEPARATOR in label
