"""
Unit tests for Authentication Manager.

Covers the login flows, Microsoft SSO resolution, and the refresh-token lifecycle: rotation,
reuse detection with its grace window, and revocation. Repositories are hand-written fakes
(`user_fakes.py`), not mocks; the corporate directory is a `FakeDirectory`.
"""

from datetime import UTC, datetime, timedelta

import pytest
from user_fakes import (
    FakeDirectory,
    FakeRefreshTokenRepository,
    FakeUserDetailsRepository,
    FakeUserRepository,
)

from src.config.settings import settings
from src.domain.entities.user import User
from src.domain.entities.user_details import UserDetails
from src.infrastructure.external.employee_ad.employee_ad_client import (
    EmployeeADError,
    EmployeeADUnavailableError,
)
from src.infrastructure.security.auth_manager import (
    AuthenticationError,
    AuthManager,
    AuthServiceUnavailableError,
    InvalidCredentialsError,
    InvalidTokenError,
    MicrosoftEmailMissingError,
    SsoUserNotProvisionedError,
    UserBlockedError,
    UserInactiveError,
)
from src.infrastructure.security.jwt_provider import JWTProvider
from src.infrastructure.security.password_encoder import hash_password

PASSWORD = "ValidPass123!"


@pytest.fixture
def users() -> FakeUserRepository:
    return FakeUserRepository()


@pytest.fixture
def details() -> FakeUserDetailsRepository:
    return FakeUserDetailsRepository()


@pytest.fixture
def tokens() -> FakeRefreshTokenRepository:
    return FakeRefreshTokenRepository()


@pytest.fixture
def directory() -> FakeDirectory:
    return FakeDirectory()


@pytest.fixture
def jwt_provider() -> JWTProvider:
    return JWTProvider()


@pytest.fixture
def auth_manager(
    users: FakeUserRepository,
    details: FakeUserDetailsRepository,
    tokens: FakeRefreshTokenRepository,
    directory: FakeDirectory,
    jwt_provider: JWTProvider,
) -> AuthManager:
    return AuthManager(
        user_repository=users,
        jwt_provider=jwt_provider,
        user_details_repository=details,
        refresh_token_repository=tokens,
        directory=directory,
    )


def _local_user(**overrides: object) -> User:
    # is_validate_ad=False keeps login on the local bcrypt path unless a test says otherwise.
    fields: dict[str, object] = {
        "username": "activeuser",
        "password_hash": hash_password(PASSWORD),
        "is_active": True,
        "is_blocked": False,
        "is_validate_ad": False,
    }
    fields.update(overrides)
    return User(**fields)  # type: ignore[arg-type]


@pytest.fixture
def active_user(users: FakeUserRepository) -> User:
    return users.add(_local_user())


