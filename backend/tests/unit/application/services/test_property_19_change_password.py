# Feature: lacm-masters, Property 19: Change-password behaviour.
"""Property-based test for Edit-User change-password behaviour.

Property 19: Change-password behaviour.

**Validates: Requirements 5.8, 5.9, 5.10, 5.11**

*For any* edit-user request with Validate-with-AD disabled:
  * a non-empty Change Password value of at least 8 characters sets the user's
    password so the new password verifies, without requiring the old
    password (Req 5.9);
  * a non-empty value shorter than 8 characters is rejected with no
    modification (Req 5.10);
  * an empty Change Password value leaves the existing password hash
    unchanged (Req 5.11).
Enabling Validate-with-AD updates the user so authentication no longer requires
a stored password, and any supplied Change Password is ignored (Req 5.8).

``UserService.update_user`` is exercised end-to-end through a real in-memory
``IUserRepository`` (not a mock) and lightweight stand-ins for the Entity
repository and async session, so the actual change-password ordering and the
"nothing is modified on rejection" guarantee are validated against the real
service logic. Each Hypothesis example drives the async service via
``asyncio.run`` so examples stay isolated. Real bcrypt hashing/verification is
used so the "new password verifies" claim is checked against production crypto.
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
from src.domain.entities.user import User
from src.domain.repositories.user_repository import IUserRepository
from src.infrastructure.security.password_encoder import hash_password, verify_password

_MIN_PASSWORD_LEN = 8


# ─── Fakes (no mocks) ───


class FakeUserRepository(IUserRepository):
    """In-memory ``IUserRepository`` holding a single editable user.

    ``get_by_id`` returns the *stored reference* (as the real adapter does for a
    session-attached entity), so any in-place mutation the service performs is
    observable through the store — this is what lets the test assert that a
    rejected request modifies nothing.
    """

    def __init__(self, user: User | None = None) -> None:
        self._store: dict[UUID, User] = {}
        if user is not None:
            self._store[user.id] = user
        self.update_calls = 0

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
        self.update_calls += 1
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


class _FakeSession:
    """Async-session stand-in.

    ``update_user`` only touches the session when ``email``/``first_name``/
    ``last_name`` or ``role_ids`` are supplied; the scenarios here never supply
    those, so no query is ever issued and the session needs no behaviour.
    """

    def add(self, obj: object) -> None:  # pragma: no cover - never reached here
        raise AssertionError("update_user staged a row unexpectedly")

    async def execute(self, stmt: object):  # pragma: no cover - never reached here
        raise AssertionError("update_user issued a query unexpectedly")


class _FakeEntityRepository:
    """Entity repo stand-in; ``entity_id`` is never supplied, so it is unused."""

    async def get_by_id(self, entity_id: UUID):  # pragma: no cover - unused
        return None


def _actor() -> User:
    return User(id=uuid4(), username="admin", is_active=True)


def _make_user(*, password_hash: str, is_validate_ad: bool) -> User:
    return User(
        id=uuid4(),
        username="jdoe",
        password_hash=password_hash,
        is_active=True,
        is_validate_ad=is_validate_ad,
        entity_id=None,
        created_by="seed",
        modified_by="seed",
    )


def _service(user: User) -> tuple[UserService, FakeUserRepository]:
    repo = FakeUserRepository(user)
    service = UserService(
        session=_FakeSession(),  # type: ignore[arg-type]
        user_repo=repo,
        entity_repo=_FakeEntityRepository(),  # type: ignore[arg-type]
    )
    return service, repo


# ─── Generators ───

# Passwords use printable characters (bcrypt-safe at these lengths) so the
# verification claim is exercised against realistic secrets.
_valid_password = st.text(alphabet=string.printable, min_size=_MIN_PASSWORD_LEN, max_size=24)
_short_password = st.text(alphabet=string.printable, min_size=1, max_size=_MIN_PASSWORD_LEN - 1)
_original_secret = st.text(alphabet=string.ascii_letters + string.digits, min_size=8, max_size=16)


@settings(max_examples=20, deadline=None)
@given(original_secret=_original_secret, new_password=_valid_password)
def test_valid_change_password_sets_new_password_when_ad_off(
    original_secret: str, new_password: str
) -> None:
    """Req 5.9: a >= 8 char Change Password with AD off sets the new password.

    The new password MUST verify against the stored hash afterwards, without
    any need for the previous password.
    """

    async def scenario() -> None:
        original_hash = hash_password(original_secret)
        user = _make_user(password_hash=original_hash, is_validate_ad=False)
        service, repo = _service(user)

        request = EditUserRequest(change_password=new_password)
        await service.update_user(user.id, request, _actor())

        stored = repo._store[user.id]
        # The new password verifies against the freshly stored hash (Req 5.9)…
        assert verify_password(new_password, stored.password_hash)
        # …and the hash actually changed from the seeded one.
        assert stored.password_hash != original_hash
        # AD stays disabled (it was neither supplied nor toggled).
        assert stored.is_validate_ad is False

    asyncio.run(scenario())


@settings(max_examples=20, deadline=None)
@given(original_secret=_original_secret, short_password=_short_password)
def test_short_change_password_rejected_without_modification_when_ad_off(
    original_secret: str, short_password: str
) -> None:
    """Req 5.10: a non-empty Change Password < 8 chars with AD off is rejected.

    The request MUST raise a validation error and leave the user unmodified —
    the stored password hash and the AD flag are unchanged.
    """

    async def scenario() -> None:
        original_hash = hash_password(original_secret)
        user = _make_user(password_hash=original_hash, is_validate_ad=False)
        service, repo = _service(user)

        request = EditUserRequest(change_password=short_password)
        try:
            await service.update_user(user.id, request, _actor())
        except MasterValidationError as exc:
            assert exc.field == "change_password"
        else:
            raise AssertionError("short Change Password was not rejected")

        stored = repo._store[user.id]
        # No modification: the password hash and AD flag are untouched (Req 5.10).
        assert stored.password_hash == original_hash
        assert stored.is_validate_ad is False
        # The old secret still verifies, confirming the hash was not replaced.
        assert verify_password(original_secret, stored.password_hash)

    asyncio.run(scenario())


@settings(max_examples=20, deadline=None)
@given(original_secret=_original_secret)
def test_empty_change_password_leaves_password_unchanged(
    original_secret: str,
) -> None:
    """Req 5.11: an empty Change Password leaves the existing password unchanged.

    Editing another field (here, toggling is_active) while supplying an empty
    Change Password must not disturb the stored password hash.
    """

    async def scenario() -> None:
        original_hash = hash_password(original_secret)
        user = _make_user(password_hash=original_hash, is_validate_ad=False)
        service, repo = _service(user)

        request = EditUserRequest(change_password="", is_active=False)
        await service.update_user(user.id, request, _actor())

        stored = repo._store[user.id]
        # The password hash is preserved exactly (Req 5.11)…
        assert stored.password_hash == original_hash
        assert verify_password(original_secret, stored.password_hash)
        # …while the explicitly-supplied field still applied.
        assert stored.is_active is False

    asyncio.run(scenario())


@settings(max_examples=20, deadline=None)
@given(
    original_secret=_original_secret,
    started_with_ad=st.booleans(),
    supplied_password=st.one_of(st.none(), _valid_password),
)
def test_enabling_ad_updates_user_and_ignores_supplied_password(
    original_secret: str, started_with_ad: bool, supplied_password: str | None
) -> None:
    """Req 5.8: enabling Validate-with-AD updates the user; password is ignored.

    Once AD is enabled, authentication no longer relies on a stored password, so
    any Change Password value supplied in the same edit MUST NOT take effect.
    """

    async def scenario() -> None:
        original_hash = hash_password(original_secret)
        user = _make_user(password_hash=original_hash, is_validate_ad=started_with_ad)
        service, repo = _service(user)

        request = EditUserRequest(
            is_validate_ad=True,
            change_password=supplied_password,
        )
        await service.update_user(user.id, request, _actor())

        stored = repo._store[user.id]
        # AD is enabled after the edit (Req 5.8).
        assert stored.is_validate_ad is True
        # A password supplied alongside the AD enable is ignored — the stored
        # hash is unchanged and the original secret still verifies.
        assert stored.password_hash == original_hash
        assert verify_password(original_secret, stored.password_hash)

    asyncio.run(scenario())
