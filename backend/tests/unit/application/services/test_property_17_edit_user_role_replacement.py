# Feature: lacm-masters, Property 17: Valid edit updates mutable fields and replaces roles.
"""Property-based test for valid edit-user behaviour.

Property 17: Valid edit updates mutable fields and replaces roles.

**Validates: Requirements 5.4, 5.5**

*For any* valid edit-user request, the Email, First Name, Last Name, and Entity
reference are updated to the supplied values (Req 5.4) and the user's role
assignments are replaced so that the final active set equals exactly the
supplied Role set, regardless of prior assignments (Req 5.5).

``UserService.update_user`` is exercised end-to-end through real in-memory
implementations of its collaborators (a fake ``IUserRepository``, a fake
``IEntityRepository`` and a lightweight fake ``AsyncSession`` answering the
three read queries the edit path issues — load user-details, validate role
existence, and load the existing active role assignments) rather than mocks, so
the field-update and role-replacement guarantees are validated against the
actual service logic. Each Hypothesis example drives the async service via
``asyncio.run`` so examples stay isolated.
"""

from __future__ import annotations

import asyncio
import string
from uuid import UUID, uuid4

from hypothesis import given, settings
from hypothesis import strategies as st

from src.api.v1.schemas.user_request import EditUserRequest
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

    def scalar_one_or_none(self):
        if not self._rows:
            return None
        return self._rows[0]

    def scalars(self) -> _FakeScalars:
        return _FakeScalars(self._rows)


class FakeSession:
    """Minimal stand-in for ``AsyncSession``.

    Answers exactly the three read queries ``UserService.update_user`` issues on
    the valid edit path:
      * ``select(UserDetailsModel).where(user_id == ...)`` — load the details row
        whose mutable fields are updated (Req 5.4),
      * ``select(RoleModel.id).where(id.in_(...))`` — the role-existence probe,
      * ``select(RoleAssignmentModel).where(user_id == ..., is_active == True)`` —
        the existing active assignments that are replaced (Req 5.5).
    New ``add`` calls (the replacement assignments) are recorded.
    """

    def __init__(
        self,
        details: UserDetailsModel | None,
        existing_role_ids: set[str],
        existing_assignments: list[RoleAssignmentModel],
    ) -> None:
        self._details = details
        self._role_ids = existing_role_ids
        self._assignments = existing_assignments
        self.added: list = []

    async def execute(self, stmt):  # noqa: ANN001 - SQLAlchemy statement
        entity = stmt.column_descriptions[0]["entity"]
        if entity is UserDetailsModel:
            return _FakeResult([self._details] if self._details is not None else [])
        if entity is RoleModel:
            params = stmt.compile().params
            queried = params.get("id_1") or []
            rows = [rid for rid in queried if str(rid) in self._role_ids]
            return _FakeResult(rows)
        if entity is RoleAssignmentModel:
            active = [a for a in self._assignments if a.is_active]
            return _FakeResult(active)
        raise AssertionError(f"Unexpected query against {entity!r}")

    def add(self, obj) -> None:  # noqa: ANN001
        self.added.append(obj)


class FakeUserRepository(IUserRepository):
    """In-memory ``IUserRepository`` seeded with the user under edit."""

    def __init__(self, user: User) -> None:
        self._store: dict[UUID, User] = {user.id: user}

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
    return User(id=uuid4(), username="admin", is_active=True)


def _details_row(user_id: UUID) -> UserDetailsModel:
    """A pre-existing user_details row with stale, distinguishable values."""
    return UserDetailsModel(
        id=uuid4(),
        user_id=user_id,
        employee_id="EMP-ORIGINAL",
        employee_name="Old Name",
        first_name="OldFirst",
        last_name="OldLast",
        email="old@example.com",
    )


def _assignment(user_id: UUID, role_id: UUID) -> RoleAssignmentModel:
    return RoleAssignmentModel(
        id=uuid4(),
        user_id=str(user_id),
        role_id=str(role_id),
        tenant_id=None,
        is_active=True,
        created_by="seed",
        modified_by="seed",
    )


# ─── Generators ───

_text = st.text(alphabet=string.printable, min_size=0, max_size=40)


@settings(max_examples=20, deadline=None)
@given(
    email=_text,
    first_name=_text,
    last_name=_text,
    prior_role_ids=st.lists(st.uuids(), unique=True, max_size=5),
    supplied_role_ids=st.lists(st.uuids(), unique=True, max_size=5),
)
def test_valid_edit_updates_fields_and_replaces_roles(
    email: str,
    first_name: str,
    last_name: str,
    prior_role_ids: list[UUID],
    supplied_role_ids: list[UUID],
) -> None:
    """A valid edit updates the mutable fields and replaces the role set.

    The supplied Email/First/Last/Entity MUST be applied verbatim (after the
    service's trimming) and the final active role-assignment set MUST equal
    exactly the supplied Role set, independent of the prior assignments.
    """

    user_id = uuid4()
    new_entity = EntityEntity(
        id=uuid4(),
        entity_name="Target",
        short_code="TG",
        company_code="TGT",
        is_active=True,
    )

    user = User(
        id=user_id,
        username="jdoe",
        password_hash="x",
        is_active=True,
        is_validate_ad=True,
        entity_id=None,
    )

    details = _details_row(user_id)
    existing_assignments = [_assignment(user_id, rid) for rid in prior_role_ids]

    # Every supplied role must exist for the request to be valid (Req 5.5 path).
    existing_role_ids = {str(r) for r in supplied_role_ids}

    request = EditUserRequest(
        email=email,
        first_name=first_name,
        last_name=last_name,
        entity_id=new_entity.id,
        role_ids=supplied_role_ids,
    )

    session = FakeSession(
        details=details,
        existing_role_ids=existing_role_ids,
        existing_assignments=existing_assignments,
    )
    user_repo = FakeUserRepository(user)
    entity_repo = FakeEntityRepository([new_entity])
    service = UserService(
        session=session,  # type: ignore[arg-type]
        user_repo=user_repo,
        entity_repo=entity_repo,
    )

    async def scenario() -> None:
        await service.update_user(user_id, request, _actor())

        stored = await user_repo.get_by_id(user_id)
        assert stored is not None

        # Req 5.4 — Entity reference updated to the supplied value.
        assert stored.entity_id == new_entity.id

        # Req 5.4 — mutable employee detail fields updated to supplied (trimmed).
        assert details.email == email.strip()
        assert details.first_name == first_name.strip()
        assert details.last_name == last_name.strip()
        assert details.employee_name == f"{first_name.strip()} {last_name.strip()}".strip()

        # Req 5.5 — final active role set equals exactly the supplied set,
        # regardless of what was assigned before.
        for prior in existing_assignments:
            assert prior.is_active is False, "prior assignment was not deactivated"

        final_active = {
            a.role_id
            for a in [*existing_assignments, *session.added]
            if a.is_active
        }
        expected = {str(r) for r in supplied_role_ids}
        assert final_active == expected

    asyncio.run(scenario())
