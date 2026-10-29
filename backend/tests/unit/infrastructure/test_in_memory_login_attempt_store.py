"""
Unit tests for InMemoryLoginAttemptStore.

The clock is injected, so expiry is exact. The bound is the part worth the most care:
attackers choose the usernames, so this store is a memory-growth target if it is ever
unbounded.
"""

import asyncio

import pytest

from src.infrastructure.cache.in_memory_login_attempt_store import InMemoryLoginAttemptStore


class Clock:
    """A clock the test moves by hand."""

    def __init__(self) -> None:
        self.now = 1_000.0

    def __call__(self) -> float:
        return self.now

    def advance(self, seconds: float) -> None:
        self.now += seconds


@pytest.fixture
def clock() -> Clock:
    return Clock()


@pytest.fixture
def store(clock: Clock) -> InMemoryLoginAttemptStore:
    return InMemoryLoginAttemptStore(clock=clock)


class TestIncrement:
    async def test_the_first_increment_creates_the_counter(
        self, store: InMemoryLoginAttemptStore
    ) -> None:
        state = await store.increment("k", 300)

        assert state.count == 1
        assert state.ttl_seconds == 300

    async def test_later_increments_count_up_without_extending_the_lifetime(
        self, store: InMemoryLoginAttemptStore, clock: Clock
    ) -> None:
        await store.increment("k", 300)
        clock.advance(100)

        state = await store.increment("k", 300)

        assert state.count == 2
        assert state.ttl_seconds == 200  # still counted from the first attempt

    async def test_an_expired_counter_starts_over(
        self, store: InMemoryLoginAttemptStore, clock: Clock
    ) -> None:
        await store.increment("k", 300)
        await store.increment("k", 300)
        clock.advance(301)

        state = await store.increment("k", 300)

        assert state.count == 1
        assert state.ttl_seconds == 300

    async def test_counters_are_independent(self, store: InMemoryLoginAttemptStore) -> None:
        await store.increment("a", 300)
        await store.increment("a", 300)

        assert (await store.increment("b", 300)).count == 1

    async def test_concurrent_increments_are_never_lost(
        self, store: InMemoryLoginAttemptStore
    ) -> None:
        states = await asyncio.gather(*(store.increment("k", 300) for _ in range(200)))

        assert sorted(s.count for s in states) == list(range(1, 201))


class TestPeek:
    async def test_a_missing_counter_is_none(self, store: InMemoryLoginAttemptStore) -> None:
        assert await store.peek("k") is None

    async def test_it_reports_the_count_and_remaining_lifetime_without_changing_them(
        self, store: InMemoryLoginAttemptStore, clock: Clock
    ) -> None:
        await store.increment("k", 300)
        clock.advance(50)

        first = await store.peek("k")
        second = await store.peek("k")

        assert first == second
        assert first is not None
        assert (first.count, first.ttl_seconds) == (1, 250)

    async def test_an_expired_counter_is_gone(
        self, store: InMemoryLoginAttemptStore, clock: Clock
    ) -> None:
        await store.increment("k", 300)
        clock.advance(300)

        assert await store.peek("k") is None

    async def test_the_remaining_lifetime_is_never_reported_as_zero(
        self, store: InMemoryLoginAttemptStore, clock: Clock
    ) -> None:
        """A Retry-After of 0 invites an immediate retry that is refused again."""
        await store.increment("k", 300)
        clock.advance(299.2)

        state = await store.peek("k")

        assert state is not None
        assert state.ttl_seconds == 1


class TestLocks:
    async def test_the_first_caller_sets_the_flag_and_the_second_does_not(
        self, store: InMemoryLoginAttemptStore
    ) -> None:
        assert await store.set_lock("lock", 900) is True
        assert await store.set_lock("lock", 900) is False

    async def test_an_existing_flag_is_not_extended(
        self, store: InMemoryLoginAttemptStore, clock: Clock
    ) -> None:
        await store.set_lock("lock", 900)
        clock.advance(600)

        await store.set_lock("lock", 900)

        assert await store.lock_ttl("lock") == 300

    async def test_a_flag_that_is_not_set_has_no_ttl(
        self, store: InMemoryLoginAttemptStore
    ) -> None:
        assert await store.lock_ttl("lock") is None

    async def test_the_flag_can_be_set_again_once_it_has_expired(
        self, store: InMemoryLoginAttemptStore, clock: Clock
    ) -> None:
        await store.set_lock("lock", 900)
        clock.advance(901)

        assert await store.lock_ttl("lock") is None
        assert await store.set_lock("lock", 900) is True

    async def test_concurrent_callers_produce_exactly_one_winner(
        self, store: InMemoryLoginAttemptStore
    ) -> None:
        results = await asyncio.gather(*(store.set_lock("lock", 900) for _ in range(50)))

        assert results.count(True) == 1


