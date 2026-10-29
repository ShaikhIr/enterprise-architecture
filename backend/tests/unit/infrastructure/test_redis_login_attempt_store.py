"""
Unit tests for RedisLoginAttemptStore.

No Redis server is needed, or available in CI: the store is exercised against a small
hand-written client that behaves like Redis for the handful of commands it uses (SET with
NX/EX, GET, INCR, TTL, DEL, MULTI/EXEC pipelines), on a clock the test moves by hand.

What these tests pin down is the shape of what the store sends, because that is where its
guarantees live and where a refactor could quietly break them: the increment must be one
transaction, and the key must be created with its expiry *before* it is incremented, or a
crash in between would leave a counter that never resets.
"""

import math
from types import TracebackType
from typing import Any, cast

import pytest
from redis.asyncio import Redis

from src.infrastructure.cache.redis_login_attempt_store import RedisLoginAttemptStore


class FakeRedis:
    """Just enough of redis.asyncio.Redis (decode_responses=True) for the store."""

    def __init__(self) -> None:
        self.now = 0.0
        # key -> (value, expires_at or None for "no expiry")
        self.data: dict[str, tuple[str, float | None]] = {}
        self.pipelines: list[FakePipeline] = []
        self.ttl_override: dict[str, int] = {}
        # Every direct SET the store sent (not those inside a pipeline), to pin its arguments.
        self.sets: list[dict[str, object]] = []

    def advance(self, seconds: float) -> None:
        self.now += seconds

    # ─── command implementations ───

    def _alive(self, key: str) -> tuple[str, float | None] | None:
        entry = self.data.get(key)
        if entry is None:
            return None
        if entry[1] is not None and entry[1] <= self.now:
            del self.data[key]
            return None
        return entry

    def do_get(self, key: str) -> str | None:
        entry = self._alive(key)
        return None if entry is None else entry[0]

    def do_set(self, key: str, value: object, ex: int | None, nx: bool) -> bool | None:
        if nx and self._alive(key) is not None:
            return None
        self.data[key] = (str(value), None if ex is None else self.now + ex)
        return True

    def do_incr(self, key: str) -> int:
        entry = self._alive(key)
        value = 0 if entry is None else int(entry[0])
        expires = None if entry is None else entry[1]  # INCR keeps an existing expiry
        self.data[key] = (str(value + 1), expires)
        return value + 1

    def do_ttl(self, key: str) -> int:
        if key in self.ttl_override:
            return self.ttl_override[key]
        entry = self._alive(key)
        if entry is None:
            return -2
        if entry[1] is None:
            return -1
        return math.ceil(entry[1] - self.now)

    def do_delete(self, key: str) -> int:
        return 1 if self.data.pop(key, None) is not None else 0

    # ─── the surface the store calls ───

    def pipeline(self, transaction: bool = True) -> "FakePipeline":
        pipe = FakePipeline(self, transaction)
        self.pipelines.append(pipe)
        return pipe

    async def set(
        self, key: str, value: object, ex: int | None = None, nx: bool = False
    ) -> bool | None:
        self.sets.append({"key": key, "ex": ex, "nx": nx})
        return self.do_set(key, value, ex, nx)

    async def exists(self, key: str) -> int:
        return 0 if self._alive(key) is None else 1

    async def ttl(self, key: str) -> int:
        return self.do_ttl(key)

    async def delete(self, key: str) -> int:
        return self.do_delete(key)


