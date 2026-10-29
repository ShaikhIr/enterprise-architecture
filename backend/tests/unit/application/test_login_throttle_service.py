"""
Unit tests for LoginThrottleService.

Run against a hand-written in-memory store (`login_throttle_fakes`) with a clock the test
moves by hand, so every window and lockout is exact. The store's own behaviour (and Redis's)
is covered where those live; here the subject is the policy: which attempt is refused, why,
for how long, and what is left alone.
"""

import asyncio
from dataclasses import replace

import pytest
import structlog
from login_throttle_fakes import FakeLoginAttemptStore

from src.application.services.login_throttle_service import (
    LoginAttemptTicket,
    LoginThrottledError,
    LoginThrottlePolicy,
    LoginThrottleService,
    ThrottleReason,
)

IP = "203.0.113.1"
OTHER_IP = "198.51.100.7"
FAMILIAR_TTL = 86_400

POLICY = LoginThrottlePolicy(
    window_seconds=300,
    max_attempts_per_account_ip=5,
    max_attempts_per_account=20,
    max_failures_per_ip=50,
    lockout_seconds=900,
    familiar_ip_ttl_seconds=FAMILIAR_TTL,
)


@pytest.fixture
def store() -> FakeLoginAttemptStore:
    return FakeLoginAttemptStore()


@pytest.fixture
def service(store: FakeLoginAttemptStore) -> LoginThrottleService:
    return LoginThrottleService(store, POLICY)


async def _fail_n_times(
    service: LoginThrottleService, username: str, ip: str, times: int
) -> None:
    """Attempt and fail, as a guesser would."""
    for _ in range(times):
        ticket = await service.begin_attempt(username, ip)
        await service.record_failure(ticket)


async def _refusal(service: LoginThrottleService, username: str, ip: str) -> LoginThrottledError:
    with pytest.raises(LoginThrottledError) as caught:
        await service.begin_attempt(username, ip)
    return caught.value


async def _log_in(service: LoginThrottleService, username: str, ip: str) -> None:
    """A successful login, which is what makes an address familiar to the account."""
    ticket = await service.begin_attempt(username, ip)
    await service.record_success(ticket)


async def _lock_out_strangers(service: LoginThrottleService, username: str) -> None:
    """
    Guess from fresh addresses, one attempt each, until the account locks for strangers.

    Stops at the attempt that starts the lock rather than assuming how many slots were
    already used, so it works after earlier logins have used some.
    """
    for n in range(POLICY.max_attempts_per_account + 1):
        try:
            ticket = await service.begin_attempt(username, f"192.0.2.{n + 1}")
        except LoginThrottledError as refused:
            assert refused.reason is ThrottleReason.ACCOUNT_UNFAMILIAR_LOCKOUT
            return
        await service.record_failure(ticket)
    raise AssertionError("the account never locked for strangers")


