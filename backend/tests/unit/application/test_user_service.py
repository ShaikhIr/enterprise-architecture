"""
Unit tests for the extended UserService logic (Requirements 3, 4, 5).

These tests exercise the input-validation and entity-resolution logic that does
not require a live database session: password rules (Req 4.4/4.7), active-Entity
validation (Req 4.5/5.3), and HR-import entity resolution/creation (Req 3.2-3.4).
DB round-trip behaviour is covered by the dedicated property tests.
"""

from __future__ import annotations

from uuid import UUID, uuid4

import pytest

from src.api.v1.schemas.user_request import (
    CreateUserRequest,
    EditUserRequest,
    HrImportRow,
)
from src.api.v1.schemas.user_response import ImportSummary
from src.application.exceptions.application_exceptions import MasterValidationError
from src.application.services.user_service import UserService
from src.domain.entities.masters.entity import EntityEntity
from src.domain.entities.user import User
from src.domain.repositories.masters.entity_repository import IEntityRepository
from src.infrastructure.security.password_encoder import verify_password


class FakeEntityRepository(IEntityRepository):
    """In-memory IEntityRepository for unit testing the service logic."""

    def __init__(self, entities: list[EntityEntity] | None = None) -> None:
        self._store: dict[UUID, EntityEntity] = {}
        for entity in entities or []:
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

    async def list(self, skip=0, limit=20, search=None, is_active=None):
        items = list(self._store.values())
        return items[skip : skip + limit], len(items)

    async def list_active(self) -> list[EntityEntity]:
        return [e for e in self._store.values() if e.is_active]

    async def get_by_name(self, entity_name: str) -> EntityEntity | None:
        target = entity_name.strip().lower()
        for e in self._store.values():
            if (e.entity_name or "").strip().lower() == target:
                return e
        return None

    async def get_by_company_code(self, company_code: str) -> EntityEntity | None:
        target = company_code.strip().lower()
        for e in self._store.values():
            if (e.company_code or "").strip().lower() == target:
                return e
        return None

    async def exists_by_name(self, entity_name: str, exclude_id=None) -> bool:
        match = await self.get_by_name(entity_name)
        return match is not None and match.id != exclude_id

    async def exists_by_company_code(self, company_code: str, exclude_id=None) -> bool:
        match = await self.get_by_company_code(company_code)
        return match is not None and match.id != exclude_id


def _actor() -> User:
    return User(id=uuid4(), username="admin")


def _make_service(entities: list[EntityEntity] | None = None) -> UserService:
    # session/user_repo are unused by the logic under test; an injected fake
    # entity repo avoids any DB access.
    return UserService(
        session=None,  # type: ignore[arg-type]
        user_repo=None,  # type: ignore[arg-type]
        entity_repo=FakeEntityRepository(entities),
    )


def _entity(*, active: bool = True, name="Acme", code="AC") -> EntityEntity:
    return EntityEntity(
        id=uuid4(), entity_name=name, short_code="AC", company_code=code, is_active=active
    )


# ─── Password rules (Req 4.4, 4.7) ───

def test_create_password_ad_enabled_yields_unusable_hash() -> None:
    svc = _make_service()
    req = CreateUserRequest(employee_id="E1", username="u1", is_validate_ad=True)
    pw_hash = svc._resolve_create_password(req)
    assert pw_hash  # a real bcrypt hash is produced
    assert not verify_password("", pw_hash)


def test_create_password_disabled_missing_password_rejected() -> None:
    svc = _make_service()
    req = CreateUserRequest(
        employee_id="E1", username="u1", is_validate_ad=False, password=None
    )
    with pytest.raises(MasterValidationError):
        svc._resolve_create_password(req)


def test_create_password_disabled_short_password_rejected() -> None:
    svc = _make_service()
    req = CreateUserRequest(
        employee_id="E1", username="u1", is_validate_ad=False, password="short7!"
    )
    with pytest.raises(MasterValidationError):
        svc._resolve_create_password(req)


def test_create_password_disabled_valid_password_hashes() -> None:
    svc = _make_service()
    req = CreateUserRequest(
        employee_id="E1", username="u1", is_validate_ad=False, password="LongEnough1"
    )
    pw_hash = svc._resolve_create_password(req)
    assert verify_password("LongEnough1", pw_hash)


# ─── Active-entity validation (Req 4.5, 5.3) ───

@pytest.mark.asyncio
async def test_validate_active_entity_none_is_allowed() -> None:
    svc = _make_service()
    await svc._validate_active_entity(None)  # no exception


@pytest.mark.asyncio
async def test_validate_active_entity_unknown_rejected() -> None:
    svc = _make_service()
    with pytest.raises(MasterValidationError):
        await svc._validate_active_entity(uuid4())


@pytest.mark.asyncio
async def test_validate_active_entity_inactive_rejected() -> None:
    inactive = _entity(active=False)
    svc = _make_service([inactive])
    with pytest.raises(MasterValidationError):
        await svc._validate_active_entity(inactive.id)


@pytest.mark.asyncio
async def test_validate_active_entity_active_ok() -> None:
    active = _entity(active=True)
    svc = _make_service([active])
    await svc._validate_active_entity(active.id)  # no exception


# ─── HR-import entity resolution (Req 3.2, 3.3, 3.4) ───

@pytest.mark.asyncio
async def test_resolve_entity_by_company_code_prefers_code() -> None:
    existing = _entity(name="Acme Ltd", code="ACME")
    svc = _make_service([existing])
    resolved = await svc._resolve_or_create_entity("ACME", "Different Name", _actor())
    assert resolved.id == existing.id


@pytest.mark.asyncio
async def test_resolve_entity_by_name_when_no_company_code() -> None:
    existing = _entity(name="Acme Ltd", code="ACME")
    svc = _make_service([existing])
    resolved = await svc._resolve_or_create_entity("", "acme ltd", _actor())
    assert resolved.id == existing.id


@pytest.mark.asyncio
async def test_resolve_entity_creates_when_absent() -> None:
    repo = FakeEntityRepository()
    svc = UserService(session=None, user_repo=None, entity_repo=repo)  # type: ignore[arg-type]
    resolved = await svc._resolve_or_create_entity("NEWCO", "New Company", _actor())
    assert resolved.entity_name == "New Company"
    assert resolved.company_code == "NEWCO"
    # the new entity is persisted in the repo (no duplicate on a second resolve)
    again = await svc._resolve_or_create_entity("NEWCO", "New Company", _actor())
    assert again.id == resolved.id


# ─── Schema shape / defaults ───

def test_create_user_request_defaults() -> None:
    req = CreateUserRequest(employee_id="E1", username="u1")
    assert req.is_validate_ad is True
    assert req.role_ids == []
    assert req.password is None


def test_edit_user_request_tracks_supplied_fields() -> None:
    req = EditUserRequest(email="a@b.com")
    assert "email" in req.model_fields_set
    assert "first_name" not in req.model_fields_set
    assert req.role_ids is None  # not supplied → roles untouched


def test_hr_import_row_minimal() -> None:
    row = HrImportRow(employee_id="E1", company_code="ACME")
    assert row.employee_id == "E1"
    assert row.is_validate_ad is True


def test_import_summary_received_equals_breakdown() -> None:
    summary = ImportSummary(received=3, created=1, updated=1, failed=1)
    assert summary.received == summary.created + summary.updated + summary.failed