class FakePipeline:
    """Queues commands and runs them in order on execute(), recording what was queued."""

    def __init__(self, redis: FakeRedis, transaction: bool) -> None:
        self._redis = redis
        self.transaction = transaction
        self.commands: list[tuple[str, tuple[Any, ...], dict[str, Any]]] = []

    async def __aenter__(self) -> "FakePipeline":
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None:
        return None

    def get(self, key: str) -> "FakePipeline":
        self.commands.append(("get", (key,), {}))
        return self

    def ttl(self, key: str) -> "FakePipeline":
        self.commands.append(("ttl", (key,), {}))
        return self

    def set(
        self, key: str, value: object, ex: int | None = None, nx: bool = False
    ) -> "FakePipeline":
        self.commands.append(("set", (key, value), {"ex": ex, "nx": nx}))
        return self

    def incr(self, key: str) -> "FakePipeline":
        self.commands.append(("incr", (key,), {}))
        return self

    async def execute(self) -> list[Any]:
        results: list[Any] = []
        for name, args, kwargs in self.commands:
            if name == "get":
                results.append(self._redis.do_get(*args))
            elif name == "ttl":
                results.append(self._redis.do_ttl(*args))
            elif name == "set":
                results.append(self._redis.do_set(args[0], args[1], kwargs["ex"], kwargs["nx"]))
            elif name == "incr":
                results.append(self._redis.do_incr(*args))
            else:  # pragma: no cover - a command the store should not be sending
                raise AssertionError(f"unexpected command {name}")
        return results

    @property
    def command_names(self) -> list[str]:
        return [name for name, _, _ in self.commands]


@pytest.fixture
def redis() -> FakeRedis:
    return FakeRedis()


@pytest.fixture
def store(redis: FakeRedis) -> RedisLoginAttemptStore:
    return RedisLoginAttemptStore(cast(Redis, redis))


class TestIncrement:
    async def test_the_first_increment_creates_the_counter_with_the_window_as_its_lifetime(
        self, store: RedisLoginAttemptStore
    ) -> None:
        state = await store.increment("k", 300)

        assert state.count == 1
        assert state.ttl_seconds == 300

    async def test_later_increments_count_up_without_extending_the_lifetime(
        self, store: RedisLoginAttemptStore, redis: FakeRedis
    ) -> None:
        await store.increment("k", 300)
        redis.advance(100)

        state = await store.increment("k", 300)

        assert state.count == 2
        assert state.ttl_seconds == 200

    async def test_an_expired_counter_starts_over(
        self, store: RedisLoginAttemptStore, redis: FakeRedis
    ) -> None:
        await store.increment("k", 300)
        redis.advance(301)

        assert (await store.increment("k", 300)).count == 1

    async def test_a_counter_never_exists_without_an_expiry(
        self, store: RedisLoginAttemptStore, redis: FakeRedis
    ) -> None:
        await store.increment("k", 300)
        await store.increment("k", 300)

        assert redis.do_ttl("k") > 0

    async def test_the_increment_is_a_single_transaction(
        self, store: RedisLoginAttemptStore, redis: FakeRedis
    ) -> None:
        """MULTI/EXEC is what makes create-then-increment atomic across replicas."""
        await store.increment("k", 300)

        assert len(redis.pipelines) == 1
        assert redis.pipelines[0].transaction is True

    async def test_the_key_is_created_with_its_expiry_before_it_is_incremented(
        self, store: RedisLoginAttemptStore, redis: FakeRedis
    ) -> None:
        """INCR first, EXPIRE after, would leave a counter that never resets if we died between."""
        await store.increment("k", 300)

        pipe = redis.pipelines[0]
        assert pipe.command_names == ["set", "incr", "ttl"]
        _, _, kwargs = pipe.commands[0]
        assert kwargs == {"ex": 300, "nx": True}


class TestPeek:
    async def test_a_missing_counter_is_none(self, store: RedisLoginAttemptStore) -> None:
        assert await store.peek("k") is None

    async def test_it_reports_count_and_remaining_lifetime_and_changes_nothing(
        self, store: RedisLoginAttemptStore, redis: FakeRedis
    ) -> None:
        await store.increment("k", 300)
        redis.advance(50)

        state = await store.peek("k")

        assert state is not None
        assert (state.count, state.ttl_seconds) == (1, 250)
        assert redis.do_get("k") == "1"

    async def test_peeking_does_not_use_a_transaction(
        self, store: RedisLoginAttemptStore, redis: FakeRedis
    ) -> None:
        await store.peek("k")

        assert redis.pipelines[0].transaction is False


