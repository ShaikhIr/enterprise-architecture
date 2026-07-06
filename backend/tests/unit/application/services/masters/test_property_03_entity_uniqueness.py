# Feature: lacm-masters, Property 3: Entity name/company-code uniqueness is trimmed and case-insensitive.
"""Property-based test for Entity uniqueness.

Property 3: Entity name/company-code uniqueness is trimmed and case-insensitive.

**Validates: Requirements 1.3, 1.4**

For any persisted Entity, a subsequent create whose Entity Name (or Company
Code) equals the existing value *after trimming surrounding whitespace and
case-folding* is rejected with a conflict error, and no second record is
stored. This pins down Requirements 1.3 (duplicate Entity Name) and 1.4
(duplicate Company Code).

The service (:class:`EntityService`) is exercised through a real in-memory
implementation of ``IEntityRepository`` (not a mock), so the trimmed,
case-insensitive comparison is validated end-to-end through the port.
"""

from __future__ import annotations

import asyncio
import string
from uuid import UUID, uuid4

from hypothesis import assume, given, settings
from hypothesis import strategies as st

from src.application.exceptions.application_exceptions import MasterConflictError
from src.application.services.masters.entity_service import (
    EntityCreateInput,
    EntityService,
)
from src.domain.entities.masters.entity import EntityEntity
from src.domain.entities.user import User
from src.domain.repositories.masters.entity_repository import IEntityRepository


class FakeEntityRepository(IEntityRepository):
    """In-memory IEntityRepository performing trimmed, case-insensitive matching."""

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

    @property
    def count(self) -> int:
        return len(self._store)


# ─── Generators ───

# ASCII letters/digits only: no internal whitespace (so a stripped value is
# never empty) and ``.lower()`` round-trips cleanly without Unicode case-folding
# surprises (e.g. German "ß", Turkish dotless "i").
_CORE_ALPHABET = string.ascii_letters + string.digits


def _normalize(value: str) -> str:
    return value.strip().lower()


@st.composite
def _present(draw: st.DrawFn, core: str) -> str:
    """Render ``core`` with random surrounding whitespace and per-letter casing.

    Every rendering normalizes (trim + case-fold) back to ``core.lower()``, so
    two independent renderings of the same core are duplicates under the
    Requirement 1.3/1.4 comparison while differing in raw bytes.
    """
    chars = [
        ch.upper() if (ch.isalpha() and draw(st.booleans())) else ch.lower()
        for ch in core
    ]
    pad_left = " " * draw(st.integers(min_value=0, max_value=3))
    pad_right = " " * draw(st.integers(min_value=0, max_value=3))
    return f"{pad_left}{''.join(chars)}{pad_right}"


_core = st.text(alphabet=_CORE_ALPHABET, min_size=1, max_size=20)


def _actor() -> User:
    return User(id=uuid4(), username="admin", is_active=True)


@settings(max_examples=20)
@given(
    dup_field=st.sampled_from(["name", "company"]),
    name_core=_core,
    company_core=_core,
    other_core=_core,
    first_name_present=st.data(),
)
def test_entity_uniqueness_is_trimmed_and_case_insensitive(
    dup_field: str,
    name_core: str,
    company_core: str,
    other_core: str,
    first_name_present: st.DataObject,
) -> None:
    """A create duplicating an existing name/company-code (modulo trim+case) conflicts.

    The first Entity is persisted with a name and company code. A second create
    duplicates exactly one of those fields using a differently cased and padded
    rendering, while keeping the *other* field distinct so the conflict is
    attributable to the field under test. The second create MUST raise
    :class:`MasterConflictError` and leave the store with a single record.
    """
    # The unrelated field of the second entity must not itself collide.
    assume(_normalize(other_core) != _normalize(name_core))
    assume(_normalize(other_core) != _normalize(company_core))

    draw = first_name_present.draw

    first_name = draw(_present(name_core))
    first_company = draw(_present(company_core))

    if dup_field == "name":
        second_name = draw(_present(name_core))  # duplicate (normalizes equal)
        second_company = draw(_present(other_core))  # distinct
    else:
        second_name = draw(_present(other_core))  # distinct
        second_company = draw(_present(company_core))  # duplicate

    async def scenario() -> None:
        repo = FakeEntityRepository()
        service = EntityService(session=None, entity_repo=repo)  # type: ignore[arg-type]
        actor = _actor()

        await service.create_entity(
            EntityCreateInput(
                entity_name=first_name,
                short_code=None,
                company_code=first_company,
            ),
            actor,
        )
        assert repo.count == 1

        try:
            await service.create_entity(
                EntityCreateInput(
                    entity_name=second_name,
                    short_code=None,
                    company_code=second_company,
                ),
                actor,
            )
        except MasterConflictError:
            pass
        else:
            raise AssertionError(
                f"Duplicate {dup_field} was not rejected "
                f"(first=({first_name!r},{first_company!r}), "
                f"second=({second_name!r},{second_company!r}))"
            )

        # No second record was stored.
        assert repo.count == 1

    asyncio.run(scenario())
