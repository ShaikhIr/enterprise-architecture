# Feature: lacm-masters, Property 4: Partial update preserves unsupplied fields.
"""Property-based test for Entity partial update.

Property 4: Partial update preserves unsupplied fields.

**Validates: Requirements 1.8**

Requirement 1.8: WHEN a request to update an existing Entity is received, THE
Entity_Service SHALL apply only the supplied fields, SHALL leave all unsupplied
fields unchanged, and SHALL preserve the Entity Name and Company Code uniqueness
constraints.

For any persisted Entity and any partial update patch, the fields present in the
patch take their new values while every field absent from the patch is left
unchanged. The patch is driven through :class:`EntityUpdateInput`, whose ``UNSET``
sentinel marks "field not supplied" — distinct from an explicit ``None`` that
clears a nullable field.

The service is exercised through a real in-memory implementation of
``IEntityRepository`` (not a mock), so the partial-update logic is validated
end-to-end through the port. Each Hypothesis example drives the async service via
``asyncio.run`` against a fresh repository holding a single Entity, which keeps
name/company-code uniqueness trivially satisfied so the property isolates the
"preserve unsupplied fields" behaviour.
"""

from __future__ import annotations

import asyncio
from uuid import UUID, uuid4

from hypothesis import given, settings
from hypothesis import strategies as st

from src.application.services.masters.entity_service import (
    UNSET,
    EntityCreateInput,
    EntityService,
    EntityUpdateInput,
)
from src.domain.entities.masters.entity import EntityEntity
from src.domain.entities.user import User
from src.domain.repositories.masters.entity_repository import IEntityRepository


class _FakeEntityRepository(IEntityRepository):
    """In-memory ``IEntityRepository`` for property testing the service."""

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


# ─── Smart generators constrained to the valid input space (Req 1.2) ───

# Entity Name: required, non-empty/non-whitespace, ≤ 255 chars. Prefixing a
# literal "x" guarantees a non-whitespace first character without filtering.
_entity_names = st.text(max_size=254).map(lambda s: "x" + s)

# Short Code / Company Code: optional, ≤ 50 chars when supplied (None clears).
_optional_codes = st.one_of(st.none(), st.text(max_size=50))


def _build_patch(
    *,
    set_name: bool,
    name_value: str,
    set_short: bool,
    short_value: str | None,
    set_company: bool,
    company_value: str | None,
    set_active: bool,
    active_value: bool,
) -> EntityUpdateInput:
    """Construct a patch supplying only the flagged fields (others stay UNSET)."""
    return EntityUpdateInput(
        entity_name=name_value if set_name else UNSET,
        short_code=short_value if set_short else UNSET,
        company_code=company_value if set_company else UNSET,
        is_active=active_value if set_active else UNSET,
    )


@settings(max_examples=20)
@given(
    initial_name=_entity_names,
    initial_short=_optional_codes,
    initial_company=_optional_codes,
    initial_active=st.booleans(),
    set_name=st.booleans(),
    name_value=_entity_names,
    set_short=st.booleans(),
    short_value=_optional_codes,
    set_company=st.booleans(),
    company_value=_optional_codes,
    set_active=st.booleans(),
    active_value=st.booleans(),
)
def test_partial_update_preserves_unsupplied_fields(
    initial_name: str,
    initial_short: str | None,
    initial_company: str | None,
    initial_active: bool,
    set_name: bool,
    name_value: str,
    set_short: bool,
    short_value: str | None,
    set_company: bool,
    company_value: str | None,
    set_active: bool,
    active_value: bool,
) -> None:
    """Supplied patch fields change; every unsupplied field is preserved."""

    async def scenario() -> None:
        repo = _FakeEntityRepository()
        service = EntityService(session=None, entity_repo=repo)  # type: ignore[arg-type]
        actor = User(id=uuid4(), username="admin", is_active=True)

        created = await service.create_entity(
            EntityCreateInput(
                entity_name=initial_name,
                short_code=initial_short,
                company_code=initial_company,
                is_active=initial_active,
            ),
            actor,
        )

        # Snapshot the persisted state before the partial update.
        before = {
            "entity_name": created.entity_name,
            "short_code": created.short_code,
            "company_code": created.company_code,
            "is_active": created.is_active,
        }

        patch = _build_patch(
            set_name=set_name,
            name_value=name_value,
            set_short=set_short,
            short_value=short_value,
            set_company=set_company,
            company_value=company_value,
            set_active=set_active,
            active_value=active_value,
        )

        updated = await service.update_entity(created.id, patch, actor)

        # Expected: supplied fields take the patch value; unsupplied preserved.
        expected = {
            "entity_name": name_value if set_name else before["entity_name"],
            "short_code": short_value if set_short else before["short_code"],
            "company_code": (
                company_value if set_company else before["company_code"]
            ),
            "is_active": active_value if set_active else before["is_active"],
        }

        assert updated.entity_name == expected["entity_name"]
        assert updated.short_code == expected["short_code"]
        assert updated.company_code == expected["company_code"]
        assert updated.is_active == expected["is_active"]

        # The same identity is updated in place, not replaced.
        assert updated.id == created.id

        # The persisted record reflects exactly the same state.
        persisted = await service.get_entity(created.id)
        assert persisted.entity_name == expected["entity_name"]
        assert persisted.short_code == expected["short_code"]
        assert persisted.company_code == expected["company_code"]
        assert persisted.is_active == expected["is_active"]

    asyncio.run(scenario())
