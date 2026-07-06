# Feature: lacm-masters, Property 11: HR import resolves and links entities correctly.
"""Property-based test for HR-import entity resolution and linking.

Property 11: HR import resolves and links entities correctly.

**Validates: Requirements 3.2, 3.3, 3.4**

*For any* import row, the referenced Entity is resolved by Company Code when the
imported Company Code is non-empty and otherwise by Entity Name (Req 3.2); when
the resolved Entity does not exist it is created first and the user is linked to
the new Entity (Req 3.3); and when it already exists the user is linked to the
existing Entity without creating a duplicate (Req 3.4).

The service is exercised end-to-end through ``UserService.import_users`` using
lightweight, real in-memory stand-ins (not mocks) for the Entity repository, the
User repository, and the async session. A fresh set is built per generated
example so no state leaks between examples. The async service is driven with
``asyncio.run`` because each Hypothesis example is independent.

Generation builds a (possibly empty) set of pre-existing Entities with
case-insensitively unique names and Company Codes, then a single import row whose
Company Code / Entity Name either match an existing Entity (via a case/whitespace
variant, exercising the trimmed case-insensitive resolution) or are fresh tokens
that force a create. The test computes the *expected* resolution from the seeded
repository (the same lookups the service must use) and asserts the imported user
is linked to exactly that Entity, that a match creates no duplicate, and that a
miss creates exactly one new Entity carrying the imported codes.
"""

from __future__ import annotations

import asyncio
import string
from uuid import UUID, uuid4

from hypothesis import assume, given, settings
from hypothesis import strategies as st

from src.api.v1.schemas.user_request import HrImportRow
from src.application.services.user_service import UserService
from src.domain.entities.masters.entity import EntityEntity
from src.domain.entities.user import User

_MAX_NAME_LEN = 255
_MAX_CODE_LEN = 50

# Tokens are short alphanumerics: digits are case-stable while letters let the
# case/whitespace variants exercise trimmed, case-insensitive resolution.
_token = st.text(alphabet=string.ascii_letters + string.digits, min_size=1, max_size=12)


# ─── Real in-memory repositories / session (duck-typed against the ports) ───


class _InMemoryEntityRepository:
    """Dict-backed Entity repository sufficient for import resolution."""

    def __init__(self, entities: list[EntityEntity]) -> None:
        self._store: dict[UUID, EntityEntity] = {e.id: e for e in entities}

    async def get_by_id(self, entity_id: UUID) -> EntityEntity | None:
        return self._store.get(entity_id)

    async def create(self, entity: EntityEntity) -> EntityEntity:
        self._store[entity.id] = entity
        return entity

    async def update(self, entity: EntityEntity) -> EntityEntity:
        self._store[entity.id] = entity
        return entity

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


class _InMemoryUserRepository:
    """Dict-backed User repository capturing created/updated users."""

    def __init__(self) -> None:
        self._store: dict[UUID, User] = {}

    async def get_by_id(self, user_id: UUID) -> User | None:
        return self._store.get(user_id)

    async def create(self, user: User) -> User:
        self._store[user.id] = user
        return user

    async def update(self, user: User) -> User:
        self._store[user.id] = user
        return user

    async def exists_by_username(self, username: str) -> bool:
        return any(u.username == username for u in self._store.values())

    def all_users(self) -> list[User]:
        return list(self._store.values())


class _FakeResult:
    def __init__(self, value: object) -> None:
        self._value = value

    def scalar_one_or_none(self) -> object:
        return self._value


class _FakeSession:
    """Async-session stand-in interpreting the two user_details queries.

    ``UserService`` issues exactly two kinds of statement during import:
    a lookup of ``UserDetailsModel.user_id`` filtered by ``employee_id`` and a
    lookup of the whole ``UserDetailsModel`` filtered by ``user_id``. The added
    detail rows are kept in a list so those lookups can be answered.
    """

    def __init__(self) -> None:
        self._details: list[object] = []

    def add(self, obj: object) -> None:
        self._details.append(obj)

    async def execute(self, stmt: object) -> _FakeResult:
        where = stmt.whereclause  # type: ignore[attr-defined]
        column_name = where.left.name
        value = where.right.value
        if column_name == "employee_id":
            for detail in self._details:
                if getattr(detail, "employee_id", None) == value:
                    return _FakeResult(getattr(detail, "user_id"))
            return _FakeResult(None)
        # column_name == "user_id": return the matching details row
        for detail in self._details:
            if str(getattr(detail, "user_id", None)) == str(value):
                return _FakeResult(detail)
        return _FakeResult(None)


def _actor() -> User:
    return User(id=uuid4(), username="admin", is_active=True)


def _vary(token: str, swap: bool, pad_left: int, pad_right: int) -> str:
    """A trimmed/case variant that still resolves to ``token`` (Req 3.2)."""
    body = token.swapcase() if swap else token
    return (" " * pad_left) + body + (" " * pad_right)


