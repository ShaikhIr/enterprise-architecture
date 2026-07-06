# Feature: lacm-masters, Property 16: Edit-user preserves identity and validates references.
"""Property-based test for Edit-User identity preservation and reference validation.

Property 16: Edit-user preserves identity and validates references.

**Validates: Requirements 5.1, 5.3**

*For any* edit-user request on an existing user:
  * the Employee ID and User Name remain unchanged (Req 5.1 — both are
    immutable on edit; the ``EditUserRequest`` schema does not even expose
    them), and
  * the request is rejected *without modification* when the supplied Entity
    reference is not an existing active Entity (Req 5.3).

``UserService.update_user`` is exercised end-to-end through real in-memory
implementations of its collaborators (a fake ``IUserRepository``, a fake
``IEntityRepository`` and a lightweight fake ``AsyncSession`` that answers the
read queries the service issues) rather than mocks, so the identity-preservation
guarantee and the "nothing is modified on rejection" guarantee are validated
against the actual service logic. Each Hypothesis example drives the async
service via ``asyncio.run`` so examples stay isolated.
"""

from __future__ import annotations

import asyncio
import string
from uuid import UUID, uuid4

from hypothesis import given, settings
from hypothesis import strategies as st

from src.api.v1.schemas.user_request import EditUserRequest
from src.application.exceptions.application_exceptions import MasterValidationError
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

    def scalar_one_or_none(self):
        return self._rows[0] if self._rows else None

    def scalars(self) -> _FakeScalars:
        return _FakeScalars(self._rows)


class FakeSession:
    """Minimal stand-in for ``AsyncSession`` for the edit path.

    Answers the read queries ``UserService.update_user`` issues:
      * ``select(UserDetailsModel).where(user_id == ...)`` — the details row
        load used to apply mutable fields,
      * ``select(RoleAssignmentModel).where(...)`` — existing-assignment load
        used when replacing roles,
      * ``select(RoleModel.id).where(id.in_(...))`` — the role-existence probe.
    Any ``add`` is recorded so a test can assert nothing was staged.
    """

    def __init__(
        self,
        details: UserDetailsModel | None = None,
        role_assignments: list | None = None,
        existing_role_ids: set[str] | None = None,
    ) -> None:
        self._details = details
        self._role_assignments = role_assignments or []
        self._role_ids = existing_role_ids or set()
        self.added: list = []

    async def execute(self, stmt):  # noqa: ANN001 - SQLAlchemy statement
        entity = stmt.column_descriptions[0]["entity"]
        if entity is UserDetailsModel:
            rows = [self._details] if self._details is not None else []
            return _FakeResult(rows)
        if entity is RoleAssignmentModel:
            return _FakeResult(list(self._role_assignments))
        if entity is RoleModel:
            params = stmt.compile().params
            queried = params.get("id_1") or []
            rows = [rid for rid in queried if str(rid) in self._role_ids]
            return _FakeResult(rows)
        raise AssertionError(f"Unexpected query against {entity!r}")

    def add(self, obj) -> None:  # noqa: ANN001
        self.added.append(obj)


class FakeUserRepository(IUserRepository):
    """In-memory ``IUserRepository`` returning the stored user by reference."""

    def __init__(self) -> None:
        self._store: dict[UUID, User] = {}

    def seed(self, user: User) -> None:
        self._store[user.id] = user

    async def get_by_id(self, user_id: UUID) -> User | None:
        return self._store.get(user_id)

    async def get_by_username(self, username: str) -> User | None:
        for u in self._store.values():
            if u.username.lower() == username.lower():
                return u
        return None

    async def create(self, user: User) -> User:
        self._store[user.id] = user
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
        return any(u.username.lower() == username.lower() for u in self._store.values())


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
    return User(id=uuid4(), username="editor", is_active=True)


# ─── Generators ───

_token = st.text(alphabet=string.ascii_letters + string.digits, min_size=1, max_size=20)
_optional_token = st.one_of(
    st.none(),
    st.text(alphabet=string.ascii_letters + string.digits + " ", min_size=0, max_size=20),
)

# The three identity/reference scenarios named by Property 16.
_KINDS = ["valid_edit", "unknown_entity", "inactive_entity"]


