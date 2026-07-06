# Feature: lacm-masters, Property 18: Deactivation blocks authentication.
"""Property-based test for deactivation blocking authentication.

Property 18: Deactivation blocks authentication.

**Validates: Requirements 5.6**

Requirement 5.6: *WHEN an edit-user request that sets Is Active to false is
persisted successfully, THE User_Service SHALL block the user from
authenticating.*

The property exercises the real authentication path
(``src.infrastructure.security.auth_manager.AuthManager.login``) against an
in-memory user repository. For any user who would otherwise authenticate
successfully (active, unblocked, correct local password), persisting an edit
that sets ``is_active`` to false MUST cause authentication to be rejected. The
test first confirms a successful login on the active user so that the post-edit
rejection is attributable to the deactivation alone.
"""

from __future__ import annotations

import asyncio
from uuid import uuid4

from hypothesis import given, settings
from hypothesis import strategies as st

from src.domain.entities.user import User
from src.infrastructure.security.auth_manager import (
    AuthManager,
    UserInactiveError,
)
from src.infrastructure.security.jwt_provider import JWTProvider
from src.infrastructure.security.password_encoder import hash_password


class FakeUserRepository:
    """Minimal in-memory user repository exposing ``get_by_username``.

    ``AuthManager.login`` only depends on ``get_by_username``; the user object it
    returns is the same instance held in the store, so a persisted deactivation
    is reflected on the next lookup.
    """

    def __init__(self, user: User) -> None:
        self._user = user

    async def get_by_username(self, username: str) -> User | None:
        if self._user.username == username:
            return self._user
        return None


def _make_auth_manager(user: User) -> AuthManager:
    return AuthManager(
        user_repository=FakeUserRepository(user),  # type: ignore[arg-type]
        jwt_provider=JWTProvider(),
    )


# Usernames: non-empty printable identifiers; passwords: non-empty text. Both are
# constrained to the input space the login flow actually accepts.
_usernames = st.text(
    alphabet=st.characters(min_codepoint=33, max_codepoint=126), min_size=1, max_size=40
)
_passwords = st.text(min_size=1, max_size=72)


@settings(max_examples=20, deadline=None)
@given(username=_usernames, password=_passwords)
def test_deactivation_blocks_authentication(username: str, password: str) -> None:
    """A persisted deactivation makes a previously valid login fail.

    The user is created active, unblocked, and using a local password (so the
    flow does not reach the external AD service). After confirming the active
    user authenticates, the edit sets ``is_active`` to false and persists it;
    the subsequent login MUST raise ``UserInactiveError``.
    """
    user = User(
        id=uuid4(),
        username=username,
        password_hash=hash_password(password),
        is_active=True,
        is_blocked=False,
        is_validate_ad=False,
    )
    auth = _make_auth_manager(user)

    async def scenario() -> None:
        # Precondition: the active, unblocked user authenticates successfully.
        tokens = await auth.login(username, password)
        assert tokens.access_token

        # Edit that sets Is Active to false, persisted on the stored user.
        user.deactivate("admin")
        assert user.is_active is False
        # The domain invariant agrees the user can no longer authenticate.
        assert user.can_authenticate() is False

        # Post-condition: authentication is now blocked.
        try:
            await auth.login(username, password)
        except UserInactiveError:
            return
        raise AssertionError("Deactivated user was able to authenticate")

    asyncio.run(scenario())