@st.composite
def _import_scenarios(draw: st.DrawFn) -> dict:
    """Build a seeded Entity repo and one import row with a known resolution."""
    # ─── Seed case-insensitively unique existing entities ───
    specs = draw(
        st.lists(
            st.fixed_dictionaries(
                {"name": _token, "code": st.none() | _token}
            ),
            max_size=3,
        )
    )
    existing: list[EntityEntity] = []
    used_names: set[str] = set()
    used_codes: set[str] = set()
    for spec in specs:
        name = spec["name"]
        if name.strip().lower() in used_names:
            continue
        code = spec["code"]
        if code is not None and code.strip().lower() in used_codes:
            code = None
        existing.append(
            EntityEntity(
                id=uuid4(),
                entity_name=name,
                short_code=None,
                company_code=code,
                is_active=True,
            )
        )
        used_names.add(name.strip().lower())
        if code is not None:
            used_codes.add(code.strip().lower())

    entities_with_code = [e for e in existing if e.company_code]

    # ─── Choose a resolution branch ───
    branches = ["create_with_code", "create_by_name"]
    if existing:
        branches.append("match_by_name")
    if entities_with_code:
        branches.append("match_by_code")
    branch = draw(st.sampled_from(branches))

    swap = draw(st.booleans())
    pad_left = draw(st.integers(min_value=0, max_value=2))
    pad_right = draw(st.integers(min_value=0, max_value=2))

    company_code: str | None
    entity_name: str | None

    if branch == "match_by_code":
        target = draw(st.sampled_from(entities_with_code))
        assert target.company_code is not None
        company_code = _vary(target.company_code, swap, pad_left, pad_right)
        # Entity Name is ignored because Company Code is non-empty (Req 3.2).
        entity_name = draw(st.none() | _token)
    elif branch == "match_by_name":
        target = draw(st.sampled_from(existing))
        company_code = draw(st.sampled_from([None, "", "   "]))
        entity_name = _vary(target.entity_name, swap, pad_left, pad_right)
    elif branch == "create_with_code":
        fresh_code = draw(_token)
        assume(fresh_code.strip().lower() not in used_codes)
        # The create-name is (entity_name or company_code); it must not collide
        # with an existing name, or the create would raise a duplicate-name
        # conflict (that conflict path is covered by other properties).
        assume(fresh_code.strip().lower() not in used_names)
        opt_name = draw(st.none() | _token)
        if opt_name is not None:
            assume(opt_name.strip().lower() not in used_names)
        company_code = fresh_code
        entity_name = opt_name
    else:  # create_by_name
        fresh_name = draw(_token)
        assume(fresh_name.strip().lower() not in used_names)
        company_code = draw(st.sampled_from([None, "", "   "]))
        entity_name = fresh_name

    # Keep created/looked-up values within the persisted length limits.
    if company_code is not None:
        assume(len(company_code.strip()) <= _MAX_CODE_LEN)
    if entity_name is not None:
        assume(len(entity_name.strip()) <= _MAX_NAME_LEN)

    employee_id = draw(_token)

    return {
        "existing": existing,
        "branch": branch,
        "row": HrImportRow(
            employee_id=employee_id,
            company_code=company_code,
            entity_name=entity_name,
        ),
    }


# ``deadline=None``: creating the imported user runs a deliberately-slow bcrypt
# password hash per example, which exceeds the default 200ms per-example
# deadline without indicating any property violation.
@settings(max_examples=20, deadline=None)
@given(scenario=_import_scenarios())
def test_hr_import_resolves_and_links_entities(scenario: dict) -> None:
    """Importing one row links the user to the resolved/created Entity.

    Resolution uses Company Code when non-empty else Entity Name (Req 3.2); a
    miss creates exactly one Entity carrying the imported codes and links the
    user to it (Req 3.3); a hit links to the existing Entity and creates no
    duplicate (Req 3.4).
    """

    async def run() -> None:
        entity_repo = _InMemoryEntityRepository(scenario["existing"])
        user_repo = _InMemoryUserRepository()
        session = _FakeSession()
        service = UserService(
            session=session,  # type: ignore[arg-type]
            user_repo=user_repo,  # type: ignore[arg-type]
            entity_repo=entity_repo,  # type: ignore[arg-type]
        )

        row: HrImportRow = scenario["row"]
        before_ids = set(entity_repo._store.keys())

        # Independently compute the expected resolution with the same lookup
        # precedence the service must follow (Req 3.2).
        cc = (row.company_code or "").strip()
        en = (row.entity_name or "").strip()
        if cc:
            pre_match = await entity_repo.get_by_company_code(cc)
        else:
            pre_match = await entity_repo.get_by_name(en)

        summary = await service.import_users([row], _actor())

        # The single valid row imports successfully (no row-level failure).
        assert summary.received == 1
        assert summary.failed == 0
        assert summary.created == 1

        users = user_repo.all_users()
        assert len(users) == 1
        user = users[0]

        after_ids = set(entity_repo._store.keys())

        if pre_match is not None:
            # Existing Entity reused; user linked to it; no duplicate (Req 3.4).
            assert user.entity_id == pre_match.id
            assert after_ids == before_ids
        else:
            # Missing Entity created first, then linked (Req 3.3).
            new_ids = after_ids - before_ids
            assert len(new_ids) == 1
            new_entity = entity_repo._store[new_ids.pop()]
            assert user.entity_id == new_entity.id
            # Created with the imported Company Code (or None) and the imported
            # Entity Name, falling back to the Company Code when name is empty.
            assert (new_entity.company_code or None) == (cc or None)
            assert new_entity.entity_name == (en or cc)

    asyncio.run(run())
