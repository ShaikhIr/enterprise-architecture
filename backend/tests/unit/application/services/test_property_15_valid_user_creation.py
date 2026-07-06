# Feature: lacm-masters, Property 15: Valid user creation stores fields, roles, and entity.
"""Property-based test for valid user creation.

Property 15: Valid user creation stores fields, roles, and entity.

**Validates: Requirements 4.7, 4.8, 4.9**

*For any* valid create-user request, the created user persists the supplied
Employee ID, User Name, Email, First Name, Last Name, and Entity reference
(Req 4.8); when Validate-with-AD is enabled the user is created without
requiring a password (Req 4.7); and the user's role assignments equal exactly
the supplied (possibly empty) Role set (Req 4.9).

``UserService.create_user`` is exercised end-to-end through real in-memory
implementations of its collaborators (a fake ``IUserRepository``, a fake
``IEntityRepository`` and a lightweight fake ``AsyncSession`` that answers the
two validation queries the service issues and records staged rows) rather than
mocks, so what is actually persisted — the user, its ``user_details`` row, and
its role-assignment rows — is observed against the real service logic. Each
Hypothesis example drives the async service via ``asyncio.run`` so examples
stay isolated.
"""

from __future__ import annotations

import asyncio
import string
from uuid import UUID, uuid4

from hypothesis import given, settings
from hypothesis import strategies as st

from src.api.v1.schemas.user_request import CreateUserRequest
from src.application.services.user_service import UserService
from src.domain.entities.masters.entity import EntityEntity
from src.domain.entities.user import User
from src.domain.repositories.masters.entity_repository import IEntityRepository
from src.domain.repositories.user_repository import IUserRepository
from src.infrastructure.database.models.role_model import RoleAssignmentModel, RoleModel
from src.infrastructure.database.models.user_details_model import UserDetailsModel


# ─── Fakes (no mocks) ───


class _FakeScalars:
    def __init__(self, rows: list) -> None:
        self._rows = rows

    def all(self) -> list:
        return self._rows


class _FakeResult:
    def __init__(self, rows: list) -> None:
        self._rows = rows

    def first(self):
        return (self._rows[0],) if self._rows else None

    def scalars(self) -> _FakeScalars:
        return _FakeScalars(self._rows)


class FakeSession:
    """Minimal stand-in for ``AsyncSession``.

    Answers exactly the two read queries ``UserService.create_user`` issues:
      * ``select(UserDetailsModel.id).where(employee_id == ...)`` — the
        Employee-ID uniqueness probe (here always empty: a brand-new id),
      * ``select(RoleModel.id).where(id.in_(...))`` — the role-existence probe
        (here every queried role is known so creation proceeds).
    Every ``add`` is recorded so the test can inspect the persisted user-details
    row and role-assignment rows.
    """

    def __init__(self, existing_role_ids: set[str] | None = None) -> None:
        self._role_ids = existing_role_ids or set()
        self.added: list = []

    async def execute(self, stmt):  # noqa: ANN001 - SQLAlchemy statement
        entity = stmt.column_descriptions[0]["entity"]
        params = stmt.compile().params
        if entity is UserDetailsModel:
            # Employee-ID uniqueness probe — no existing user uses this id.
            return _FakeResult([])
        if entity is RoleModel:
            queried = params.get("id_1") or []
            rows = [rid for rid in queried if str(rid) in self._role_ids]
            return _FakeResult(rows)
        raise AssertionError(f"Unexpected query against {entity!r}")

    def add(self, obj) -> None:  # noqa: ANN001
        self.added.append(obj)


class FakeUserRepository(IUserRepository):
    """In-memory ``IUserRepository`` tracking created users and usernames."""

    def __init__(self) -> None:
        self._store: dict[UUID, User] = {}
        self._usernames: set[str] = set()

    async def get_by_id(self, user_id: UUID) -> User | None:
        return self._store.get(user_id)

    async def get_by_username(self, username: str) -> User | None:
        for u in self._store.values():
            if u.username.lower() == username.lower():
                return u
        return None

    async def create(self, user: User) -> User:
        self._store[user.id] = user
        self._usernames.add(user.username.lower())
        return user

    async def update(self, user: User) -> User:
        self._store[user.id] = user
        return user

    async def delete(self, user_id: UUID) -> None:
        self._store.pop(user_id, None)

    async def list_all(self, skip: int = 0, limit: int = 100) -> list[User]:
        return list(self._store.values())[skip : skip + limit]

    async def get_by_email(self, email: str) -> User | None:
        return None

    async def exists_by_username(self, username: str) -> bool:
        return username.lower() in self._usernames