class TestAccountFromOneIp:
    async def test_attempts_up_to_the_limit_are_admitted(
        self, service: LoginThrottleService
    ) -> None:
        for _ in range(POLICY.max_attempts_per_account_ip):
            assert isinstance(await service.begin_attempt("alice", IP), LoginAttemptTicket)

    async def test_the_next_attempt_starts_a_lockout(
        self, service: LoginThrottleService
    ) -> None:
        await _fail_n_times(service, "alice", IP, POLICY.max_attempts_per_account_ip)

        refused = await _refusal(service, "alice", IP)

        assert refused.reason is ThrottleReason.ACCOUNT_IP_LOCKOUT
        assert refused.lockout_started is True
        assert refused.retry_after_seconds == POLICY.lockout_seconds

    async def test_later_attempts_are_refused_without_restarting_the_lockout(
        self, service: LoginThrottleService
    ) -> None:
        await _fail_n_times(service, "alice", IP, POLICY.max_attempts_per_account_ip)
        await _refusal(service, "alice", IP)

        refused = await _refusal(service, "alice", IP)

        assert refused.reason is ThrottleReason.ACCOUNT_IP_LOCKOUT
        assert refused.lockout_started is False

    async def test_a_lockout_is_not_extended_by_attempts_made_during_it(
        self, service: LoginThrottleService, store: FakeLoginAttemptStore
    ) -> None:
        await _fail_n_times(service, "alice", IP, POLICY.max_attempts_per_account_ip)
        await _refusal(service, "alice", IP)

        store.advance(600)
        midway = await _refusal(service, "alice", IP)
        store.advance(301)  # now past the original 900 s, however often we knocked

        assert midway.retry_after_seconds == 300
        assert isinstance(await service.begin_attempt("alice", IP), LoginAttemptTicket)

    async def test_retry_after_counts_down(
        self, service: LoginThrottleService, store: FakeLoginAttemptStore
    ) -> None:
        await _fail_n_times(service, "alice", IP, POLICY.max_attempts_per_account_ip)
        await _refusal(service, "alice", IP)

        store.advance(100)

        assert (await _refusal(service, "alice", IP)).retry_after_seconds == 800

    async def test_the_budget_is_fresh_once_the_lockout_has_passed(
        self, service: LoginThrottleService, store: FakeLoginAttemptStore
    ) -> None:
        await _fail_n_times(service, "alice", IP, POLICY.max_attempts_per_account_ip)
        await _refusal(service, "alice", IP)

        store.advance(POLICY.lockout_seconds + 1)

        for _ in range(POLICY.max_attempts_per_account_ip):
            await service.begin_attempt("alice", IP)

    async def test_the_same_account_from_another_ip_is_not_locked(
        self, service: LoginThrottleService
    ) -> None:
        """Anyone who knows `admin` must not be able to lock the real admin out."""
        await _fail_n_times(service, "admin", IP, POLICY.max_attempts_per_account_ip)
        await _refusal(service, "admin", IP)

        assert isinstance(await service.begin_attempt("admin", OTHER_IP), LoginAttemptTicket)

    async def test_another_account_from_the_same_ip_is_not_locked(
        self, service: LoginThrottleService
    ) -> None:
        await _fail_n_times(service, "alice", IP, POLICY.max_attempts_per_account_ip)
        await _refusal(service, "alice", IP)

        assert isinstance(await service.begin_attempt("bob", IP), LoginAttemptTicket)

    async def test_attempts_in_one_window_do_not_carry_into_the_next(
        self, service: LoginThrottleService, store: FakeLoginAttemptStore
    ) -> None:
        await _fail_n_times(service, "alice", IP, POLICY.max_attempts_per_account_ip)

        store.advance(POLICY.window_seconds + 1)

        for _ in range(POLICY.max_attempts_per_account_ip):
            await service.begin_attempt("alice", IP)


