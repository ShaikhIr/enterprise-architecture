"""
Unit tests for Authentication Manager.
Tests login flows: success, invalid password, inactive user, blocked user.
"""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.domain.entities.user import User
from src.domain.entities.user_details import UserDetails
from src.infrastructure.security.auth_manager import (
    AuthManager,
    InvalidCredentialsError,
    MicrosoftEmailMissingError,
    SsoUserNotProvisionedError,
    UserBlockedError,
    UserInactiveError,
)
from src.infrastructure.security.jwt_provider import JWTProvider
from src.infrastructure.security.password_encoder import hash_password


@pytest.fixture
def mock_user_repo() -> AsyncMock:
    repo = AsyncMock()
    return repo


@pytest.fixture
def mock_user_details_repo() -> AsyncMock:
    repo = AsyncMock()
    # Default: no imported profile matches, so microsoft_login falls back to the
    # username lookup unless a test overrides this.
    repo.get_by_email.return_value = None
    return repo


@pytest.fixture
def jwt_provider() -> JWTProvider:
    return JWTProvider()


@pytest.fixture
def auth_manager(
    mock_user_repo: AsyncMock,
    jwt_provider: JWTProvider,
    mock_user_details_repo: AsyncMock,
) -> AuthManager:
    return AuthManager(
        user_repository=mock_user_repo,
        jwt_provider=jwt_provider,
        user_details_repository=mock_user_details_repo,
    )


@pytest.fixture
def active_user() -> User:
    # is_validate_ad=False keeps login on the local bcrypt path; with the
    # default (True) these unit tests would call the external Darwin AD service.
    return User(
        id=1,
        username="activeuser",
        password_hash=hash_password("ValidPass123!"),
        is_active=True,
        is_blocked=False,
        is_validate_ad=False,
    )


class TestLoginSuccess:
    @pytest.mark.asyncio
    async def test_login_success(
        self, auth_manager: AuthManager, mock_user_repo: AsyncMock, active_user: User
    ) -> None:
        """Valid credentials for an active, unblocked user should return tokens."""
        mock_user_repo.get_by_username.return_value = active_user

        result = await auth_manager.login("activeuser", "ValidPass123!")

        assert result.access_token
        assert result.refresh_token
        assert result.token_type == "Bearer"
        assert result.expires_in > 0


class TestLoginInvalidPassword:
    @pytest.mark.asyncio
    async def test_login_wrong_password(
        self, auth_manager: AuthManager, mock_user_repo: AsyncMock, active_user: User
    ) -> None:
        """Wrong password should raise InvalidCredentialsError."""
        mock_user_repo.get_by_username.return_value = active_user

        with pytest.raises(InvalidCredentialsError):
            await auth_manager.login("activeuser", "WrongPassword!")


class TestLoginUserNotFound:
    @pytest.mark.asyncio
    async def test_login_user_not_found(
        self, auth_manager: AuthManager, mock_user_repo: AsyncMock
    ) -> None:
        """Non-existent user should raise InvalidCredentialsError."""
        mock_user_repo.get_by_username.return_value = None

        with pytest.raises(InvalidCredentialsError):
            await auth_manager.login("ghost", "anypass")


class TestLoginInactiveUser:
    @pytest.mark.asyncio
    async def test_login_inactive_user(
        self, auth_manager: AuthManager, mock_user_repo: AsyncMock
    ) -> None:
        """Inactive user should raise UserInactiveError."""
        user = User(
            id=1,
            username="inactiveuser",
            password_hash=hash_password("ValidPass123!"),
            is_active=False,
            is_blocked=False,
            is_validate_ad=False,
        )
        mock_user_repo.get_by_username.return_value = user

        with pytest.raises(UserInactiveError):
            await auth_manager.login("inactiveuser", "ValidPass123!")


class TestLoginBlockedUser:
    @pytest.mark.asyncio
    async def test_login_blocked_user(
        self, auth_manager: AuthManager, mock_user_repo: AsyncMock
    ) -> None:
        """Blocked user should raise UserBlockedError."""
        user = User(
            id=1,
            username="blockeduser",
            password_hash=hash_password("ValidPass123!"),
            is_active=True,
            is_blocked=True,
            is_validate_ad=False,
        )
        mock_user_repo.get_by_username.return_value = user

        with pytest.raises(UserBlockedError):
            await auth_manager.login("blockeduser", "ValidPass123!")


