# Feature: lacm-masters, Property 13: Import upsert is keyed by Employee ID.
"""Property-based test for HR-import upsert keying.

Property 13: Import upsert is keyed by Employee ID.

**Validates: Requirements 3.6**

For any batch of import rows, a row whose Employee ID does not match an
existing user creates a user and a row whose Employee ID matches updates that
user; importing the same batch twice updates rather than duplicating users.

The service is exercised end-to-end through real in-memory stand-ins (not
mocks): an ``IUserRepository`` backed by dicts, an ``IEntityRepository`` backed
by a dict, and a minimal ``AsyncSession`` stand-in that stores ``user_details``
rows and answers the exact two ``select`` statements ``UserService`` issues
during import (``user_id`` by ``employee_id`` and the details row by
``user_id``). A fresh trio is built per generated example so no state leaks
between examples; the async service is driven with ``asyncio.run``.
"""

from __future__ import annotations

import asyncio
from uuid import UUID, uuid4

from hypothesis import given, settings
from hypothesis import strategies as st

from src.api.v1.schemas.user_request import HrImportRow
from src.application.services.user_service import UserService
from src.domain.entities.masters.entity import EntityEntity
from src.domain.entities.user import User
from src.domain.repositories.masters.entity_repository import IEntityRepository
from src.domain.repositories.user_repository import IUserRepository
from src.infrastructure.database.models.user_details_model import UserDetailsModel


# ─── In-memory IUserRepository (real implementation, not a mock) ───

class _InMemoryUserRepository(IUserRepository):
    def __init__(self) -> None:
        self._by_id: dict[UUID, User] = {}
        self._by_username: dict[str, User] = {}

    async def get_by_id(self, user_id: UUID) -> User | None:
        return self._by_id.get(user_id)

    async def get_by_username(self, username: str) -> User | None:
        return self._by_username.get(username)

    async def create(self, user: User) -> User:
        self._by_id[user.id] = user
        self._by_username[user.username] = user
        return user

    async def update(self, user: User) -> User:
        self._by_id[user.id] = user
        self._by_username[user.username] = user
        return user

    async def delete(self, user_id: UUID) -> None:
        removed = self._by_id.pop(user_id, None)
        if removed is not None:
            self._by_username.pop(removed.username, None)

    async def list_all(self, skip: int = 0, limit: int = 100) -> list[User]:
        return list(self._by_id.values())[skip : skip + limit]

    async def get_by_email(self, email: str) -> User | None:
        return None

    async def exists_by_username(self, username: str) -> bool:
        return username in self._by_username


# ─── In-memory IEntityRepository (real implementation, not a mock) ───

class _InMemoryEntityRepository(IEntityRepository):
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

    async def list(self, skip=0, limit=20, search=None, is_active=None):
        items = list(self._store.values())
        return items[skip : skip + limit], len(items)

    async def list_active(self) -> list[EntityEntity]:
        return [e for e in self._store.values() if e.is_active]

    async def get_by_name(self, entity_name: str) -> EntityEntity | None:
        target = entity_name.strip().lower()
        return next(
            (e for e in self._store.values()
             if (e.entity_name or "").strip().lower() == target),
            None,
        )

    async def get_by_company_code(self, company_code: str) -> EntityEntity | None:
        target = company_code.strip().lower()
        return next(
            (e for e in self._store.values()
             if e.company_code and e.company_code.strip().lower() == target),
            None,
        )

    async def exists_by_name(self, entity_name, exclude_id=None) -> bool:
        match = await self.get_by_name(entity_name)
        return match is not None and match.id != exclude_id

    async def exists_by_company_code(self, company_code, exclude_id=None) -> bool:
        match = await self.get_by_company_code(company_code)
        return match is not None and match.id != exclude_id


# ─── Minimal AsyncSession stand-in for the user_details access used by import ───

class _FakeResult:
    def __init__(self, value: object) -> None:
        self._value = value

    def scalar_one_or_none(self) -> object:
        return self._value