# ``deadline=None``: keeps per-example timing out of the pass/fail signal.
@settings(max_examples=20, deadline=None)
@given(
    kind=st.sampled_from(_KINDS),
    employee_id=_token,
    username=_token,
    new_email=_optional_token,
    new_first=_optional_token,
    new_last=_optional_token,
    supply_active_entity=st.booleans(),
    supply_roles=st.booleans(),
)
def test_edit_user_preserves_identity_and_validates_entity(
    kind: str,
    employee_id: str,
    username: str,
    new_email: str | None,
    new_first: str | None,
    new_last: str | None,
    supply_active_entity: bool,
    supply_roles: bool,
) -> None:
    """Edit preserves Employee ID / User Name; invalid Entity is rejected intact.

    For ``valid_edit`` the request is applied and afterwards the user's User Name
    and the details row's Employee ID MUST be unchanged from before the edit.
    For ``unknown_entity``/``inactive_entity`` the request supplies an Entity
    reference that is not an existing active Entity; ``update_user`` MUST raise
    ``MasterValidationError`` and leave the user and details row untouched (and
    stage nothing on the session).
    """

    actor = _actor()

    # Seed an existing user and its details row (the immutable identity carriers).
    user = User(
        id=uuid4(),
        username=username,
        password_hash="seed-hash",
        is_active=True,
        is_validate_ad=True,
        entity_id=None,
        created_by="seed",
        modified_by="seed",
    )
    details = UserDetailsModel(
        id=uuid4(),
        user_id=user.id,
        employee_id=employee_id,
        employee_name="Seed Name",
        first_name="Seed",
        last_name="Name",
        email="seed@example.com",
        created_by="seed",
        modified_by="seed",
    )

    user_repo = FakeUserRepository()
    user_repo.seed(user)

    active_entity = EntityEntity(
        id=uuid4(),
        entity_name="Acme",
        short_code="AC",
        company_code="ACME",
        is_active=True,
    )
    inactive_entity = EntityEntity(
        id=uuid4(),
        entity_name="Dormant",
        short_code="DM",
        company_code="DORM",
        is_active=False,
    )

    # Build the request and the collaborator state for the chosen scenario.
    request_kwargs: dict = {
        "email": new_email,
        "first_name": new_first,
        "last_name": new_last,
    }
    entities: list[EntityEntity] = [active_entity, inactive_entity]
    existing_role_ids: set[str] = set()
    expect_rejection = False

    if kind == "valid_edit":
        if supply_active_entity:
            request_kwargs["entity_id"] = active_entity.id
        if supply_roles:
            request_kwargs["role_ids"] = []  # empty replacement set stays valid
    elif kind == "unknown_entity":
        request_kwargs["entity_id"] = uuid4()  # absent from the entity repo
        expect_rejection = True
    elif kind == "inactive_entity":
        request_kwargs["entity_id"] = inactive_entity.id
        expect_rejection = True

    request = EditUserRequest(**request_kwargs)

    session = FakeSession(details=details, existing_role_ids=existing_role_ids)
    entity_repo = FakeEntityRepository(entities)
    service = UserService(
        session=session,  # type: ignore[arg-type]
        user_repo=user_repo,
        entity_repo=entity_repo,
    )

    # Snapshots of the immutable identity and the full mutable user state.
    original_username = user.username
    original_employee_id = details.employee_id
    original_entity_id = user.entity_id
    original_is_active = user.is_active
    original_is_validate_ad = user.is_validate_ad
    original_password_hash = user.password_hash
    original_modified_by = user.modified_by
    original_details_email = details.email
    original_details_first = details.first_name
    original_details_last = details.last_name

    async def scenario() -> None:
        if expect_rejection:
            try:
                await service.update_user(user.id, request, actor)
            except MasterValidationError:
                pass
            else:
                raise AssertionError(
                    f"{kind}: update_user accepted an invalid Entity reference"
                )

            # Rejected without modification: identity AND every mutable field of
            # the user/details remain exactly as seeded; nothing was staged.
            assert user.username == original_username, f"{kind}: username changed"
            assert details.employee_id == original_employee_id, (
                f"{kind}: employee_id changed"
            )
            assert user.entity_id == original_entity_id, f"{kind}: entity_id changed"
            assert user.is_active == original_is_active, f"{kind}: is_active changed"
            assert user.is_validate_ad == original_is_validate_ad, (
                f"{kind}: is_validate_ad changed"
            )
            assert user.password_hash == original_password_hash, (
                f"{kind}: password_hash changed"
            )
            assert user.modified_by == original_modified_by, (
                f"{kind}: user was marked modified on a rejected edit"
            )
            assert details.email == original_details_email, f"{kind}: email changed"
            assert details.first_name == original_details_first, (
                f"{kind}: first_name changed"
            )
            assert details.last_name == original_details_last, (
                f"{kind}: last_name changed"
            )
            assert session.added == [], f"{kind}: rows were staged on a rejected edit"
            return

        # Valid edit: the request is accepted and identity is preserved.
        response = await service.update_user(user.id, request, actor)

        # Req 5.1 — Employee ID and User Name are immutable across the edit.
        assert user.username == original_username, f"{kind}: User Name changed on edit"
        assert response.username == original_username, (
            f"{kind}: response User Name changed on edit"
        )
        assert details.employee_id == original_employee_id, (
            f"{kind}: Employee ID changed on edit"
        )

    asyncio.run(scenario())
