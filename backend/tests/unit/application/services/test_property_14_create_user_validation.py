# Feature: lacm-masters, Property 14: Create-user validation.
"""Property-based test for Create-User validation.

Property 14: Create-user validation.

**Validates: Requirements 4.1, 4.2, 4.3, 4.4, 4.5, 4.6**

*For any* create-user request, the request is rejected and no user is created
when:
  * the Employee ID or User Name is missing/empty (Req 4.1),
  * the Employee ID duplicates an existing user (Req 4.2),
  * the User Name duplicates an existing user (Req 4.3),
  * Validate-with-AD is disabled and the password is absent or shorter than 8
    characters (Req 4.4),
  * the Entity reference is not an existing active Entity (Req 4.5),
  * any supplied Role does not exist (Req 4.6).

``UserService.create_user`` is exercised end-to-end through real in-memory
implementations of its collaborators (a fake ``IUserRepository``, a fake
``IEntityRepository`` and a lightweight fake ``AsyncSession`` that answers the
two validation queries the service issues) rather than mocks, so the validation
ordering and the "nothing is persisted on rejection" guarantee are validated
against the actual service logic. Each Hypothesis example drives the async
service via ``asyncio.run`` so examples stay isolated.
"""

from __future__ import annotations

import asyncio
import string
from uuid import UUID, uuid4

from hypothesis import given, settings
from hypothesis import strategies as st