class TestMarkers:
    async def test_a_marker_that_was_never_set_is_not_remembered(
        self, store: InMemoryLoginAttemptStore
    ) -> None:
        assert await store.is_remembered("m") is False

    async def test_a_marker_is_remembered_once_set(
        self, store: InMemoryLoginAttemptStore
    ) -> None:
        await store.remember("m", 3_600)

        assert await store.is_remembered("m") is True

    async def test_a_marker_is_forgotten_when_its_lifetime_ends(
        self, store: InMemoryLoginAttemptStore, clock: Clock
    ) -> None:
        await store.remember("m", 3_600)
        clock.advance(3_599)
        assert await store.is_remembered("m") is True

        clock.advance(2)

        assert await store.is_remembered("m") is False

    async def test_remembering_again_restarts_the_lifetime(
        self, store: InMemoryLoginAttemptStore, clock: Clock
    ) -> None:
        """Unlike a lock, which is never extended: a marker lives while it is confirmed."""
        await store.remember("m", 3_600)
        clock.advance(3_000)

        await store.remember("m", 3_600)
        clock.advance(3_000)  # 6000 s after the first call, 3000 after the second

        assert await store.is_remembered("m") is True

    async def test_a_marker_can_be_removed(self, store: InMemoryLoginAttemptStore) -> None:
        await store.remember("m", 3_600)

        await store.delete("m")

        assert await store.is_remembered("m") is False

    async def test_markers_and_counters_do_not_see_each_other(
        self, store: InMemoryLoginAttemptStore
    ) -> None:
        await store.remember("m", 3_600)

        assert await store.is_remembered("k") is False
        assert await store.peek("k") is None

    async def test_refreshing_a_marker_does_not_evict_anything_else(self, clock: Clock) -> None:
        store = InMemoryLoginAttemptStore(max_keys=2, clock=clock)
        await store.remember("m", 3_600)
        await store.increment("other", 300)

        await store.remember("m", 3_600)  # already present: needs no room

        assert await store.peek("other") is not None
        assert await store.is_remembered("m") is True

    async def test_a_refreshed_marker_counts_as_recent_for_eviction(
        self, clock: Clock
    ) -> None:
        """Otherwise the address someone just logged in from would be the first to go."""
        store = InMemoryLoginAttemptStore(max_keys=3, clock=clock)
        await store.remember("m", 3_600)
        await store.increment("a", 300)
        await store.increment("b", 300)
        await store.remember("m", 3_600)  # confirmed again, after a and b were written

        await store.increment("c", 300)  # full: the oldest write goes, which is now "a"

        assert await store.is_remembered("m") is True
        assert await store.peek("a") is None

    async def test_a_marker_can_still_be_stored_when_the_store_is_full(
        self, clock: Clock
    ) -> None:
        store = InMemoryLoginAttemptStore(max_keys=2, clock=clock)
        await store.increment("a", 300)
        await store.increment("b", 300)

        await store.remember("m", 3_600)

        assert await store.is_remembered("m") is True
        assert len(store) == 2


class TestDelete:
    async def test_it_removes_a_counter(self, store: InMemoryLoginAttemptStore) -> None:
        await store.increment("k", 300)

        await store.delete("k")

        assert await store.peek("k") is None

    async def test_it_removes_a_flag(self, store: InMemoryLoginAttemptStore) -> None:
        await store.set_lock("lock", 900)

        await store.delete("lock")

        assert await store.lock_ttl("lock") is None

    async def test_deleting_something_absent_is_not_an_error(
        self, store: InMemoryLoginAttemptStore
    ) -> None:
        await store.delete("never-existed")


class TestBound:
    async def test_it_refuses_a_nonsense_bound(self) -> None:
        with pytest.raises(ValueError, match="max_keys"):
            InMemoryLoginAttemptStore(max_keys=0)

    async def test_the_oldest_entry_is_dropped_when_full(self, clock: Clock) -> None:
        store = InMemoryLoginAttemptStore(max_keys=3, clock=clock)
        for key in ("a", "b", "c"):
            await store.increment(key, 300)

        await store.increment("d", 300)

        assert len(store) == 3
        assert await store.peek("a") is None
        assert await store.peek("d") is not None

    async def test_expired_entries_are_dropped_before_live_ones(self, clock: Clock) -> None:
        store = InMemoryLoginAttemptStore(max_keys=3, clock=clock)
        await store.increment("short", 10)
        await store.increment("long1", 300)
        await store.increment("long2", 300)
        clock.advance(11)

        await store.increment("new", 300)

        assert await store.peek("long1") is not None  # live entries were not sacrificed
        assert await store.peek("long2") is not None
        assert await store.peek("new") is not None

    async def test_flooding_with_unique_usernames_cannot_grow_it_without_limit(
        self, clock: Clock
    ) -> None:
        store = InMemoryLoginAttemptStore(max_keys=100, clock=clock)

        for n in range(10_000):
            await store.increment(f"login:count:account:{n}", 300)

        assert len(store) <= 100

    async def test_a_flag_can_still_be_set_when_the_store_is_full(self, clock: Clock) -> None:
        """A lockout must always be recordable, even mid-flood."""
        store = InMemoryLoginAttemptStore(max_keys=2, clock=clock)
        await store.increment("a", 300)
        await store.increment("b", 300)

        assert await store.set_lock("lock", 900) is True
        assert await store.lock_ttl("lock") == 900
