"""
Login-attempt store that survives its primary going down.

Login must keep working, and keep being protected, when Redis is unreachable. This wraps a
primary store (Redis) and a fallback (in-process): while the primary is healthy every call
goes to it; on a failure the call is served from the fallback, and the primary is not tried
again for `retry_after_seconds`. That pause matters. Without it every login would first wait
out the Redis connect timeout, several times over, for as long as the outage lasts.

One WARNING per outage and one INFO on recovery, not one line per request.
"""

import time
from collections.abc import Awaitable, Callable
from typing import TypeVar

import structlog

from src.application.ports.login_attempt_store import CounterState, ILoginAttemptStore

__all__ = ["ResilientLoginAttemptStore"]

logger = structlog.get_logger(__name__)

T = TypeVar("T")


class ResilientLoginAttemptStore(ILoginAttemptStore):
    """Primary store with an in-process fallback and a pause between retries."""

    def __init__(
        self,
        primary: ILoginAttemptStore,
        fallback: ILoginAttemptStore,
        *,
        retry_after_seconds: float = 30.0,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self._primary = primary
        self._fallback = fallback
        self._retry_after = retry_after_seconds
        self._clock = clock
        self._primary_unavailable_until = 0.0
        self._degraded = False

    async def peek(self, key: str) -> CounterState | None:
        return await self._run(lambda store: store.peek(key))

    async def increment(self, key: str, window_seconds: int) -> CounterState:
        return await self._run(lambda store: store.increment(key, window_seconds))

    async def set_lock(self, key: str, seconds: int) -> bool:
        return await self._run(lambda store: store.set_lock(key, seconds))

    async def lock_ttl(self, key: str) -> int | None:
        return await self._run(lambda store: store.lock_ttl(key))

    async def remember(self, key: str, seconds: int) -> None:
        await self._run(lambda store: store.remember(key, seconds))

    async def is_remembered(self, key: str) -> bool:
        return await self._run(lambda store: store.is_remembered(key))

    async def delete(self, key: str) -> None:
        await self._run(lambda store: store.delete(key))

    @property
    def degraded(self) -> bool:
        """True while calls are being served by the fallback."""
        return self._degraded

    async def _run(self, operation: Callable[[ILoginAttemptStore], Awaitable[T]]) -> T:
        if self._clock() >= self._primary_unavailable_until:
            try:
                result = await operation(self._primary)
            except Exception as exc:  # any backend failure must degrade, never fail a login
                self._primary_unavailable_until = self._clock() + self._retry_after
                if not self._degraded:
                    self._degraded = True
                    logger.warning(
                        "login_throttle_store_unavailable",
                        error_type=type(exc).__name__,
                        detail=str(exc)[:200],
                        fallback="in-process",
                        retry_after_seconds=self._retry_after,
                        consequence=(
                            "limits are enforced per process only until the shared store "
                            "is reachable again"
                        ),
                    )
            else:
                if self._degraded:
                    self._degraded = False
                    logger.info("login_throttle_store_recovered")
                return result
        return await operation(self._fallback)
