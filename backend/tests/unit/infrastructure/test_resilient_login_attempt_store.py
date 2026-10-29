"""
Unit tests for ResilientLoginAttemptStore.

Login has to keep working, and keep being protected, while Redis is down. The wrapper's job
is to degrade quietly and not to make things worse on the way: no per-request wait on a dead
backend, and no log line per request.
"""

import asyncio
from collections.abc import Awaitable, Callable

import pytest
import structlog

from src.application.ports.login_attempt_store import CounterState, ILoginAttemptStore
from src.infrastructure.cache.in_memory_login_attempt_store import InMemoryLoginAttemptStore
from src.infrastructure.cache.resilient_login_attempt_store import ResilientLoginAttemptStore

RETRY_AFTER = 30.0


class Clock:
    def __init__(self) -> None:
        self.now = 1_000.0

    def __call__(self) -> float:
        return self.now

    def advance(self, seconds: float) -> None:
        self.now += seconds


class SwitchableStore(ILoginAttemptStore):
    """A real in-memory store that can be made to fail like an unreachable Redis."""

    def __init__(self, clock: Clock) -> None:
        self.inner = InMemoryLoginAttemptStore(clock=clock)
        self.failure: Exception | None = None
        self.calls = 0

    def _check(self) -> None:
        self.calls += 1
        if self.failure is not None:
            raise self.failure

    async def peek(self, key: str) -> CounterState | None:
        self._check()
        return await self.inner.peek(key)

    async def increment(self, key: str, window_seconds: int) -> CounterState:
        self._check()
        return await self.inner.increment(key, window_seconds)

    async def set_lock(self, key: str, seconds: int) -> bool:
        self._check()
        return await self.inner.set_lock(key, seconds)

    async def lock_ttl(self, key: str) -> int | None:
        self._check()
        return await self.inner.lock_ttl(key)

    async def remember(self, key: str, seconds: int) -> None:
        self._check()
        await self.inner.remember(key, seconds)

    async def is_remembered(self, key: str) -> bool:
        self._check()
        return await self.inner.is_remembered(key)

    async def delete(self, key: str) -> None:
        self._check()
        await self.inner.delete(key)


@pytest.fixture
def clock() -> Clock:
    return Clock()


@pytest.fixture
def primary(clock: Clock) -> SwitchableStore:
    return SwitchableStore(clock)


@pytest.fixture
def fallback(clock: Clock) -> SwitchableStore:
    return SwitchableStore(clock)


@pytest.fixture
def store(
    primary: SwitchableStore, fallback: SwitchableStore, clock: Clock
) -> ResilientLoginAttemptStore:
    return ResilientLoginAttemptStore(
        primary, fallback, retry_after_seconds=RETRY_AFTER, clock=clock
    )


class TestHealthyPrimary:
    async def test_everything_goes_to_the_primary(
        self, store: ResilientLoginAttemptStore, primary: SwitchableStore, fallback: SwitchableStore
    ) -> None:
        await store.increment("k", 300)
        await store.peek("k")

        assert primary.calls == 2
        assert fallback.calls == 0
        assert store.degraded is False


