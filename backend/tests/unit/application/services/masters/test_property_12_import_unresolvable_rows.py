# Feature: lacm-masters, Property 12: Import rejects unresolvable rows and continues the batch.
"""Property-based test for HR-import handling of unresolvable rows.

Property 12: Import rejects unresolvable rows and continues the batch.

**Validates: Requirements 3.5**

For any batch of import rows, every row supplying neither a non-empty Company
Code nor a non-empty Entity Name is rejected with a logged row-level error, and
every other valid row in the batch is still processed.

The service is exercised end-to-end through real in-memory implementations of
``IEntityRepository`` and ``IUserRepository`` (not mocks) plus a tiny in-memory
stand-in for the SQLAlchemy session that ``UserService`` uses for its
``user_details`` look-ups. A fresh service/repository set is built per generated
example so no state leaks between examples. The async service is driven with
``asyncio.run`` because each Hypothesis example is independent.
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


# ─── In-memory fakes ───


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

    async def exists_by_name(
        self, entity_name: str, exclude_id: UUID | None = None
    ) -> bool:
        match = await self.get_by_name(entity_name)
        return match is not None and match.id != exclude_id

    async def exists_by_company_code(
        self, company_code: str, exclude_id: UUID | None = None
    ) -> bool:
        match = await self.get_by_company_code(company_code)
        return match is not None and match.id != exclude_id


class _InMemoryUserRepository(IUserRepository):
    """Minimal real ``IUserRepository`` backed by dicts."""

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
        user = self._by_id.pop(user_id, None)
        if user is not None:
            self._by_username.pop(user.username, None)

    async def list_all(self, skip: int = 0, limit: int = 100) -> list[User]:
        return list(self._by_id.values())[skip : skip + limit]

    async def get_by_email(self, email: str) -> User | None:
        return None

    async def exists_by_username(self, username: str) -> bool:
        return username in self._by_username


class _FakeResult:
    """Stand-in for a SQLAlchemy ``Result`` for the import look-up queries.

    During import the service only reads ``user_details`` to discover whether an
    Employee ID already maps to a user (and, on update, that user's details
    row). With a freshly built per-example store there are no pre-existing
    ``user_details`` rows, so every look-up legitimately resolves to ``None``
    and each valid row follows the create path.
    """

    def scalar_one_or_none(self) -> None:
        return None


class _FakeSession:
    """Tiny in-memory stand-in for the async session used by ``UserService``.

    Captures objects added during the import (the new ``user_details`` rows) and
    answers the two read queries with ``None`` so newly imported rows are
    treated as creates.
    """

    def __init__(self) -> None:
        self.added: list[object] = []

    def add(self, obj: object) -> None:
        self.added.append(obj)

    async def execute(self, _stmt: object) -> _FakeResult:
        return _FakeResult()


def _actor() -> User:
    return User(id=uuid4(), username="admin", is_active=True)


def _make_service() -> tuple[UserService, _InMemoryUserRepository, _FakeSession]:
    session = _FakeSession()
    user_repo = _InMemoryUserRepository()
    entity_repo = _InMemoryEntityRepository()
    service = UserService(
        session=session,  # type: ignore[arg-type]
        user_repo=user_repo,
        entity_repo=entity_repo,
    )
    return service, user_repo, session


# ─── Strategies ───

# Values that are empty after trimming — neither a usable Company Code nor a
# usable Entity Name (Req 3.5).
_blank = st.sampled_from([None, "", "   ", "\t", "  \n "])

# Each row is one of three shapes; ordering and mix are chosen by Hypothesis.
_ROW_KINDS = st.sampled_from(["valid_code", "valid_name", "unresolvable"])


# ``deadline=None``: each created user triggers a real (deliberately expensive)
# bcrypt password hash, so per-example wall-clock time is irrelevant to the
# property being verified.
@settings(max_examples=20, deadline=None)
@given(kinds=st.lists(_ROW_KINDS, min_size=1, max_size=10), blanks=st.data())
def test_import_rejects_unresolvable_rows_and_continues(
    kinds: list[str], blanks: st.DataObject
) -> None:
    """Unresolvable rows fail with a row-level error; valid rows still import.

    Distinct per-index identifiers are used so that valid rows never collide on
    Employee ID, User Name, Company Code, or Entity Name — isolating the single
    variable under test: whether a row supplies a resolvable entity reference.
    """
    rows: list[HrImportRow] = []
    valid_indices: list[int] = []
    invalid_indices: list[int] = []

    for position, kind in enumerate(kinds, start=1):
        employee_id = f"EMP{position}"
        if kind == "valid_code":
            rows.append(
                HrImportRow(employee_id=employee_id, company_code=f"CC{position}")
            )
            valid_indices.append(position)
        elif kind == "valid_name":
            rows.append(
                HrImportRow(employee_id=employee_id, entity_name=f"Entity {position}")
            )
            valid_indices.append(position)
        else:  # unresolvable: neither a non-empty Company Code nor Entity Name
            rows.append(
                HrImportRow(
                    employee_id=employee_id,
                    company_code=blanks.draw(_blank),
                    entity_name=blanks.draw(_blank),
                )
            )
            invalid_indices.append(position)

    service, user_repo, _session = _make_service()
    summary = asyncio.run(service.import_users(rows, _actor()))

    # The batch is fully accounted for and the breakdown is consistent.
    assert summary.received == len(rows)
    assert summary.received == summary.created + summary.updated + summary.failed

    # Every unresolvable row is rejected; every valid row is still processed.
    assert summary.failed == len(invalid_indices)
    assert summary.created == len(valid_indices)
    assert summary.updated == 0

    # Each rejection is logged as a row-level error at the right position,
    # naming the offending row by its Employee ID.
    error_positions = {err.row_number for err in summary.errors}
    assert error_positions == set(invalid_indices)
    assert len(summary.errors) == len(invalid_indices)
    for err in summary.errors:
        assert err.employee_id == f"EMP{err.row_number}"
        assert err.reason  # a non-empty, logged reason is recorded

    # Valid rows really were persisted; unresolvable rows created no user.
    for position in valid_indices:
        assert user_repo._by_username.get(f"EMP{position}") is not None
    for position in invalid_indices:
        assert user_repo._by_username.get(f"EMP{position}") is None