class TestAccountFromManyIps:
    """Strangers: addresses the account has no successful login from. See TestFamiliarAddresses."""

    async def test_a_spread_out_guesser_is_capped_across_addresses(
        self, service: LoginThrottleService
    ) -> None:
        """Each address stays under its own limit; together they reach the account's."""
        per_ip = POLICY.max_attempts_per_account_ip
        addresses = [f"192.0.2.{n}" for n in range(POLICY.max_attempts_per_account // per_ip)]
        for address in addresses:
            await _fail_n_times(service, "alice", address, per_ip)

        refused = await _refusal(service, "alice", "192.0.2.200")

        assert refused.reason is ThrottleReason.ACCOUNT_UNFAMILIAR_LOCKOUT
        assert refused.lockout_started is True

    async def test_once_the_account_is_locked_every_unfamiliar_address_is_refused(
        self, service: LoginThrottleService
    ) -> None:
        await _lock_out_strangers(service, "alice")

        refused = await _refusal(service, "alice", "192.0.2.201")

        assert refused.reason is ThrottleReason.ACCOUNT_UNFAMILIAR_LOCKOUT
        assert refused.lockout_started is False
        assert refused.retry_after_seconds == POLICY.lockout_seconds

    async def test_the_longest_remaining_lockout_is_the_one_reported(
        self, service: LoginThrottleService, store: FakeLoginAttemptStore
    ) -> None:
        """Locked for this IP first, then for the whole account: Retry-After is the later."""
        per_ip = POLICY.max_attempts_per_account_ip
        await _fail_n_times(service, "alice", IP, per_ip)
        await _refusal(service, "alice", IP)  # account+IP lock: 900 s from t=0
        store.advance(600)  # 300 s of it left; the 300 s counting window has long passed
        for n in range(POLICY.max_attempts_per_account // per_ip):
            await _fail_n_times(service, "alice", f"192.0.2.{n}", per_ip)
        await _refusal(service, "alice", "192.0.2.99")  # account lock: 900 s from t=600

        refused = await _refusal(service, "alice", IP)

        # Both locks apply to this address. The reply must be the one that lasts longer.
        assert refused.reason is ThrottleReason.ACCOUNT_UNFAMILIAR_LOCKOUT
        assert refused.retry_after_seconds == POLICY.lockout_seconds


class TestFamiliarAddresses:
    """
    A spread-out attack must not be able to lock the real user out of their usual network.

    An address is familiar to an account once a login from it has succeeded. The cap on
    attempts from strangers neither counts nor locks familiar addresses.
    """

    async def test_a_familiar_address_still_gets_in_while_strangers_are_locked_out(
        self, service: LoginThrottleService
    ) -> None:
        await _log_in(service, "alice", IP)
        await _lock_out_strangers(service, "alice")

        assert isinstance(await service.begin_attempt("alice", IP), LoginAttemptTicket)

    async def test_strangers_stay_locked_out(self, service: LoginThrottleService) -> None:
        """The exemption must not weaken the cap on a guesser who has no familiar address."""
        await _log_in(service, "alice", IP)
        await _lock_out_strangers(service, "alice")

        refused = await _refusal(service, "alice", OTHER_IP)

        assert refused.reason is ThrottleReason.ACCOUNT_UNFAMILIAR_LOCKOUT
        assert refused.retry_after_seconds == POLICY.lockout_seconds

    async def test_a_familiar_address_is_still_limited_to_its_own_budget(
        self, service: LoginThrottleService
    ) -> None:
        """Exempt from the cap on strangers, not licensed to guess without limit."""
        await _log_in(service, "alice", IP)
        await _lock_out_strangers(service, "alice")
        await _fail_n_times(service, "alice", IP, POLICY.max_attempts_per_account_ip)

        refused = await _refusal(service, "alice", IP)

        assert refused.reason is ThrottleReason.ACCOUNT_IP_LOCKOUT

    async def test_a_familiar_address_is_still_subject_to_the_address_failure_limit(
        self, service: LoginThrottleService
    ) -> None:
        await _log_in(service, "alice", IP)
        for n in range(POLICY.max_failures_per_ip):
            await _fail_n_times(service, f"user{n}", IP, 1)

        refused = await _refusal(service, "alice", IP)

        assert refused.reason is ThrottleReason.IP_LIMIT

    async def test_failures_from_familiar_addresses_are_counted_separately(
        self, service: LoginThrottleService
    ) -> None:
        """The owner's typos on their usual networks must not lock out a trip."""
        familiar = [f"203.0.113.{n}" for n in range(10, 14)]
        for address in familiar:
            await _log_in(service, "alice", address)
        for address in familiar:  # 4 x 5 = 20 failures: the cap on strangers, if they counted
            await _fail_n_times(service, "alice", address, POLICY.max_attempts_per_account_ip)

        assert isinstance(await service.begin_attempt("alice", OTHER_IP), LoginAttemptTicket)

    async def test_the_owners_login_does_not_refill_a_spread_out_guessers_budget(
        self, service: LoginThrottleService
    ) -> None:
        per_ip = POLICY.max_attempts_per_account_ip
        await _log_in(service, "alice", IP)  # a stranger then: 1 of the 20 used
        for n in range(3):
            await _fail_n_times(service, "alice", f"192.0.2.{n + 1}", per_ip)  # 16 of 20
        await _log_in(service, "alice", IP)  # the owner again, from a familiar address
        await _fail_n_times(service, "alice", "192.0.2.50", 4)  # 20 of 20

        refused = await _refusal(service, "alice", "192.0.2.51")

        # Had the owner's login cleared the count, this address would have had a fresh budget.
        assert refused.reason is ThrottleReason.ACCOUNT_UNFAMILIAR_LOCKOUT

    async def test_an_address_is_familiar_to_one_account_only(
        self, service: LoginThrottleService
    ) -> None:
        await _log_in(service, "bob", IP)
        await _lock_out_strangers(service, "alice")

        refused = await _refusal(service, "alice", IP)

        assert refused.reason is ThrottleReason.ACCOUNT_UNFAMILIAR_LOCKOUT

    async def test_a_failed_login_does_not_make_an_address_familiar(
        self, service: LoginThrottleService
    ) -> None:
        """Otherwise a guesser could earn the exemption by failing."""
        await _fail_n_times(service, "alice", IP, 1)
        await _lock_out_strangers(service, "alice")

        refused = await _refusal(service, "alice", IP)

        assert refused.reason is ThrottleReason.ACCOUNT_UNFAMILIAR_LOCKOUT

    async def test_an_address_is_forgotten_a_lifetime_after_its_last_login(
        self, service: LoginThrottleService, store: FakeLoginAttemptStore
    ) -> None:
        await _log_in(service, "alice", IP)
        store.advance(FAMILIAR_TTL + 1)
        await _lock_out_strangers(service, "alice")

        refused = await _refusal(service, "alice", IP)

        assert refused.reason is ThrottleReason.ACCOUNT_UNFAMILIAR_LOCKOUT

    async def test_each_login_restarts_the_lifetime(
        self, service: LoginThrottleService, store: FakeLoginAttemptStore
    ) -> None:
        await _log_in(service, "alice", IP)
        store.advance(FAMILIAR_TTL - 100)
        await _log_in(service, "alice", IP)
        store.advance(200)  # past the first lifetime, inside the second
        await _lock_out_strangers(service, "alice")

        assert isinstance(await service.begin_attempt("alice", IP), LoginAttemptTicket)

    async def test_a_zero_lifetime_turns_the_exemption_off(
        self, store: FakeLoginAttemptStore
    ) -> None:
        off = LoginThrottleService(store, replace(POLICY, familiar_ip_ttl_seconds=0))
        await _log_in(off, "alice", IP)
        await _lock_out_strangers(off, "alice")

        refused = await _refusal(off, "alice", IP)

        assert refused.reason is ThrottleReason.ACCOUNT_UNFAMILIAR_LOCKOUT
        assert not [key for key in store.live_keys() if key.startswith("login:familiar:")]

    async def test_an_address_that_could_not_be_resolved_is_never_remembered(
        self, service: LoginThrottleService, store: FakeLoginAttemptStore
    ) -> None:
        """Many unrelated clients can end up under 'unknown'; none of them is familiar."""
        await _log_in(service, "alice", "")
        await _lock_out_strangers(service, "alice")

        refused = await _refusal(service, "alice", "")

        assert refused.reason is ThrottleReason.ACCOUNT_UNFAMILIAR_LOCKOUT
        assert not [key for key in store.live_keys() if key.startswith("login:familiar:")]

    async def test_the_marker_does_not_contain_the_username(
        self, service: LoginThrottleService, store: FakeLoginAttemptStore
    ) -> None:
        await _log_in(service, "alice.smith@example.com", IP)

        assert [key for key in store.live_keys() if key.startswith("login:familiar:")]
        assert not any("alice" in key for key in store.live_keys())

    async def test_a_burst_from_a_familiar_address_is_still_capped(
        self, service: LoginThrottleService
    ) -> None:
        await _log_in(service, "alice", IP)

        outcomes = await asyncio.gather(
            *(service.begin_attempt("alice", IP) for _ in range(50)), return_exceptions=True
        )

        admitted = [o for o in outcomes if isinstance(o, LoginAttemptTicket)]
        assert len(admitted) == POLICY.max_attempts_per_account_ip


class TestFailuresFromOneIp:
    async def test_an_address_spraying_many_usernames_is_stopped(
        self, service: LoginThrottleService
    ) -> None:
        for n in range(POLICY.max_failures_per_ip):
            await _fail_n_times(service, f"user{n}", IP, 1)

        refused = await _refusal(service, "someone-new", IP)

        assert refused.reason is ThrottleReason.IP_LIMIT
        assert refused.lockout_started is False

    async def test_retry_after_is_the_rest_of_the_window(
        self, service: LoginThrottleService, store: FakeLoginAttemptStore
    ) -> None:
        for n in range(POLICY.max_failures_per_ip):
            await _fail_n_times(service, f"user{n}", IP, 1)
        store.advance(120)

        refused = await _refusal(service, "someone-new", IP)

        assert refused.retry_after_seconds == POLICY.window_seconds - 120

    async def test_another_address_is_unaffected(self, service: LoginThrottleService) -> None:
        for n in range(POLICY.max_failures_per_ip):
            await _fail_n_times(service, f"user{n}", IP, 1)

        assert isinstance(await service.begin_attempt("user0", OTHER_IP), LoginAttemptTicket)

    async def test_successful_logins_never_use_up_the_address_budget(
        self, service: LoginThrottleService
    ) -> None:
        """An office behind one address logs in all morning; that must not lock it."""
        for n in range(POLICY.max_failures_per_ip * 3):
            ticket = await service.begin_attempt(f"user{n}", IP)
            await service.record_success(ticket)

        assert isinstance(await service.begin_attempt("anyone", IP), LoginAttemptTicket)

    async def test_the_budget_returns_when_the_window_ends(
        self, service: LoginThrottleService, store: FakeLoginAttemptStore
    ) -> None:
        for n in range(POLICY.max_failures_per_ip):
            await _fail_n_times(service, f"user{n}", IP, 1)
        store.advance(POLICY.window_seconds + 1)

        assert isinstance(await service.begin_attempt("anyone", IP), LoginAttemptTicket)


class TestSuccess:
    async def test_a_successful_login_clears_earlier_failures(
        self, service: LoginThrottleService
    ) -> None:
        await _fail_n_times(service, "alice", IP, POLICY.max_attempts_per_account_ip - 1)
        ticket = await service.begin_attempt("alice", IP)
        await service.record_success(ticket)

        # A full budget again, not the single attempt that was left.
        for _ in range(POLICY.max_attempts_per_account_ip):
            await service.begin_attempt("alice", IP)

    async def test_it_leaves_the_address_failure_count_alone(
        self, service: LoginThrottleService, store: FakeLoginAttemptStore
    ) -> None:
        await _fail_n_times(service, "alice", IP, 3)
        ticket = await service.begin_attempt("bob", IP)
        await service.record_success(ticket)

        assert store.count(f"login:count:ip:{IP}") == 3

    async def test_it_does_not_clear_another_accounts_failures(
        self, service: LoginThrottleService
    ) -> None:
        """Logging in as yourself must not reset the count against someone else's account."""
        await _fail_n_times(service, "victim", IP, POLICY.max_attempts_per_account_ip)
        ticket = await service.begin_attempt("attacker", IP)
        await service.record_success(ticket)

        assert (await _refusal(service, "victim", IP)).reason is (
            ThrottleReason.ACCOUNT_IP_LOCKOUT
        )


class TestAccountNormalisation:
    async def test_spelling_variants_share_one_budget(
        self, service: LoginThrottleService
    ) -> None:
        variants = ["admin", "Admin", "ADMIN", " admin ", "ａｄｍｉｎ"]  # last one is full-width
        for variant in variants:
            await service.begin_attempt(variant, IP)

        refused = await _refusal(service, "AdMiN", IP)

        # Five variants used the whole per-address budget, so the sixth spelling is refused.
        assert refused.reason is ThrottleReason.ACCOUNT_IP_LOCKOUT

    async def test_the_username_is_not_stored_in_the_clear(
        self, service: LoginThrottleService, store: FakeLoginAttemptStore
    ) -> None:
        await service.begin_attempt("alice.smith@example.com", IP)

        assert store.live_keys()
        assert not any("alice" in key for key in store.live_keys())

    async def test_accounts_that_do_not_exist_are_counted_like_any_other(
        self, service: LoginThrottleService
    ) -> None:
        """The service never learns whether an account exists, so it cannot treat them apart."""
        await _fail_n_times(service, "no-such-user", IP, POLICY.max_attempts_per_account_ip)

        refused = await _refusal(service, "no-such-user", IP)

        assert refused.reason is ThrottleReason.ACCOUNT_IP_LOCKOUT
        assert refused.retry_after_seconds == POLICY.lockout_seconds


class TestConcurrentAttempts:
    async def test_a_burst_admits_no_more_than_the_limit(
        self, service: LoginThrottleService
    ) -> None:
        """50 guesses in flight at once: only the limit's worth may ever be evaluated."""
        outcomes = await asyncio.gather(
            *(service.begin_attempt("alice", IP) for _ in range(50)), return_exceptions=True
        )

        admitted = [o for o in outcomes if isinstance(o, LoginAttemptTicket)]
        refused = [o for o in outcomes if isinstance(o, LoginThrottledError)]
        assert len(admitted) == POLICY.max_attempts_per_account_ip
        assert len(refused) == 50 - POLICY.max_attempts_per_account_ip

    async def test_exactly_one_request_in_a_burst_reports_the_lockout(
        self, service: LoginThrottleService
    ) -> None:
        """The audit entry is written by whoever sees `lockout_started`, so it must be one."""
        outcomes = await asyncio.gather(
            *(service.begin_attempt("alice", IP) for _ in range(50)), return_exceptions=True
        )

        started = [
            o for o in outcomes if isinstance(o, LoginThrottledError) and o.lockout_started
        ]
        assert len(started) == 1


class TestDisabled:
    async def test_nothing_is_refused_and_nothing_is_stored(
        self, store: FakeLoginAttemptStore
    ) -> None:
        service = LoginThrottleService(store, replace(POLICY, enabled=False))

        for _ in range(POLICY.max_attempts_per_account_ip * 10):
            ticket = await service.begin_attempt("alice", IP)
            await service.record_failure(ticket)
            await service.record_success(ticket)

        assert store.live_keys() == []


class TestMonitoring:
    async def test_starting_a_lockout_is_logged_once_without_secrets(
        self, service: LoginThrottleService
    ) -> None:
        with structlog.testing.capture_logs() as logs:
            await _fail_n_times(service, "alice", IP, POLICY.max_attempts_per_account_ip)
            await _refusal(service, "alice", IP)  # starts it
            await _refusal(service, "alice", IP)  # already locked

        started = [entry for entry in logs if entry["event"] == "login_lockout_started"]
        assert len(started) == 1
        assert started[0]["account"] == "alice"
        assert started[0]["client_ip"] == IP
        assert started[0]["log_level"] == "warning"

    async def test_reaching_the_address_limit_is_logged(
        self, service: LoginThrottleService
    ) -> None:
        with structlog.testing.capture_logs() as logs:
            for n in range(POLICY.max_failures_per_ip):
                await _fail_n_times(service, f"user{n}", IP, 1)

        assert [e["event"] for e in logs].count("login_ip_limit_reached") == 1

    async def test_a_hostile_username_cannot_forge_log_lines(
        self, service: LoginThrottleService
    ) -> None:
        await _fail_n_times(service, "bob\nINFO fake entry", IP, POLICY.max_attempts_per_account_ip)

        refused = await _refusal(service, "bob\nINFO fake entry", IP)

        assert "\n" not in refused.account
        assert len(refused.account) <= 64
