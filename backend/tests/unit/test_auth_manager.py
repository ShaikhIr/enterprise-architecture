"""
Unit tests for Authentication Manager.
Tests login flows: success, invalid password, inactive user, blocked user.
"""

from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest

from src.domain.entities.user import User
from src.infrastructure.security.auth_manager import (
    AuthManager,
    InvalidCredentialsError,
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
def jwt_provider() -> JWTProvider:
    return JWTProvider()


@pytest.fixture
def auth_manager(mock_user_repo: AsyncMock, jwt_provider: JWTProvider) -> AuthManager:
    return AuthManager(user_repository=mock_user_repo, jwt_provider=jwt_provider)


@pytest.fixture
def active_user() -> User:
    # is_validate_ad=False keeps login on the local bcrypt path; with the
    # default (True) these unit tests would call the external Darwin AD service.
    return User(
        id=uuid4(),
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
            id=uuid4(),
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
            id=uuid4(),
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
            id=uuid4(),
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
