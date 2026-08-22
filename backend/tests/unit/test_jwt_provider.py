"""
Unit tests for JWT token creation, validation, and expiration.
"""

from datetime import UTC, datetime, timedelta
from unittest.mock import patch
from uuid import uuid4

import pytest

from src.config.settings import settings
from src.infrastructure.security.jwt_provider import JWTProvider


class TestJWTProvider:
    """JWT provider unit tests."""

    def setup_method(self) -> None:
        self.jwt = JWTProvider()
        self.username = "testuser"
        self.user_id = uuid4()

    def test_create_access_token(self) -> None:
        """Access token should be a non-empty string."""
        token = self.jwt.create_access_token(self.username, self.user_id)
        assert isinstance(token, str)
        assert len(token) > 0

    def test_create_refresh_token(self) -> None:
        """Refresh token should be a non-empty string."""
        token = self.jwt.create_refresh_token(self.username, self.user_id)
        assert isinstance(token, str)
        assert len(token) > 0

    def test_verify_access_token(self) -> None:
        """Valid access token should decode correctly."""
        token = self.jwt.create_access_token(self.username, self.user_id)
        payload = self.jwt.verify_token(token, expected_type="access")

        assert payload.sub == self.username
        assert payload.user_id == str(self.user_id)
        assert payload.token_type == "access"

    def test_verify_refresh_token(self) -> None:
        """Valid refresh token should decode correctly."""
        token = self.jwt.create_refresh_token(self.username, self.user_id)
        payload = self.jwt.verify_token(token, expected_type="refresh")

        assert payload.sub == self.username
        assert payload.token_type == "refresh"

    def test_wrong_token_type_raises(self) -> None:
        """Verifying access token as refresh should raise ValueError."""
        token = self.jwt.create_access_token(self.username, self.user_id)

        with pytest.raises(ValueError, match="Invalid token type"):
            self.jwt.verify_token(token, expected_type="refresh")

    def test_expired_token_raises(self) -> None:
        """Expired token should raise an exception."""
        with patch(
            "src.config.settings.settings.ACCESS_TOKEN_EXPIRE_MINUTES", 0
        ):
            jwt = JWTProvider()
            # Create token that expires immediately
            jwt._access_expire_minutes = 0

        # Create a token with 0 minutes expiry won't actually expire instantly
        # due to datetime precision, so we test with decode instead
        from datetime import datetime, timedelta

        import jwt as pyjwt

        expired_payload = {
            "sub": self.username,
            "user_id": str(self.user_id),
            "token_type": "access",
            "iat": datetime.now(UTC) - timedelta(hours=2),
            "exp": datetime.now(UTC) - timedelta(hours=1),
        }
        # Sign with the configured secret, not a hardcoded default. Previously
        # this used the default secret while settings loads one from .env, so
        # verification failed on the signature and never reached the expiry
        # check — `pytest.raises(Exception)` hid that the test proved nothing
        # about expiry.
        expired_token = pyjwt.encode(
            expired_payload,
            settings.JWT_SECRET_KEY,
            algorithm=settings.JWT_ALGORITHM,
        )

        with pytest.raises(pyjwt.ExpiredSignatureError):
            self.jwt.verify_token(expired_token, expected_type="access")

    def test_token_signed_with_wrong_secret_is_rejected(self) -> None:
        """A token signed with a different key must fail signature verification."""
        import jwt as pyjwt

        forged = pyjwt.encode(
            {
                "sub": self.username,
                "user_id": str(self.user_id),
                "token_type": "access",
                "iat": datetime.now(UTC),
                "exp": datetime.now(UTC) + timedelta(hours=1),
            },
            "not-the-real-signing-key",
            algorithm=settings.JWT_ALGORITHM,
        )

        with pytest.raises(pyjwt.InvalidSignatureError):
            self.jwt.verify_token(forged, expected_type="access")

    def test_decode_token_returns_dict(self) -> None:
        """decode_token should return raw payload dictionary."""
        token = self.jwt.create_access_token(self.username, self.user_id)
        payload = self.jwt.decode_token(token)

        assert isinstance(payload, dict)
        assert payload["sub"] == self.username
        assert payload["token_type"] == "access"