class TestRefreshToken:
    @pytest.mark.asyncio
    async def test_refresh_success(
        self,
        auth_manager: AuthManager,
        mock_user_repo: AsyncMock,
        active_user: User,
        jwt_provider: JWTProvider,
    ) -> None:
        """Valid refresh token should return new access token."""
        mock_user_repo.get_by_username.return_value = active_user
        refresh = jwt_provider.create_refresh_token(active_user.username, active_user.id)

        result = await auth_manager.refresh(refresh)

        assert result.access_token
        assert result.token_type == "Bearer"

    @pytest.mark.asyncio
    async def test_refresh_invalid_token(
        self, auth_manager: AuthManager, mock_user_repo: AsyncMock
    ) -> None:
        """Invalid refresh token should raise AuthenticationError."""
        from src.infrastructure.security.auth_manager import AuthenticationError

        with pytest.raises(AuthenticationError):
            await auth_manager.refresh("invalid.token.here")


class TestLoginViaActiveDirectory:
    """The is_validate_ad=True branch, with the external AD client mocked out."""

    @staticmethod
    def _ad_user() -> User:
        return User(
            id=1,
            username="aduser",
            password_hash="",  # unused on the AD path
            is_active=True,
            is_blocked=False,
            is_validate_ad=True,
        )

    @pytest.mark.asyncio
    async def test_ad_user_authenticates_via_ad_service(
        self, auth_manager: AuthManager, mock_user_repo: AsyncMock
    ) -> None:
        """An AD-backed user is validated by the AD service, not the local hash."""
        mock_user_repo.get_by_username.return_value = self._ad_user()

        ad_client = AsyncMock()
        ad_client.validate_credentials.return_value = MagicMock(is_valid_user=True)

        with patch(
            "src.infrastructure.external.employee_ad.employee_ad_client.EmployeeADClient",
            return_value=ad_client,
        ):
            result = await auth_manager.login("aduser", "AnyPassword")

        assert result.access_token
        assert result.token_type == "Bearer"
        ad_client.validate_credentials.assert_awaited_once_with("aduser", "AnyPassword")

    @pytest.mark.asyncio
    async def test_ad_rejection_raises_invalid_credentials(
        self, auth_manager: AuthManager, mock_user_repo: AsyncMock
    ) -> None:
        """If AD says the user is invalid, login fails with InvalidCredentialsError."""
        mock_user_repo.get_by_username.return_value = self._ad_user()

        ad_client = AsyncMock()
        ad_client.validate_credentials.return_value = MagicMock(is_valid_user=False)

        with (
            patch(
                "src.infrastructure.external.employee_ad.employee_ad_client.EmployeeADClient",
                return_value=ad_client,
            ),
            pytest.raises(InvalidCredentialsError),
        ):
            await auth_manager.login("aduser", "AnyPassword")

    @pytest.mark.asyncio
    async def test_ad_outage_raises_invalid_credentials(
        self, auth_manager: AuthManager, mock_user_repo: AsyncMock
    ) -> None:
        """An AD service outage must not leak as a 500; it maps to 401."""
        from src.infrastructure.external.employee_ad.employee_ad_client import (
            EmployeeADError,
        )

        mock_user_repo.get_by_username.return_value = self._ad_user()

        ad_client = AsyncMock()
        ad_client.validate_credentials.side_effect = EmployeeADError("connection refused")

        with (
            patch(
                "src.infrastructure.external.employee_ad.employee_ad_client.EmployeeADClient",
                return_value=ad_client,
            ),
            pytest.raises(InvalidCredentialsError),
        ):
            await auth_manager.login("aduser", "AnyPassword")


