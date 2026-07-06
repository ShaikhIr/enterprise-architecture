"""
Unit tests for :class:`EntityService`.

These exercise the service's business rules against a lightweight in-memory
fake repository (a real implementation of ``IEntityRepository``, not a mock),
so the tests validate actual service logic end-to-end through the port.
"""

from __future__ import annotations

from uuid import UUID, uuid4

import pytest

from src.application.exceptions.application_exceptions import (
    MasterConflictError,
    MasterNotFoundError,
    MasterValidationError,
)
from src.application.services.masters.entity_service import (
    EntityCreateInput,
    EntityService,
    EntityUpdateInput,
)
from src.domain.entities.masters.entity import EntityEntity
from src.domain.entities.user import User
from src.domain.repositories.masters.entity_repository import IEntityRepository


class FakeEntityRepository(IEntityRepository):
    """In-memory IEntityRepository for unit testing the service."""

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

            def matches(e: EntityEntity) -> bool:
                fields = [e.entity_name, e.short_code, e.company_code]
                return any(
                    f is not None and term in f.strip().lower() for f in fields
                )

            items = [e for e in items if matches(e)]

        if is_active is not None:
            items = [e for e in items if e.is_active == is_active]

        items.sort(key=lambda e: (e.entity_name, str(e.id)))
        total = len(items)
        return items[skip : skip + limit], total

    async def list_active(self) -> list[EntityEntity]:
        active = [e for e in self._store.values() if e.is_active]
        active.sort(key=lambda e: (e.entity_name, str(e.id)))
        return active

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


@pytest.fixture
def repo() -> FakeEntityRepository:
    return FakeEntityRepository()


@pytest.fixture
def service(repo: FakeEntityRepository) -> EntityService:
    # The session is unused by the in-memory repository path.
    return EntityService(session=None, entity_repo=repo)  # type: ignore[arg-type]


@pytest.fixture
def actor() -> User:
    return User(id=uuid4(), username="admin", is_active=True)


def _valid_input(**overrides: object) -> EntityCreateInput:
    base: dict[str, object] = {
        "entity_name": "Emcure Pharmaceuticals Ltd",
        "short_code": "EMC",
        "company_code": "EMC001",
    }
    base.update(overrides)
    return EntityCreateInput(**base)  # type: ignore[arg-type]


# ─── Create: defaults & persistence (Req 1.5) ───


async def test_create_defaults_is_active_true(
    service: EntityService, actor: User
) -> None:
    created = await service.create_entity(_valid_input(), actor)
    assert created.is_active is True
    assert created.entity_name == "Emcure Pharmaceuticals Ltd"
    assert created.created_by == "admin"


async def test_create_respects_explicit_is_active_false(
    service: EntityService, actor: User
) -> None:
    created = await service.create_entity(
        _valid_input(is_active=False), actor
    )
    assert created.is_active is False


# ─── Create: validation (Req 1.2) ───


@pytest.mark.parametrize("name", ["", "   ", None])
async def test_create_rejects_missing_name(
    service: EntityService, actor: User, name: object
) -> None:
    with pytest.raises(MasterValidationError) as exc:
        await service.create_entity(_valid_input(entity_name=name), actor)
    assert exc.value.field == "entity_name"


async def test_create_rejects_long_name(
    service: EntityService, actor: User
) -> None:
    with pytest.raises(MasterValidationError) as exc:
        await service.create_entity(_valid_input(entity_name="x" * 256), actor)
    assert exc.value.field == "entity_name"


async def test_create_rejects_long_short_code(
    service: EntityService, actor: User
) -> None:
    with pytest.raises(MasterValidationError) as exc:
        await service.create_entity(_valid_input(short_code="x" * 51), actor)
    assert exc.value.field == "short_code"


async def test_create_rejects_long_company_code(
    service: EntityService, actor: User
) -> None:
    with pytest.raises(MasterValidationError) as exc:
        await service.create_entity(_valid_input(company_code="x" * 51), actor)
    assert exc.value.field == "company_code"


# ─── Create: uniqueness, trimmed + case-insensitive (Req 1.3, 1.4) ───


async def test_create_rejects_duplicate_name_case_insensitive(
    service: EntityService, actor: User
) -> None:
    await service.create_entity(_valid_input(), actor)
    with pytest.raises(MasterConflictError):
        await service.create_entity(
            _valid_input(
                entity_name="  emcure pharmaceuticals ltd  ",
                company_code="OTHER",
            ),
            actor,
        )


async def test_create_rejects_duplicate_company_code_case_insensitive(
    service: EntityService, actor: User
) -> None:
    await service.create_entity(_valid_input(), actor)
    with pytest.raises(MasterConflictError):
        await service.create_entity(
            _valid_input(entity_name="Different Co", company_code="  emc001 "),
            actor,
        )


# ─── Read / not-found (Req 1.6, 1.7) ───


async def test_get_existing_returns_entity(
    service: EntityService, actor: User
) -> None:
    created = await service.create_entity(_valid_input(), actor)
    fetched = await service.get_entity(created.id)
    assert fetched.id == created.id