class TestLocks:
    async def test_the_first_caller_sets_the_flag_and_the_second_does_not(
        self, store: RedisLoginAttemptStore
    ) -> None:
        assert await store.set_lock("lock", 900) is True
        assert await store.set_lock("lock", 900) is False

    async def test_the_flag_is_created_with_its_expiry(
        self, store: RedisLoginAttemptStore, redis: FakeRedis
    ) -> None:
        await store.set_lock("lock", 900)

        assert redis.do_ttl("lock") == 900

    async def test_an_existing_flag_is_not_extended(
        self, store: RedisLoginAttemptStore, redis: FakeRedis
    ) -> None:
        await store.set_lock("lock", 900)
        redis.advance(600)

        await store.set_lock("lock", 900)

        assert await store.lock_ttl("lock") == 300

    async def test_a_flag_that_is_not_set_has_no_ttl(
        self, store: RedisLoginAttemptStore
    ) -> None:
        assert await store.lock_ttl("lock") is None

    async def test_a_flag_without_an_expiry_is_removed_rather_than_locking_forever(
        self, store: RedisLoginAttemptStore, redis: FakeRedis
    ) -> None:
        redis.data["lock"] = ("1", None)  # something else wrote it, with no TTL

        assert await store.lock_ttl("lock") is None
        assert "lock" not in redis.data

    async def test_the_final_second_is_reported_as_one_not_zero(
        self, store: RedisLoginAttemptStore, redis: FakeRedis
    ) -> None:
        await store.set_lock("lock", 900)
        redis.ttl_override["lock"] = 0  # Redis reports 0 for the last second

        assert await store.lock_ttl("lock") == 1


class TestMarkers:
    async def test_a_marker_that_was_never_set_is_not_remembered(
        self, store: RedisLoginAttemptStore
    ) -> None:
        assert await store.is_remembered("m") is False

    async def test_a_marker_is_remembered_once_set(self, store: RedisLoginAttemptStore) -> None:
        await store.remember("m", 3_600)

        assert await store.is_remembered("m") is True

    async def test_the_marker_is_created_with_its_expiry(
        self, store: RedisLoginAttemptStore, redis: FakeRedis
    ) -> None:
        """A marker with no expiry would exempt an address for ever."""
        await store.remember("m", 3_600)

        assert redis.do_ttl("m") == 3_600

    async def test_the_marker_is_not_set_with_nx_so_that_it_can_be_refreshed(
        self, store: RedisLoginAttemptStore, redis: FakeRedis
    ) -> None:
        await store.remember("m", 3_600)

        assert redis.sets == [{"key": "m", "ex": 3_600, "nx": False}]

    async def test_remembering_again_restarts_the_lifetime(
        self, store: RedisLoginAttemptStore, redis: FakeRedis
    ) -> None:
        """Unlike set_lock, which leaves a flag that is already set alone."""
        await store.remember("m", 3_600)
        redis.advance(3_000)

        await store.remember("m", 3_600)

        assert redis.do_ttl("m") == 3_600

    async def test_a_marker_is_forgotten_when_its_lifetime_ends(
        self, store: RedisLoginAttemptStore, redis: FakeRedis
    ) -> None:
        await store.remember("m", 3_600)
        redis.advance(3_601)

        assert await store.is_remembered("m") is False

    async def test_a_marker_can_be_removed(
        self, store: RedisLoginAttemptStore
    ) -> None:
        await store.remember("m", 3_600)

        await store.delete("m")

        assert await store.is_remembered("m") is False


class TestDelete:
    async def test_it_removes_the_key(
        self, store: RedisLoginAttemptStore, redis: FakeRedis
    ) -> None:
        await store.increment("k", 300)

        await store.delete("k")

        assert "k" not in redis.data

    async def test_deleting_something_absent_is_not_an_error(
        self, store: RedisLoginAttemptStore
    ) -> None:
        await store.delete("never-existed")