class TestMicrosoftLogin:
    """
    The SSO path: a verified Microsoft email must resolve to a locally-known
    user — primarily an employee imported from AD, whose email lives on
    user_details while their username is the employee id.
    """

    @staticmethod
    def _imported_user() -> User:
        # Username is the employee id (as set by the AD import), NOT the email.
        return User(
            id=42,
            username="E12345",
            password_hash="",
            is_active=True,
            is_blocked=False,
        )

    @pytest.mark.asyncio
    async def test_resolves_imported_employee_by_user_details_email(
        self,
        auth_manager: AuthManager,
        mock_user_repo: AsyncMock,
        mock_user_details_repo: AsyncMock,
    ) -> None:
        """The AD-imported email (user_details.email) links the SSO identity."""
        user = self._imported_user()
        mock_user_details_repo.get_by_email.return_value = UserDetails(
            id=7, user_id=user.id, employee_id="E12345", email="ada@example.com"
        )
        mock_user_repo.get_by_id.return_value = user

        result = await auth_manager.microsoft_login({"mail": "Ada@Example.com"})

        assert result.access_token
        assert result.token_type == "Bearer"
        # Matched by email, resolved by user_id — never by username here.
        mock_user_details_repo.get_by_email.assert_awaited_once_with("ada@example.com")
        mock_user_repo.get_by_id.assert_awaited_once_with(user.id)
        mock_user_repo.get_by_username.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_falls_back_to_username_for_legacy_sso_user(
        self,
        auth_manager: AuthManager,
        mock_user_repo: AsyncMock,
        mock_user_details_repo: AsyncMock,
    ) -> None:
        """A user whose username IS the email (no imported profile) still works."""
        mock_user_details_repo.get_by_email.return_value = None
        mock_user_repo.get_by_username.return_value = User(
            id=5,
            username="legacy@example.com",
            password_hash="",
            is_active=True,
            is_blocked=False,
        )

        result = await auth_manager.microsoft_login(
            {"userPrincipalName": "legacy@example.com"}
        )

        assert result.access_token
        mock_user_repo.get_by_username.assert_awaited_once_with("legacy@example.com")

    @pytest.mark.asyncio
    async def test_prefers_mail_over_upn(
        self,
        auth_manager: AuthManager,
        mock_user_repo: AsyncMock,
        mock_user_details_repo: AsyncMock,
    ) -> None:
        """When both are present, `mail` is the email used for verification."""
        mock_user_repo.get_by_username.return_value = None

        with pytest.raises(SsoUserNotProvisionedError):
            await auth_manager.microsoft_login(
                {"mail": "real@example.com", "userPrincipalName": "upn@example.com"}
            )

        mock_user_details_repo.get_by_email.assert_awaited_once_with("real@example.com")

    @pytest.mark.asyncio
    async def test_missing_email_is_rejected(self, auth_manager: AuthManager) -> None:
        """A Microsoft profile with no mail/UPN cannot be verified."""
        with pytest.raises(MicrosoftEmailMissingError):
            await auth_manager.microsoft_login({"displayName": "No Email"})

    @pytest.mark.asyncio
    async def test_unprovisioned_email_is_rejected_not_auto_created(
        self,
        auth_manager: AuthManager,
        mock_user_repo: AsyncMock,
        mock_user_details_repo: AsyncMock,
    ) -> None:
        """An email matching no imported profile and no username is refused."""
        mock_user_details_repo.get_by_email.return_value = None
        mock_user_repo.get_by_username.return_value = None

        with pytest.raises(SsoUserNotProvisionedError):
            await auth_manager.microsoft_login({"mail": "stranger@example.com"})

        # The callback must never silently provision a rogue account.
        mock_user_repo.create.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_inactive_imported_user_is_rejected(
        self,
        auth_manager: AuthManager,
        mock_user_repo: AsyncMock,
        mock_user_details_repo: AsyncMock,
    ) -> None:
        user = self._imported_user()
        user.is_active = False
        mock_user_details_repo.get_by_email.return_value = UserDetails(
            id=7, user_id=user.id, employee_id="E12345", email="ada@example.com"
        )
        mock_user_repo.get_by_id.return_value = user

        with pytest.raises(UserInactiveError):
            await auth_manager.microsoft_login({"mail": "ada@example.com"})

    @pytest.mark.asyncio
    async def test_blocked_imported_user_is_rejected(
        self,
        auth_manager: AuthManager,
        mock_user_repo: AsyncMock,
        mock_user_details_repo: AsyncMock,
    ) -> None:
        user = self._imported_user()
        user.is_blocked = True
        mock_user_details_repo.get_by_email.return_value = UserDetails(
            id=7, user_id=user.id, employee_id="E12345", email="ada@example.com"
        )
        mock_user_repo.get_by_id.return_value = user

        with pytest.raises(UserBlockedError):
            await auth_manager.microsoft_login({"mail": "ada@example.com"})