class TestPrimaryFailure:
    async def test_the_call_is_served_by_the_fallback_instead_of_failing(
        self, store: ResilientLoginAttemptStore, primary: SwitchableStore
    ) -> None:
        primary.failure = ConnectionError("redis is down")

        state = await store.increment("k", 300)

        assert state.count == 1
        assert store.degraded is True

    @pytest.mark.parametrize(
        "failure",
        [ConnectionError("refused"), TimeoutError("slow"), OSError("network"), RuntimeError("?")],
    )
    async def test_any_kind_of_backend_failure_degrades_rather_than_raises(
        self, store: ResilientLoginAttemptStore, primary: SwitchableStore, failure: Exception
    ) -> None:
        primary.failure = failure

        assert (await store.increment("k", 300)).count == 1

    @pytest.mark.parametrize(
        "operation",
        [
            lambda s: s.peek("k"),
            lambda s: s.increment("k", 300),
            lambda s: s.set_lock("lock", 900),
            lambda s: s.lock_ttl("lock"),
            lambda s: s.remember("m", 3_600),
            lambda s: s.is_remembered("m"),
            lambda s: s.delete("k"),
        ],
        ids=["peek", "increment", "set_lock", "lock_ttl", "remember", "is_remembered", "delete"],
    )
    async def test_every_operation_has_a_fallback(
        self,
        store: ResilientLoginAttemptStore,
        primary: SwitchableStore,
        operation: Callable[[ILoginAttemptStore], Awaitable[object]],
    ) -> None:
        primary.failure = ConnectionError("down")

        await operation(store)  # must not raise

    async def test_markers_are_kept_by_the_fallback_while_the_primary_is_down(
        self, store: ResilientLoginAttemptStore, primary: SwitchableStore
    ) -> None:
        """Familiar addresses keep working per process during an outage."""
        primary.failure = ConnectionError("down")

        await store.remember("m", 3_600)

        assert await store.is_remembered("m") is True

    async def test_markers_set_before_an_outage_are_not_visible_to_the_fallback(
        self, store: ResilientLoginAttemptStore, primary: SwitchableStore
    ) -> None:
        """The stricter side: an address reverts to a stranger rather than staying exempt."""
        await store.remember("m", 3_600)
        primary.failure = ConnectionError("down")

        assert await store.is_remembered("m") is False

    async def test_the_primary_is_left_alone_until_the_pause_is_over(
        self, store: ResilientLoginAttemptStore, primary: SwitchableStore, clock: Clock
    ) -> None:
        """Otherwise every login would first wait out Redis's connect timeout."""
        primary.failure = ConnectionError("down")
        await store.increment("k", 300)
        tried_so_far = primary.calls

        clock.advance(RETRY_AFTER - 1)
        for _ in range(20):
            await store.increment("k", 300)

        assert primary.calls == tried_so_far

    async def test_the_primary_is_tried_again_after_the_pause(
        self, store: ResilientLoginAttemptStore, primary: SwitchableStore, clock: Clock
    ) -> None:
        primary.failure = ConnectionError("down")
        await store.increment("k", 300)
        tried_so_far = primary.calls

        clock.advance(RETRY_AFTER + 1)
        await store.increment("k", 300)

        assert primary.calls == tried_so_far + 1

    async def test_the_fallback_keeps_counting_across_calls(
        self, store: ResilientLoginAttemptStore, primary: SwitchableStore
    ) -> None:
        primary.failure = ConnectionError("down")

        counts = [(await store.increment("k", 300)).count for _ in range(3)]

        assert counts == [1, 2, 3]


class TestRecovery:
    async def test_the_primary_takes_over_again_once_it_works(
        self,
        store: ResilientLoginAttemptStore,
        primary: SwitchableStore,
        fallback: SwitchableStore,
        clock: Clock,
    ) -> None:
        primary.failure = ConnectionError("down")
        await store.increment("k", 300)
        primary.failure = None
        clock.advance(RETRY_AFTER + 1)
        fallback_calls = fallback.calls

        await store.increment("k", 300)

        assert store.degraded is False
        assert fallback.calls == fallback_calls  # served by the primary this time

    async def test_a_still_broken_primary_is_paused_again_not_hammered(
        self, store: ResilientLoginAttemptStore, primary: SwitchableStore, clock: Clock
    ) -> None:
        primary.failure = ConnectionError("down")
        await store.increment("k", 300)
        clock.advance(RETRY_AFTER + 1)
        await store.increment("k", 300)  # retried, fails again
        retried = primary.calls

        for _ in range(10):
            await store.increment("k", 300)

        assert primary.calls == retried


class TestLogging:
    async def test_an_outage_is_one_warning_not_one_per_request(
        self, store: ResilientLoginAttemptStore, primary: SwitchableStore, clock: Clock
    ) -> None:
        primary.failure = ConnectionError("redis is down")

        with structlog.testing.capture_logs() as logs:
            for _ in range(5):
                await store.increment("k", 300)
            clock.advance(RETRY_AFTER + 1)
            for _ in range(5):
                await store.increment("k", 300)  # retried, still down

        warnings = [e for e in logs if e["event"] == "login_throttle_store_unavailable"]
        assert len(warnings) == 1
        assert warnings[0]["log_level"] == "warning"
        assert warnings[0]["error_type"] == "ConnectionError"

    async def test_recovery_is_logged_once(
        self, store: ResilientLoginAttemptStore, primary: SwitchableStore, clock: Clock
    ) -> None:
        primary.failure = ConnectionError("down")
        await store.increment("k", 300)
        primary.failure = None
        clock.advance(RETRY_AFTER + 1)

        with structlog.testing.capture_logs() as logs:
            await store.increment("k", 300)
            await store.increment("k", 300)

        assert [e["event"] for e in logs].count("login_throttle_store_recovered") == 1

    async def test_a_healthy_store_logs_nothing(
        self, store: ResilientLoginAttemptStore
    ) -> None:
        with structlog.testing.capture_logs() as logs:
            await asyncio.gather(*(store.increment("k", 300) for _ in range(10)))

        assert logs == []