class _FakeSession:
    """Stores ``user_details`` rows and answers the two import-time selects.

    ``UserService`` only touches the session during import via:
      * ``session.add(details)`` — append a row, and
      * ``select(UserDetailsModel.user_id).where(employee_id == ...)`` and
        ``select(UserDetailsModel).where(user_id == ...)`` — looked up here by
        inspecting the WHERE column and bound value.
    """

    def __init__(self) -> None:
        self.user_details: list[UserDetailsModel] = []

    def add(self, obj: object) -> None:
        if isinstance(obj, UserDetailsModel):
            self.user_details.append(obj)

    async def execute(self, stmt):  # type: ignore[no-untyped-def]
        where = stmt.whereclause
        column = getattr(where.left, "name", getattr(where.left, "key", None))
        value = where.right.value

        if column == "employee_id":
            match = next(
                (d for d in self.user_details if d.employee_id == value), None
            )
            return _FakeResult(match.user_id if match is not None else None)

        if column == "user_id":
            match = next(
                (d for d in self.user_details if str(d.user_id) == str(value)), None
            )
            return _FakeResult(match)

        raise AssertionError(f"Unexpected query column in import path: {column!r}")


# ─── Generators ───

# Employee IDs drawn from a small pool so batches naturally contain duplicates,
# exercising the "second occurrence updates the same user" keying within a batch.
_emp_ids = st.sampled_from([f"E{i}" for i in range(6)])
# Every row supplies a non-empty Company Code so the Entity always resolves and
# no row is rejected — isolating the upsert-keying behaviour under test.
_company_codes = st.sampled_from(["ACME", "GLOBEX", "INITECH", "UMBRELLA"])

_rows = st.builds(
    HrImportRow,
    employee_id=_emp_ids,
    company_code=_company_codes,
    is_validate_ad=st.booleans(),
)
_batches = st.lists(_rows, min_size=1, max_size=12)


def _make_service() -> tuple[UserService, _InMemoryUserRepository, _FakeSession]:
    session = _FakeSession()
    user_repo = _InMemoryUserRepository()
    entity_repo = _InMemoryEntityRepository()
    service = UserService(session=session, user_repo=user_repo, entity_repo=entity_repo)
    return service, user_repo, session


# ``deadline=None``: creating users hashes a bcrypt password (deliberately slow),
# so per-example wall-clock time is irrelevant to the keying property under test.
@settings(max_examples=20, deadline=None)
@given(rows=_batches)
def test_import_upsert_is_keyed_by_employee_id(rows: list[HrImportRow]) -> None:
    """Imports key on Employee ID: new IDs create, seen IDs update, no dupes."""
    distinct_emp_ids = {(r.employee_id or "").strip() for r in rows}
    distinct_count = len(distinct_emp_ids)
    actor = User(id=uuid4(), username="admin")

    async def scenario():
        service, user_repo, session = _make_service()
        first = await service.import_users(rows, actor)
        users_after_first = len(user_repo._by_id)
        details_after_first = [d.employee_id for d in session.user_details]
        second = await service.import_users(rows, actor)
        return (
            first,
            second,
            users_after_first,
            details_after_first,
            len(user_repo._by_id),
            [d.employee_id for d in session.user_details],
        )

    (
        first,
        second,
        users_after_first,
        details_after_first,
        users_after_second,
        details_after_second,
    ) = asyncio.run(scenario())

    # ── First import: each distinct Employee ID creates exactly once; every
    #    repeated occurrence updates that same user. All rows resolve, none fail.
    assert first.received == len(rows)
    assert first.failed == 0
    assert first.created == distinct_count
    assert first.updated == len(rows) - distinct_count

    # One user (and one details row) per distinct Employee ID — no duplicates.
    assert users_after_first == distinct_count
    assert sorted(set(details_after_first)) == sorted(distinct_emp_ids)
    assert len(details_after_first) == distinct_count

    # ── Second import of the same batch: every row now matches an existing
    #    Employee ID, so all rows update and nothing is created or duplicated.
    assert second.received == len(rows)
    assert second.failed == 0
    assert second.created == 0
    assert second.updated == len(rows)

    assert users_after_second == distinct_count
    assert len(details_after_second) == distinct_count
    assert sorted(set(details_after_second)) == sorted(distinct_emp_ids)
