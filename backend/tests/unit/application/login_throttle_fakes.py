"""
In-memory fake of the login-attempt store, for the throttle service's unit tests.

A hand-written implementation of the same port the Redis store implements, with a clock the
test moves by hand (`advance`) so expiry is exact rather than slept for.

Each operation first yields to the event loop and then does its work without awaiting. That
mimics a network round trip in front of an atomic server-side command, and it is what makes
the concurrency tests mean something: with no yield, `asyncio.gather` would run the callers
one after another and pass even for a service whose check-then-increment is racy.
"""

import asyncio
import math

from src.application.ports.login_attempt_store import CounterState, ILoginAttemptStore


class FakeLoginAttemptStore(ILoginAttemptStore):
    """Counters and flags in a dict, expiring against a hand-driven clock."""

    def __init__(self) -> None:
        self.now = 0.0
        # key -> (value, expires_at)
        self._entries: dict[str, tuple[int, float]] = {}

    def advance(self, seconds: float) -> None:
        self.now += seconds

    def live_keys(self) -> list[str]:
        return [key for key in list(self._entries) if self._live(key) is not None]

    def count(self, key: str) -> int | None:
        """The counter's value without going through the port; None if absent or expired."""
        entry = self._live(key)
        return None if entry is None else entry[0]

    # ─── ILoginAttemptStore ───

    async def peek(self, key: str) -> CounterState | None:
        await asyncio.sleep(0)
        entry = self._live(key)
        if entry is None:
            return None
        return CounterState(entry[0], self._seconds_left(entry[1]))

    async def increment(self, key: str, window_seconds: int) -> CounterState:
        await asyncio.sleep(0)
        entry = self._live(key)
        if entry is None:
            entry = (0, self.now + window_seconds)
        self._entries[key] = (entry[0] + 1, entry[1])
        return CounterState(entry[0] + 1, self._seconds_left(entry[1]))

    async def set_lock(self, key: str, seconds: int) -> bool:
        await asyncio.sleep(0)
        if self._live(key) is not None:
            return False
        self._entries[key] = (1, self.now + seconds)
        return True

    async def lock_ttl(self, key: str) -> int | None:
        await asyncio.sleep(0)
        entry = self._live(key)
        return None if entry is None else self._seconds_left(entry[1])

    async def remember(self, key: str, seconds: int) -> None:
        await asyncio.sleep(0)
        self._entries[key] = (1, self.now + seconds)

    async def is_remembered(self, key: str) -> bool:
        await asyncio.sleep(0)
        return self._live(key) is not None

    async def delete(self, key: str) -> None:
        await asyncio.sleep(0)
        self._entries.pop(key, None)

    # ─── internals ───

    def _live(self, key: str) -> tuple[int, float] | None:
        entry = self._entries.get(key)
        if entry is None:
            return None
        if entry[1] <= self.now:
            del self._entries[key]
            return None
        return entry

    def _seconds_left(self, expires_at: float) -> int:
        return max(1, math.ceil(expires_at - self.now))