from src.api.v1.schemas.user_request import CreateUserRequest
from src.application.exceptions.application_exceptions import (
    MasterConflictError,
    MasterValidationError,
)
from src.application.services.user_service import UserService
from src.domain.entities.masters.entity import EntityEntity
from src.domain.entities.user import User
from src.domain.repositories.masters.entity_repository import IEntityRepository
from src.domain.repositories.user_repository import IUserRepository
from src.infrastructure.database.models.role_model import RoleModel
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
        Employee-ID uniqueness probe (Req 4.2),
      * ``select(RoleModel.id).where(id.in_(...))`` — the role-existence probe
        (Req 4.6).
    Any ``add`` is recorded so a test can assert nothing was persisted.
    """

    def __init__(
        self,
        existing_employee_ids: set[str] | None = None,
        existing_role_ids: set[str] | None = None,
    ) -> None:
        self._employee_ids = existing_employee_ids or set()
        self._role_ids = existing_role_ids or set()
        self.added: list = []

    async def execute(self, stmt):  # noqa: ANN001 - SQLAlchemy statement
        entity = stmt.column_descriptions[0]["entity"]
        params = stmt.compile().params
        if entity is UserDetailsModel:
            value = params.get("employee_id_1")
            rows = [uuid4()] if value in self._employee_ids else []
            return _FakeResult(rows)
        if entity is RoleModel:
            queried = params.get("id_1") or []
            rows = [rid for rid in queried if str(rid) in self._role_ids]
            return _FakeResult(rows)
        raise AssertionError(f"Unexpected query against {entity!r}")

    def add(self, obj) -> None:  # noqa: ANN001
        self.added.append(obj)


class FakeUserRepository(IUserRepository):
    """In-memory ``IUserRepository`` tracking created users and known usernames."""

    def __init__(self, existing_usernames: set[str] | None = None) -> None:
        self._store: dict[UUID, User] = {}
        self._usernames = {u.lower() for u in (existing_usernames or set())}

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


def _active_entity() -> EntityEntity:
    return EntityEntity(
        id=uuid4(),
        entity_name="Acme",
        short_code="AC",
        company_code="ACME",
        is_active=True,
    )


# ─── Generators ───

_token = st.text(alphabet=string.ascii_letters + string.digits, min_size=1, max_size=20)
_blank = st.one_of(
    st.just(""),
    st.text(alphabet=" \t\n\r\f\v", min_size=1, max_size=6),
)
# Passwords too short to satisfy the >= 8 rule (Req 4.4): absent or 0–7 chars.
_short_password = st.one_of(
    st.none(),
    st.text(alphabet=string.printable, min_size=0, max_size=7),
)

# The distinct rejection triggers named by Property 14.
_KINDS = [
    "missing_employee_id",
    "missing_username",
    "duplicate_employee_id",
    "duplicate_username",
    "short_password",
    "unknown_entity",
    "inactive_entity",
    "unknown_role",
]


# ``deadline=None``: the create path performs a (deliberately slow) bcrypt hash
# when Validate-with-AD is enabled, so per-example timing is not a useful signal.
@settings(max_examples=20, deadline=None)
@given(
    kind=st.sampled_from(_KINDS),
    employee_id=_token,
    username=_token,
    blank_value=_blank,
    short_password=_short_password,
    data=st.data(),
)
def test_create_user_validation_rejects_and_persists_nothing(
    kind: str,
    employee_id: str,
    username: str,
    blank_value: str,
    short_password: str | None,
    data: st.DataObject,
) -> None:
    """A create-user request violating exactly one rule is rejected, nothing stored.

    For each rejection trigger the request is built so that precisely the field
    under test is invalid while every other field is valid; the request MUST be
    rejected (a ``MasterValidationError`` or ``MasterConflictError``) and the
    user repository and session MUST remain empty (no user, details row, or role
    assignment persisted).
    """

    # Baseline valid collaborators / fields; each branch perturbs exactly one.
    existing_employee_ids: set[str] = set()
    existing_usernames: set[str] = set()
    existing_role_ids: set[str] = set()
    entities: list[EntityEntity] = []

    req_employee_id: str = employee_id
    req_username: str = username
    req_entity_id: UUID | None = None
    req_role_ids: list[UUID] = []
    req_is_validate_ad: bool = True
    req_password: str | None = None
    expected: type[Exception] = MasterValidationError

    if kind == "missing_employee_id":
        req_employee_id = blank_value
    elif kind == "missing_username":
        req_username = blank_value
    elif kind == "duplicate_employee_id":
        existing_employee_ids = {employee_id.strip()}
        expected = MasterConflictError
    elif kind == "duplicate_username":
        existing_usernames = {username.strip()}
        expected = MasterConflictError
    elif kind == "short_password":
        req_is_validate_ad = False
        req_password = short_password
    elif kind == "unknown_entity":
        # entity_repo has no such entity → reference cannot resolve.
        req_entity_id = uuid4()
    elif kind == "inactive_entity":
        inactive = EntityEntity(
            id=uuid4(),
            entity_name="Dormant",
            short_code="DM",
            company_code="DORM",
            is_active=False,
        )
        entities = [inactive]
        req_entity_id = inactive.id
    elif kind == "unknown_role":
        # A supplied role id that is absent from the role table.
        req_role_ids = [uuid4()]

    request = CreateUserRequest(
        employee_id=req_employee_id,
        username=req_username,
        entity_id=req_entity_id,
        role_ids=req_role_ids,
        is_validate_ad=req_is_validate_ad,
        password=req_password,
    )

    session = FakeSession(
        existing_employee_ids=existing_employee_ids,
        existing_role_ids=existing_role_ids,
    )
    user_repo = FakeUserRepository(existing_usernames=existing_usernames)
    entity_repo = FakeEntityRepository(entities)
    service = UserService(
        session=session,  # type: ignore[arg-type]
        user_repo=user_repo,
        entity_repo=entity_repo,
    )

    async def scenario() -> None:
        try:
            await service.create_user(request, _actor())
        except (MasterValidationError, MasterConflictError) as exc:
            assert isinstance(exc, expected), (
                f"{kind}: expected {expected.__name__}, got {type(exc).__name__}"
            )
        else:
            raise AssertionError(f"{kind}: create_user was not rejected")

        # Nothing persisted: no user created and no details/role rows staged.
        assert user_repo._store == {}, f"{kind}: a user was persisted"
        assert session.added == [], f"{kind}: rows were staged on the session"

    asyncio.run(scenario())
