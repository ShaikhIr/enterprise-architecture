# Feature: lacm-masters, Property 7: Search returns all and only matching entities.
"""Property-based test for Entity search.

Property 7: Search returns all and only matching entities.

**Validates: Requirements 1.11**

Requirement 1.11: WHERE a list request supplies a search term of 1 to 100
characters, THE Entity_Service SHALL return only Entities whose Entity Name,
Short Code, or Company Code contains the search term using a trimmed,
case-insensitive substring match.

For any Entity dataset and any search term of 1–100 characters, the result
contains an Entity *if and only if* its Entity Name, Short Code, or Company Code
contains the term under a trimmed, case-insensitive substring match. The result
must contain **all** matching Entities (no false negatives) and **only** matching
Entities (no false positives).

The service (:class:`EntityService`) is exercised through a real in-memory
implementation of ``IEntityRepository`` (not a mock) whose ``list`` mirrors the
trimmed/case-insensitive substring semantics of the production SQLAlchemy
repository. The expected matching set is computed independently in the test body
so the assertion compares the service's output against a separately written
reference, rather than against the fake's own filter.

To isolate the search contract from create-time uniqueness rules, the dataset is
injected directly into the repository store, then read back through
``service.list_entities`` with a limit large enough to return every match.
"""

from __future__ import annotations

import asyncio
from uuid import UUID, uuid4

from hypothesis import given, settings
from hypothesis import strategies as st

from src.application.services.masters.entity_service import EntityService
from src.domain.entities.masters.entity import EntityEntity
from src.domain.repositories.masters.entity_repository import IEntityRepository


class _FakeEntityRepository(IEntityRepository):
    """In-memory ``IEntityRepository`` mirroring production search semantics.

    ``list`` applies a trimmed, case-insensitive substring match over Entity
    Name, Short Code, and Company Code — the same predicate the SQLAlchemy
    implementation expresses with ``func.lower(func.trim(col)).like('%term%')``.
    A null Short Code / Company Code never matches (SQL ``NULL LIKE`` is falsy).
    """

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

        if search is not None and search.strip():
            term = search.strip().lower()
            items = [e for e in items if self._matches(e, term)]

        if is_active is not None:
            items = [e for e in items if e.is_active == is_active]

        total = len(items)
        items.sort(key=lambda e: (e.entity_name, str(e.id)))
        return items[skip : skip + limit], total

    @staticmethod
    def _matches(entity: EntityEntity, term: str) -> bool:
        for value in (entity.entity_name, entity.short_code, entity.company_code):
            if value is not None and term in value.strip().lower():
                return True
        return False

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


# ─── Generators ───
#
# A small alphabet mixing both cases, digits, and whitespace maximises the
# chance that a generated search term is a genuine (trimmed/case-insensitive)
# substring of some field, so both the "all" and "only" sides of the iff get
# exercised rather than every example trivially returning the empty set.
_ALPHABET = "aAbB1 \t"

# Entity Name: required, non-empty after trimming, ≤ 255 chars. Prefixing a
# literal "x" guarantees a non-whitespace character without filtering.
_entity_names = st.text(alphabet=_ALPHABET, max_size=40).map(lambda s: "x" + s)
# Short Code / Company Code: optional (None) or a string up to the length cap.
_optional_codes = st.one_of(
    st.none(), st.text(alphabet=_ALPHABET, max_size=40)
)

_field_triples = st.tuples(_entity_names, _optional_codes, _optional_codes)

# Search term: 1 to 100 characters (Req 1.11).
_search_terms = st.text(alphabet=_ALPHABET, min_size=1, max_size=100)


def _expected_match(
    entity_name: str,
    short_code: str | None,
    company_code: str | None,
    search: str,
) -> bool:
    """Independent reference predicate for Requirement 1.11.

    Returns whether an Entity with these fields should be returned for ``search``
    under a trimmed, case-insensitive substring match. A whitespace-only term
    strips to empty and therefore imposes no filter (matches everything), which
    mirrors the service/repository behaviour.
    """
    term = search.strip().lower()
    if term == "":
        return True
    candidates = [
        field.strip().lower()
        for field in (entity_name, short_code, company_code)
        if field is not None
    ]
    return any(term in candidate for candidate in candidates)


@settings(max_examples=20)
@given(
    triples=st.lists(_field_triples, min_size=0, max_size=8),
    search=_search_terms,
)
def test_search_returns_all_and_only_matching_entities(
    triples: list[tuple[str, str | None, str | None]],
    search: str,
) -> None:
    """The search result equals exactly the set of entities matching the term."""

    async def scenario() -> None:
        repo = _FakeEntityRepository()
        service = EntityService(session=None, entity_repo=repo)  # type: ignore[arg-type]

        # Inject the dataset directly, recording the expected membership per id
        # using the independent reference predicate.
        expected_ids: set[UUID] = set()
        for entity_name, short_code, company_code in triples:
            entity = EntityEntity(
                id=uuid4(),
                entity_name=entity_name,
                short_code=short_code,
                company_code=company_code,
                is_active=True,
            )
            repo.seed(entity)
            if _expected_match(entity_name, short_code, company_code, search):
                expected_ids.add(entity.id)

        # A limit at least as large as the dataset guarantees every match is
        # returned, so the page is the full matching set (not a truncated slice).
        items, total = await service.list_entities(
            skip=0, limit=len(triples) + 1, search=search
        )
        returned_ids = {e.id for e in items}

        # All and only matching entities: the returned set equals the expected
        # set exactly (no false negatives, no false positives).
        assert returned_ids == expected_ids
        # The total count reflects the full matching set.
        assert total == len(expected_ids)

    asyncio.run(scenario())