class FakeEntityRepository(IEntityRepository):
    """In-memory ``IEntityRepository`` (only ``get_by_id`` is exercised here)."""

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

    async def exists_by_name(self, entity_name, exclude_id=None) -> bool:
        match = await self.get_by_name(entity_name)
        return match is not None and match.id != exclude_id

    async def exists_by_company_code(self, company_code, exclude_id=None) -> bool:
        match = await self.get_by_company_code(company_code)
        return match is not None and match.id != exclude_id


def _actor() -> User:
    return User(id=uuid4(), username="admin", is_active=True)


# ─── Generators ───

_token = st.text(alphabet=string.ascii_letters + string.digits, min_size=1, max_size=20)
# Optional free-text fields. Whitespace-only collapses to "" once stripped, so
# the property compares against the stripped value the service stores.
_optional_text = st.one_of(
    st.none(),
    st.text(alphabet=string.ascii_letters + string.digits + " ", max_size=20),
)
# Passwords valid only when Validate-with-AD is disabled (>= 8 chars).
_valid_password = st.text(alphabet=string.printable, min_size=8, max_size=64)


# ``deadline=None``: the create path performs a (deliberately slow) bcrypt hash,
# so per-example timing is not a useful signal.
@settings(max_examples=20, deadline=None)
@given(
    employee_id=_token,
    username=_token,
    email=_optional_text,
    first_name=_optional_text,
    last_name=_optional_text,
    role_ids=st.lists(st.uuids(), unique=True, max_size=5),
    is_validate_ad=st.booleans(),
    password=_valid_password,
)
def test_valid_user_creation_persists_fields_roles_and_entity(
    employee_id: str,
    username: str,
    email: str | None,
    first_name: str | None,
    last_name: str | None,
    role_ids: list[UUID],
    is_validate_ad: bool,
    password: str,
) -> None:
    """A valid create-user request stores its fields, entity, and exact roles.

    The created user MUST carry the supplied User Name, Entity reference, and AD
    flag; the staged ``user_details`` row MUST carry the supplied Employee ID,
    Email, First Name, and Last Name (stripped); and the active role-assignment
    rows MUST cover exactly the supplied (possibly empty) Role set. When
    Validate-with-AD is enabled, creation MUST succeed with no password supplied.
    """

    active_entity = EntityEntity(
        id=uuid4(),
        entity_name="Acme",
        short_code="AC",
        company_code="ACME",
        is_active=True,
    )

    request = CreateUserRequest(
        employee_id=employee_id,
        username=username,
        email=email,
        first_name=first_name,
        last_name=last_name,
        entity_id=active_entity.id,
        role_ids=role_ids,
        is_validate_ad=is_validate_ad,
        # AD-enabled users need no password (Req 4.7); otherwise a valid one.
        password=None if is_validate_ad else password,
    )

    session = FakeSession(existing_role_ids={str(r) for r in role_ids})
    user_repo = FakeUserRepository()
    entity_repo = FakeEntityRepository([active_entity])
    service = UserService(
        session=session,  # type: ignore[arg-type]
        user_repo=user_repo,
        entity_repo=entity_repo,
    )

    async def scenario() -> None:
        response = await service.create_user(request, _actor())

        # Exactly one user persisted, and the response identifies it.
        assert len(user_repo._store) == 1, "expected exactly one created user"
        created = next(iter(user_repo._store.values()))
        assert response.id == created.id
        assert response.username == username.strip()

        # User-level fields: User Name, Entity reference, AD flag (Req 4.7, 4.8).
        assert created.username == username.strip()
        assert created.entity_id == active_entity.id
        assert created.is_validate_ad is is_validate_ad

        # The user-details row carries the supplied employee fields (Req 4.8).
        details = [o for o in session.added if isinstance(o, UserDetailsModel)]
        assert len(details) == 1, "expected exactly one user_details row"
        row = details[0]
        assert row.employee_id == employee_id.strip()
        assert row.email == (email or "").strip()
        assert row.first_name == (first_name or "").strip()
        assert row.last_name == (last_name or "").strip()

        # Active role assignments cover exactly the supplied role set (Req 4.9).
        assignments = [
            o
            for o in session.added
            if isinstance(o, RoleAssignmentModel) and o.is_active
        ]
        assigned = {UUID(str(a.role_id)) for a in assignments}
        assert assigned == set(role_ids), (
            f"role assignments {assigned} != supplied {set(role_ids)}"
        )
        # Each assignment links the created user.
        for a in assignments:
            assert UUID(str(a.user_id)) == created.id

    asyncio.run(scenario())