class TestLogin:
    async def test_valid_credentials_return_a_token_pair(
        self, auth_manager: AuthManager, active_user: User
    ) -> None:
        result = await auth_manager.login("activeuser", PASSWORD)

        assert result.access_token
        assert result.refresh_token
        assert result.token_type == "Bearer"
        assert result.expires_in > 0
        assert result.user_id == active_user.id
        assert result.username == "activeuser"

    async def test_login_records_the_refresh_token_so_it_can_be_spent_and_revoked(
        self,
        auth_manager: AuthManager,
        active_user: User,
        tokens: FakeRefreshTokenRepository,
        jwt_provider: JWTProvider,
    ) -> None:
        result = await auth_manager.login("activeuser", PASSWORD)

        assert result.refresh_token is not None
        jti = jwt_provider.verify_token(result.refresh_token, expected_type="refresh").jti
        assert jti is not None
        record = await tokens.get_by_jti(jti)
        assert record is not None
        assert record.user_id == active_user.id
        assert record.used_at is None
        assert record.revoked_at is None

    async def test_every_login_starts_its_own_session(
        self, auth_manager: AuthManager, active_user: User, tokens: FakeRefreshTokenRepository
    ) -> None:
        await auth_manager.login("activeuser", PASSWORD)
        await auth_manager.login("activeuser", PASSWORD)

        assert len({row.family_id for row in tokens.rows.values()}) == 2

    async def test_login_clears_long_expired_tokens(
        self, auth_manager: AuthManager, active_user: User, tokens: FakeRefreshTokenRepository
    ) -> None:
        from src.domain.entities.refresh_token import RefreshToken

        await tokens.create(
            RefreshToken(
                jti="stale",
                family_id="old",
                user_id=active_user.id,
                expires_at=datetime.now(UTC) - timedelta(days=3),
            )
        )

        await auth_manager.login("activeuser", PASSWORD)

        assert "stale" not in tokens.rows

    async def test_wrong_password_is_rejected(
        self, auth_manager: AuthManager, active_user: User
    ) -> None:
        with pytest.raises(InvalidCredentialsError):
            await auth_manager.login("activeuser", "WrongPassword!")

    async def test_unknown_user_is_rejected_with_the_same_error(
        self, auth_manager: AuthManager
    ) -> None:
        with pytest.raises(InvalidCredentialsError) as unknown:
            await auth_manager.login("ghost", "anypass")

        assert unknown.value.message == InvalidCredentialsError().message

    async def test_unknown_user_still_pays_for_a_password_check(
        self, auth_manager: AuthManager, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """So response time does not tell an attacker which usernames exist."""
        from src.infrastructure.security import auth_manager as module

        checked: list[str] = []
        monkeypatch.setattr(
            module, "verify_password", lambda plain, hashed: checked.append(plain) or False
        )

        with pytest.raises(InvalidCredentialsError):
            await auth_manager.login("ghost", "guess")

        assert checked == ["guess"]

    async def test_inactive_user_is_rejected(
        self, auth_manager: AuthManager, users: FakeUserRepository
    ) -> None:
        users.add(_local_user(username="inactiveuser", is_active=False))

        with pytest.raises(UserInactiveError):
            await auth_manager.login("inactiveuser", PASSWORD)

    async def test_blocked_user_is_rejected(
        self, auth_manager: AuthManager, users: FakeUserRepository
    ) -> None:
        users.add(_local_user(username="blockeduser", is_blocked=True))

        with pytest.raises(UserBlockedError):
            await auth_manager.login("blockeduser", PASSWORD)

    async def test_a_rejected_login_issues_no_token(
        self, auth_manager: AuthManager, active_user: User, tokens: FakeRefreshTokenRepository
    ) -> None:
        with pytest.raises(InvalidCredentialsError):
            await auth_manager.login("activeuser", "WrongPassword!")

        assert tokens.rows == {}


class TestLoginViaActiveDirectory:
    """The is_validate_ad=True branch, against a fake directory."""

    @pytest.fixture
    def ad_user(self, users: FakeUserRepository) -> User:
        return users.add(_local_user(username="aduser", password_hash="", is_validate_ad=True))

    async def test_ad_user_is_validated_by_the_directory_not_the_local_hash(
        self, auth_manager: AuthManager, ad_user: User, directory: FakeDirectory
    ) -> None:
        result = await auth_manager.login("aduser", "AnyPassword")

        assert result.access_token
        assert directory.calls == [("aduser", "AnyPassword")]

    async def test_a_local_user_never_reaches_the_directory(
        self, auth_manager: AuthManager, active_user: User, directory: FakeDirectory
    ) -> None:
        await auth_manager.login("activeuser", PASSWORD)

        assert directory.calls == []

    async def test_directory_rejection_is_invalid_credentials(
        self, auth_manager: AuthManager, ad_user: User, directory: FakeDirectory
    ) -> None:
        directory.valid = False

        with pytest.raises(InvalidCredentialsError):
            await auth_manager.login("aduser", "AnyPassword")

    @pytest.mark.parametrize("error", [EmployeeADUnavailableError("down"), EmployeeADError("boom")])
    async def test_a_directory_outage_is_not_a_credential_failure(
        self,
        auth_manager: AuthManager,
        ad_user: User,
        directory: FakeDirectory,
        error: EmployeeADError,
    ) -> None:
        """It is a 503 apart from 401, so the caller can leave the guess budget alone."""
        directory.error = error

        with pytest.raises(AuthServiceUnavailableError) as raised:
            await auth_manager.login("aduser", "AnyPassword")

        assert raised.value.status_code == 503
        assert not isinstance(raised.value, InvalidCredentialsError)


class TestMicrosoftLogin:
    """
    The SSO path: a verified Microsoft email must resolve to a locally-known
    user — primarily an employee imported from AD, whose email lives on
    user_details while their username is the employee id.
    """

    @pytest.fixture
    def imported_user(self, users: FakeUserRepository) -> User:
        # Username is the employee id (as set by the AD import), NOT the email.
        return users.add(User(username="E12345", password_hash=""))

    async def test_resolves_imported_employee_by_user_details_email(
        self,
        auth_manager: AuthManager,
        imported_user: User,
        details: FakeUserDetailsRepository,
    ) -> None:
        details.add(
            UserDetails(user_id=imported_user.id, employee_id="E12345", email="ada@example.com")
        )

        result = await auth_manager.microsoft_login({"mail": "Ada@Example.com"})

        assert result.access_token
        assert result.refresh_token
        assert result.user_id == imported_user.id
        assert result.username == "E12345"

    async def test_falls_back_to_username_for_legacy_sso_user(
        self, auth_manager: AuthManager, users: FakeUserRepository
    ) -> None:
        users.add(User(username="legacy@example.com", password_hash=""))

        result = await auth_manager.microsoft_login({"userPrincipalName": "legacy@example.com"})

        assert result.username == "legacy@example.com"

    async def test_prefers_mail_over_upn(
        self, auth_manager: AuthManager, users: FakeUserRepository
    ) -> None:
        users.add(User(username="upn@example.com", password_hash=""))

        with pytest.raises(SsoUserNotProvisionedError):
            await auth_manager.microsoft_login(
                {"mail": "real@example.com", "userPrincipalName": "upn@example.com"}
            )

    async def test_missing_email_is_rejected(self, auth_manager: AuthManager) -> None:
        with pytest.raises(MicrosoftEmailMissingError):
            await auth_manager.microsoft_login({"displayName": "No Email"})

    async def test_unprovisioned_email_is_rejected_and_nothing_is_created(
        self, auth_manager: AuthManager, users: FakeUserRepository
    ) -> None:
        with pytest.raises(SsoUserNotProvisionedError):
            await auth_manager.microsoft_login({"mail": "stranger@example.com"})

        assert users.rows == {}

    async def test_inactive_imported_user_is_rejected(
        self,
        auth_manager: AuthManager,
        imported_user: User,
        users: FakeUserRepository,
        details: FakeUserDetailsRepository,
    ) -> None:
        imported_user.is_active = False
        await users.update(imported_user)
        details.add(UserDetails(user_id=imported_user.id, email="ada@example.com"))

        with pytest.raises(UserInactiveError):
            await auth_manager.microsoft_login({"mail": "ada@example.com"})

    async def test_blocked_imported_user_is_rejected(
        self,
        auth_manager: AuthManager,
        imported_user: User,
        users: FakeUserRepository,
        details: FakeUserDetailsRepository,
    ) -> None:
        imported_user.is_blocked = True
        await users.update(imported_user)
        details.add(UserDetails(user_id=imported_user.id, email="ada@example.com"))

        with pytest.raises(UserBlockedError):
            await auth_manager.microsoft_login({"mail": "ada@example.com"})


class TestRefresh:
    """Refresh tokens are single-use: each one is spent for its successor."""

    @pytest.fixture
    async def first_token(self, auth_manager: AuthManager, active_user: User) -> str:
        session = await auth_manager.login("activeuser", PASSWORD)
        assert session.refresh_token is not None
        return session.refresh_token

    def _jti(self, jwt_provider: JWTProvider, token: str) -> str:
        jti = jwt_provider.verify_token(token, expected_type="refresh").jti
        assert jti is not None
        return jti

    async def test_returns_a_new_access_token_and_a_new_refresh_token(
        self, auth_manager: AuthManager, first_token: str
    ) -> None:
        result = await auth_manager.refresh(first_token)

        assert result.access_token
        assert result.token_type == "Bearer"
        assert result.refresh_token
        assert result.refresh_token != first_token

    async def test_the_successor_joins_the_same_session(
        self,
        auth_manager: AuthManager,
        first_token: str,
        tokens: FakeRefreshTokenRepository,
    ) -> None:
        await auth_manager.refresh(first_token)

        assert len({row.family_id for row in tokens.rows.values()}) == 1
        assert len(tokens.rows) == 2

    async def test_the_presented_token_is_spent(
        self,
        auth_manager: AuthManager,
        first_token: str,
        tokens: FakeRefreshTokenRepository,
        jwt_provider: JWTProvider,
    ) -> None:
        await auth_manager.refresh(first_token)

        spent = await tokens.get_by_jti(self._jti(jwt_provider, first_token))
        assert spent is not None
        assert spent.used_at is not None

    async def test_the_successor_can_be_refreshed_in_turn(
        self, auth_manager: AuthManager, first_token: str
    ) -> None:
        second = await auth_manager.refresh(first_token)
        assert second.refresh_token is not None

        third = await auth_manager.refresh(second.refresh_token)

        assert third.access_token
        assert third.refresh_token

    async def test_garbage_is_rejected(self, auth_manager: AuthManager) -> None:
        with pytest.raises(InvalidTokenError):
            await auth_manager.refresh("invalid.token.here")

    async def test_an_access_token_is_not_a_refresh_token(
        self, auth_manager: AuthManager, active_user: User, jwt_provider: JWTProvider
    ) -> None:
        access = jwt_provider.create_access_token(active_user.username, active_user.id)

        with pytest.raises(InvalidTokenError):
            await auth_manager.refresh(access)

    async def test_the_error_does_not_say_why_the_token_failed(
        self, auth_manager: AuthManager
    ) -> None:
        with pytest.raises(InvalidTokenError) as raised:
            await auth_manager.refresh("invalid.token.here")

        assert raised.value.message == "Invalid or expired token"
        assert raised.value.status_code == 401

    async def test_a_token_from_before_rotation_has_no_jti_and_is_rejected(
        self, auth_manager: AuthManager, active_user: User, jwt_provider: JWTProvider
    ) -> None:
        import jwt

        now = datetime.now(UTC)
        legacy = jwt.encode(
            {
                "sub": active_user.username,
                "user_id": str(active_user.id),
                "token_type": "refresh",
                "iat": now,
                "exp": now + timedelta(days=1),
            },
            settings.JWT_SECRET_KEY,
            algorithm=settings.JWT_ALGORITHM,
        )

        with pytest.raises(InvalidTokenError):
            await auth_manager.refresh(legacy)

    async def test_a_validly_signed_token_the_server_never_issued_is_rejected(
        self, auth_manager: AuthManager, active_user: User, jwt_provider: JWTProvider
    ) -> None:
        unissued = jwt_provider.create_refresh_token(active_user.username, active_user.id)

        with pytest.raises(InvalidTokenError):
            await auth_manager.refresh(unissued)

    async def test_a_token_for_a_different_user_than_its_record_is_rejected(
        self,
        auth_manager: AuthManager,
        first_token: str,
        users: FakeUserRepository,
        tokens: FakeRefreshTokenRepository,
        jwt_provider: JWTProvider,
    ) -> None:
        tokens.rows[self._jti(jwt_provider, first_token)].user_id = 999_999

        with pytest.raises(InvalidTokenError):
            await auth_manager.refresh(first_token)

    async def test_a_revoked_session_cannot_be_refreshed(
        self, auth_manager: AuthManager, first_token: str
    ) -> None:
        await auth_manager.revoke_session(first_token)

        with pytest.raises(InvalidTokenError):
            await auth_manager.refresh(first_token)

    @pytest.mark.parametrize("field", ["is_blocked", "is_active"])
    async def test_a_user_who_lost_access_ends_the_session(
        self,
        auth_manager: AuthManager,
        first_token: str,
        active_user: User,
        users: FakeUserRepository,
        tokens: FakeRefreshTokenRepository,
        field: str,
    ) -> None:
        setattr(active_user, field, field == "is_blocked")
        await users.update(active_user)

        expected = UserBlockedError if field == "is_blocked" else UserInactiveError
        with pytest.raises(expected):
            await auth_manager.refresh(first_token)

        assert all(row.revoked_at is not None for row in tokens.rows.values())

    async def test_a_user_who_no_longer_exists_is_rejected(
        self, auth_manager: AuthManager, first_token: str, users: FakeUserRepository
    ) -> None:
        users.rows.clear()

        with pytest.raises(InvalidTokenError):
            await auth_manager.refresh(first_token)


class TestRefreshReuse:
    """A spent token presented again is either a racing tab or a copied token."""

    @pytest.fixture
    async def spent_token(self, auth_manager: AuthManager, active_user: User) -> str:
        session = await auth_manager.login("activeuser", PASSWORD)
        assert session.refresh_token is not None
        await auth_manager.refresh(session.refresh_token)
        return session.refresh_token

    def _age_the_use(
        self,
        tokens: FakeRefreshTokenRepository,
        jwt_provider: JWTProvider,
        token: str,
        seconds: int,
    ) -> None:
        jti = jwt_provider.verify_token(token, expected_type="refresh").jti
        assert jti is not None
        tokens.rows[jti].used_at = datetime.now(UTC) - timedelta(seconds=seconds)

    async def test_replay_just_after_use_gets_an_access_token_but_no_new_cookie(
        self, auth_manager: AuthManager, spent_token: str
    ) -> None:
        """Two tabs refreshing at once: the second must not be signed out."""
        result = await auth_manager.refresh(spent_token)

        assert result.access_token
        assert result.refresh_token is None

    async def test_replay_just_after_use_leaves_the_session_alive(
        self, auth_manager: AuthManager, spent_token: str, tokens: FakeRefreshTokenRepository
    ) -> None:
        await auth_manager.refresh(spent_token)

        assert all(row.revoked_at is None for row in tokens.rows.values())

    async def test_replay_after_the_grace_window_ends_the_whole_session(
        self,
        auth_manager: AuthManager,
        spent_token: str,
        tokens: FakeRefreshTokenRepository,
        jwt_provider: JWTProvider,
    ) -> None:
        self._age_the_use(
            tokens, jwt_provider, spent_token, settings.REFRESH_REUSE_GRACE_SECONDS + 5
        )

        with pytest.raises(InvalidTokenError):
            await auth_manager.refresh(spent_token)

        # The successor the thief or the owner holds is dead too.
        assert all(row.revoked_at is not None for row in tokens.rows.values())

    async def test_after_a_theft_is_detected_the_successor_stops_working(
        self,
        auth_manager: AuthManager,
        active_user: User,
        tokens: FakeRefreshTokenRepository,
        jwt_provider: JWTProvider,
    ) -> None:
        session = await auth_manager.login("activeuser", PASSWORD)
        assert session.refresh_token is not None
        rotated = await auth_manager.refresh(session.refresh_token)
        assert rotated.refresh_token is not None
        self._age_the_use(
            tokens, jwt_provider, session.refresh_token, settings.REFRESH_REUSE_GRACE_SECONDS + 5
        )

        with pytest.raises(InvalidTokenError):
            await auth_manager.refresh(session.refresh_token)
        with pytest.raises(InvalidTokenError):
            await auth_manager.refresh(rotated.refresh_token)

    async def test_with_the_grace_window_off_any_replay_is_theft(
        self,
        auth_manager: AuthManager,
        spent_token: str,
        tokens: FakeRefreshTokenRepository,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        monkeypatch.setattr(settings, "REFRESH_REUSE_GRACE_SECONDS", 0)
        await _wait_a_tick()

        with pytest.raises(InvalidTokenError):
            await auth_manager.refresh(spent_token)

        assert all(row.revoked_at is not None for row in tokens.rows.values())

    async def test_another_session_of_the_same_user_is_untouched(
        self,
        auth_manager: AuthManager,
        active_user: User,
        tokens: FakeRefreshTokenRepository,
        jwt_provider: JWTProvider,
    ) -> None:
        laptop = await auth_manager.login("activeuser", PASSWORD)
        phone = await auth_manager.login("activeuser", PASSWORD)
        assert laptop.refresh_token is not None and phone.refresh_token is not None
        await auth_manager.refresh(laptop.refresh_token)
        self._age_the_use(
            tokens, jwt_provider, laptop.refresh_token, settings.REFRESH_REUSE_GRACE_SECONDS + 5
        )

        with pytest.raises(InvalidTokenError):
            await auth_manager.refresh(laptop.refresh_token)

        assert (await auth_manager.refresh(phone.refresh_token)).access_token


async def _wait_a_tick() -> None:
    """Let the clock move past the use timestamp so a zero-second window is exceeded."""
    import asyncio

    await asyncio.sleep(0.01)


class TestRevokeSession:
    async def test_revokes_every_token_of_the_session(
        self,
        auth_manager: AuthManager,
        active_user: User,
        tokens: FakeRefreshTokenRepository,
    ) -> None:
        session = await auth_manager.login("activeuser", PASSWORD)
        assert session.refresh_token is not None
        rotated = await auth_manager.refresh(session.refresh_token)
        assert rotated.refresh_token is not None

        await auth_manager.revoke_session(rotated.refresh_token)

        assert all(row.revoked_at is not None for row in tokens.rows.values())

    async def test_leaves_other_sessions_alone(
        self, auth_manager: AuthManager, active_user: User, tokens: FakeRefreshTokenRepository
    ) -> None:
        laptop = await auth_manager.login("activeuser", PASSWORD)
        phone = await auth_manager.login("activeuser", PASSWORD)
        assert laptop.refresh_token is not None and phone.refresh_token is not None

        await auth_manager.revoke_session(laptop.refresh_token)

        assert (await auth_manager.refresh(phone.refresh_token)).access_token

    @pytest.mark.parametrize("token", ["not-a-jwt", ""])
    async def test_a_bad_token_is_ignored_not_an_error(
        self, auth_manager: AuthManager, token: str
    ) -> None:
        await auth_manager.revoke_session(token)

    async def test_a_token_the_server_never_issued_is_ignored(
        self, auth_manager: AuthManager, active_user: User, jwt_provider: JWTProvider
    ) -> None:
        await auth_manager.revoke_session(
            jwt_provider.create_refresh_token(active_user.username, active_user.id)
        )


class TestErrorTypes:
    def test_token_and_directory_errors_are_authentication_errors(self) -> None:
        assert issubclass(InvalidTokenError, AuthenticationError)
        assert issubclass(AuthServiceUnavailableError, AuthenticationError)
        assert not issubclass(AuthServiceUnavailableError, InvalidCredentialsError)
