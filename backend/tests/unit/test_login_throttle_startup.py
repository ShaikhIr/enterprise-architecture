"""
Tests for the startup report on login throttling.

The line that matters is the warning about TRUSTED_PROXY_HOPS: left at 0 behind a reverse
proxy, every user shares one per-IP budget, and nothing else will tell an operator so.
"""

from collections.abc import MutableMapping
from typing import Any

import pytest
import structlog

from src.config.settings import settings
from src.main import log_login_throttle_configuration


def _events() -> list[MutableMapping[str, Any]]:
    with structlog.testing.capture_logs() as logs:
        log_login_throttle_configuration()
    return logs


@pytest.fixture
def production_like(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "LOGIN_THROTTLE_ENABLED", True)
    monkeypatch.setattr(settings, "COOKIE_SECURE", True)
    monkeypatch.setattr(settings, "TRUSTED_PROXY_HOPS", 0)


class TestStartupReport:
    def test_the_active_configuration_is_reported(
        self, production_like: None, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(settings, "TRUSTED_PROXY_HOPS", 2)

        configured = next(e for e in _events() if e["event"] == "login_throttle_configured")

        assert configured["trusted_proxy_hops"] == 2
        assert configured["lockout_seconds"] == settings.LOGIN_LOCKOUT_SECONDS
        assert configured["familiar_ip_ttl_seconds"] == settings.LOGIN_FAMILIAR_IP_TTL_SECONDS
        assert configured["max_attempts_per_account_ip"] == (
            settings.LOGIN_MAX_ATTEMPTS_PER_ACCOUNT_IP
        )

    def test_unset_proxy_hops_in_a_production_like_setup_is_a_warning(
        self, production_like: None
    ) -> None:
        events = _events()

        warning = next(e for e in events if e["event"] == "login_throttle_proxy_hops_unset")
        assert warning["log_level"] == "warning"
        assert "TRUSTED_PROXY_HOPS" in str(warning["detail"])

    def test_configured_proxy_hops_raise_no_warning(
        self, production_like: None, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(settings, "TRUSTED_PROXY_HOPS", 1)

        assert all(e["log_level"] != "warning" for e in _events())

    def test_a_development_setup_is_not_nagged(
        self, production_like: None, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(settings, "COOKIE_SECURE", False)

        assert all(e["log_level"] != "warning" for e in _events())

    def test_a_disabled_throttle_is_called_out(
        self, production_like: None, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(settings, "LOGIN_THROTTLE_ENABLED", False)

        events = _events()

        assert [e["event"] for e in events] == ["login_throttle_disabled"]
        assert events[0]["log_level"] == "warning"