async def test_get_unknown_raises_not_found(service: EntityService) -> None:
    with pytest.raises(MasterNotFoundError):
        await service.get_entity(uuid4())


# ─── Update (partial, Req 1.7, 1.8) ───


async def test_update_partial_preserves_unsupplied_fields(
    service: EntityService, actor: User
) -> None:
    created = await service.create_entity(_valid_input(), actor)
    updated = await service.update_entity(
        created.id, EntityUpdateInput(short_code="EMCURE"), actor
    )
    assert updated.short_code == "EMCURE"
    # Unsupplied fields preserved.
    assert updated.entity_name == "Emcure Pharmaceuticals Ltd"
    assert updated.company_code == "EMC001"
    assert updated.is_active is True


async def test_update_unknown_raises_not_found(
    service: EntityService, actor: User
) -> None:
    with pytest.raises(MasterNotFoundError):
        await service.update_entity(
            uuid4(), EntityUpdateInput(entity_name="X"), actor
        )


async def test_update_duplicate_name_conflict(
    service: EntityService, actor: User
) -> None:
    await service.create_entity(_valid_input(), actor)
    second = await service.create_entity(
        _valid_input(entity_name="Second Co", company_code="SEC001"), actor
    )
    with pytest.raises(MasterConflictError):
        await service.update_entity(
            second.id,
            EntityUpdateInput(entity_name="Emcure Pharmaceuticals Ltd"),
            actor,
        )


async def test_update_same_name_allowed(
    service: EntityService, actor: User
) -> None:
    created = await service.create_entity(_valid_input(), actor)
    updated = await service.update_entity(
        created.id,
        EntityUpdateInput(entity_name="Emcure Pharmaceuticals Ltd"),
        actor,
    )
    assert updated.entity_name == "Emcure Pharmaceuticals Ltd"


async def test_update_clears_nullable_company_code(
    service: EntityService, actor: User
) -> None:
    created = await service.create_entity(_valid_input(), actor)
    updated = await service.update_entity(
        created.id, EntityUpdateInput(company_code=None), actor
    )
    assert updated.company_code is None


# ─── List / pagination, search, active filter (Req 1.9, 1.11, 1.12) ───


async def test_list_returns_slice_and_total(
    service: EntityService, actor: User
) -> None:
    for i in range(5):
        await service.create_entity(
            _valid_input(
                entity_name=f"Entity {i}", company_code=f"C{i:03d}"
            ),
            actor,
        )
    items, total = await service.list_entities(skip=1, limit=2)
    assert total == 5
    assert len(items) == 2
    assert [e.entity_name for e in items] == ["Entity 1", "Entity 2"]


async def test_list_search_matches_trimmed_case_insensitive(
    service: EntityService, actor: User
) -> None:
    await service.create_entity(
        _valid_input(entity_name="Alpha Corp", company_code="ALP"), actor
    )
    await service.create_entity(
        _valid_input(entity_name="Beta Corp", company_code="BET"), actor
    )
    items, total = await service.list_entities(search="  ALPHA ")
    assert total == 1
    assert items[0].entity_name == "Alpha Corp"


async def test_list_active_filter_is_exact(
    service: EntityService, actor: User
) -> None:
    await service.create_entity(
        _valid_input(entity_name="Active Co", company_code="ACT"), actor
    )
    await service.create_entity(
        _valid_input(
            entity_name="Inactive Co", company_code="INA", is_active=False
        ),
        actor,
    )
    active_items, active_total = await service.list_entities(is_active=True)
    assert active_total == 1
    assert active_items[0].entity_name == "Active Co"

    inactive_items, inactive_total = await service.list_entities(is_active=False)
    assert inactive_total == 1
    assert inactive_items[0].entity_name == "Inactive Co"


# ─── Dropdown (Req 2.1, 2.2, 2.3, 2.4) ───


async def test_dropdown_contains_only_active(
    service: EntityService, actor: User
) -> None:
    await service.create_entity(
        _valid_input(entity_name="Active Co", short_code="ACT", company_code="A1"),
        actor,
    )
    await service.create_entity(
        _valid_input(
            entity_name="Inactive Co",
            short_code="INA",
            company_code="I1",
            is_active=False,
        ),
        actor,
    )
    items = await service.get_dropdown()
    assert len(items) == 1
    assert items[0].label == "ACT - Active Co"


async def test_dropdown_empty_when_no_active(
    service: EntityService, actor: User
) -> None:
    await service.create_entity(
        _valid_input(is_active=False), actor
    )
    assert await service.get_dropdown() == []


async def test_dropdown_label_substitutes_unknown_for_missing_short_code(
    service: EntityService, actor: User
) -> None:
    await service.create_entity(
        _valid_input(
            entity_name="No Short Code Co", short_code="   ", company_code="N1"
        ),
        actor,
    )
    items = await service.get_dropdown()
    assert items[0].label == "Unknown - No Short Code Co"
