"""
In-process login-attempt store.

Used when Redis is not configured or is unreachable, and in tests. It is correct for a single
process and for nothing wider: each replica keeps its own counts, so with several replicas
the effective limits multiply. Production should run on Redis; this keeps login protected
(rather than open, or broken) while Redis is down.

Bounded on purpose. Attackers choose the usernames, and every distinct one creates keys, so
an unbounded dict is a memory leak waiting for a script. At the cap, expired entries go first,
then the oldest, which under flooding costs some protection for old entries and never
availability. That includes the markers for familiar addresses: losing one makes an address
a stranger again, which is the stricter side to err on.

Atomicity: every method runs to completion without awaiting, and the event loop never
interleaves two such calls, so increments cannot be lost without a lock.
"""

import math
import time
from collections.abc import Callable

from src.application.ports.login_attempt_store import CounterState, ILoginAttemptStore

__all__ = ["InMemoryLoginAttemptStore"]

DEFAULT_MAX_KEYS = 100_000


class _Entry:
    __slots__ = ("count", "expires_at")

    def __init__(self, count: int, expires_at: float) -> None:
        self.count = count
        self.expires_at = expires_at


class InMemoryLoginAttemptStore(ILoginAttemptStore):
    """Counters and flags held in a dict, expired lazily against an injectable clock."""

    def __init__(
        self,
        *,
        max_keys: int = DEFAULT_MAX_KEYS,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        if max_keys < 1:
            raise ValueError("max_keys must be at least 1")
        self._max_keys = max_keys
        self._clock = clock
        # dicts keep insertion order, so the first key is the oldest write.
        self._entries: dict[str, _Entry] = {}

    async def peek(self, key: str) -> CounterState | None:
        entry = self._live(key)
        if entry is None:
            return None
        return CounterState(entry.count, self._seconds_left(entry))

    async def increment(self, key: str, window_seconds: int) -> CounterState:
        entry = self._live(key)
        if entry is None:
            self._make_room()
            entry = _Entry(0, self._clock() + window_seconds)
            self._entries[key] = entry
        entry.count += 1
        return CounterState(entry.count, self._seconds_left(entry))

    async def set_lock(self, key: str, seconds: int) -> bool:
        if self._live(key) is not None:
            return False
        self._make_room()
        self._entries[key] = _Entry(1, self._clock() + seconds)
        return True

    async def lock_ttl(self, key: str) -> int | None:
        entry = self._live(key)
        return None if entry is None else self._seconds_left(entry)

    async def remember(self, key: str, seconds: int) -> None:
        if self._live(key) is None:
            self._make_room()
        # Re-inserted rather than updated in place, so a marker that was just confirmed counts
        # as recent for the oldest-first eviction instead of keeping its first position.
        self._entries.pop(key, None)
        self._entries[key] = _Entry(1, self._clock() + seconds)

    async def is_remembered(self, key: str) -> bool:
        return self._live(key) is not None

    async def delete(self, key: str) -> None:
        self._entries.pop(key, None)

    # ─── internals ───

    def __len__(self) -> int:
        return len(self._entries)

    def _live(self, key: str) -> _Entry | None:
        entry = self._entries.get(key)
        if entry is None:
            return None
        if entry.expires_at <= self._clock():
            del self._entries[key]
            return None
        return entry

    def _seconds_left(self, entry: _Entry) -> int:
        return max(1, math.ceil(entry.expires_at - self._clock()))

    def _make_room(self) -> None:
        """Keep room for one more entry: drop the expired, then the oldest if still full."""
        if len(self._entries) < self._max_keys:
            return
        now = self._clock()
        for key in [k for k, e in self._entries.items() if e.expires_at <= now]:
            del self._entries[key]
        while len(self._entries) >= self._max_keys:
            del self._entries[next(iter(self._entries))]
