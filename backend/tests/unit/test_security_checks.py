"""
Unit tests for the startup security checks.

A deployment that forgets to override the JWT secret signs every token with a string that is
public in this repository, so the process must refuse to start. Local development opts out
with DEBUG=true.
"""

import pytest
from structlog.testing import capture_logs

from src.config.security_checks import (
    KNOWN_PLACEHOLDER_SECRETS,
    MIN_JWT_SECRET_LENGTH,
    InsecureConfigurationError,
    validate_security_configuration,
)
from src.config.settings import Settings

STRONG_SECRET = "k3Jx9vQ2mZ7pLw4Rt8Yb6Nc1Ud5Hf0Sa3Gi7Oe2Xz9Vq"


def make_settings(**overrides: object) -> Settings:
    """Settings built from explicit values only: never from the developer's `.env`."""
    values: dict[str, object] = {
        "DEBUG": False,
        "JWT_SECRET_KEY": STRONG_SECRET,
        "COOKIE_SECURE": True,
    }
    values.update(overrides)
    return Settings(_env_file=None, **values)  # type: ignore[arg-type]


class TestJwtSecret:
    def test_a_strong_secret_passes(self) -> None:
        validate_security_configuration(make_settings())

    @pytest.mark.parametrize("placeholder", sorted(KNOWN_PLACEHOLDER_SECRETS))
    def test_a_placeholder_from_the_repository_is_refused(self, placeholder: str) -> None:
        with pytest.raises(InsecureConfigurationError, match="placeholder"):
            validate_security_configuration(make_settings(JWT_SECRET_KEY=placeholder))

    def test_the_default_setting_is_itself_a_known_placeholder(self) -> None:
        """So forgetting to set the variable at all is caught, not just copying the example."""
        default = Settings(_env_file=None).JWT_SECRET_KEY

        assert default in KNOWN_PLACEHOLDER_SECRETS

    def test_the_example_env_file_value_is_a_known_placeholder(self) -> None:
        from pathlib import Path

        example = (Path(__file__).resolve().parents[2] / ".env.example").read_text(
            encoding="utf-8", errors="ignore"
        )
        line = next(entry for entry in example.splitlines() if entry.startswith("JWT_SECRET_KEY="))

        assert line.split("=", 1)[1].strip() in KNOWN_PLACEHOLDER_SECRETS

    def test_a_short_secret_is_refused(self) -> None:
        with pytest.raises(InsecureConfigurationError, match="shorter"):
            validate_security_configuration(
                make_settings(JWT_SECRET_KEY="x" * (MIN_JWT_SECRET_LENGTH - 1))
            )

    def test_a_secret_of_exactly_the_minimum_length_passes(self) -> None:
        validate_security_configuration(make_settings(JWT_SECRET_KEY="x" * MIN_JWT_SECRET_LENGTH))

    def test_length_is_counted_in_bytes_not_characters(self) -> None:
        # 20 characters but 40 bytes: long enough as a key, and must not be refused as short.
        validate_security_configuration(make_settings(JWT_SECRET_KEY="é" * 20))

    def test_the_message_says_how_to_fix_it(self) -> None:
        with pytest.raises(InsecureConfigurationError) as raised:
            validate_security_configuration(
                make_settings(JWT_SECRET_KEY="change-me-in-production-use-strong-secret")
            )

        assert "JWT_SECRET_KEY" in str(raised.value)
        assert "DEBUG=true" in str(raised.value)


class TestDebugMode:
    def test_debug_lets_a_developer_run_with_the_placeholder(self) -> None:
        validate_security_configuration(
            make_settings(DEBUG=True, JWT_SECRET_KEY="change-me-in-production-use-strong-secret")
        )

    def test_debug_says_that_the_checks_were_skipped(self) -> None:
        with capture_logs() as logs:
            validate_security_configuration(make_settings(DEBUG=True))

        assert [entry["event"] for entry in logs] == ["security_checks_skipped"]


class TestCookieSecure:
    def test_insecure_cookies_warn_but_do_not_stop_startup(self) -> None:
        with capture_logs() as logs:
            validate_security_configuration(make_settings(COOKIE_SECURE=False))

        warnings = [e for e in logs if e["event"] == "cookie_secure_disabled"]
        assert len(warnings) == 1
        assert warnings[0]["log_level"] == "warning"

    def test_secure_cookies_are_silent(self) -> None:
        with capture_logs() as logs:
            validate_security_configuration(make_settings(COOKIE_SECURE=True))

        assert logs == []
