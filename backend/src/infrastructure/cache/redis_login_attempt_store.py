"""
Redis-backed login-attempt store.

Shared by every API replica, which is what makes the limits real once there is more than
one process: a per-process counter lets an attacker spread guesses across replicas.

Only plain commands, no Lua. The multi-step operation is one MULTI/EXEC transaction:

    SET key 0 NX EX <window>   create with its expiry, or leave an existing counter alone
    INCR key                   the atomic increment
    TTL key                    what the caller needs for Retry-After

The SET-with-expiry always comes first, so a counter can never exist without a TTL (an
INCR-then-EXPIRE pair that dies between the two would leave a counter that never resets and
blocks its account forever).
"""

from redis.asyncio import Redis

from src.application.ports.login_attempt_store import CounterState, ILoginAttemptStore

__all__ = ["RedisLoginAttemptStore"]

_NO_SUCH_KEY = -2
_NO_EXPIRY = -1


class RedisLoginAttemptStore(ILoginAttemptStore):
    """Counters and flags as Redis keys with a TTL. Built over a `decode_responses` client."""

    def __init__(self, client: Redis) -> None:
        self._redis = client

    async def peek(self, key: str) -> CounterState | None:
        async with self._redis.pipeline(transaction=False) as pipe:
            pipe.get(key)
            pipe.ttl(key)
            raw, ttl = await pipe.execute()
        if raw is None or ttl == _NO_SUCH_KEY:
            return None
        return CounterState(int(raw), self._to_seconds(ttl))

    async def increment(self, key: str, window_seconds: int) -> CounterState:
        async with self._redis.pipeline(transaction=True) as pipe:
            pipe.set(key, 0, ex=window_seconds, nx=True)
            pipe.incr(key)
            pipe.ttl(key)
            _, count, ttl = await pipe.execute()
        return CounterState(int(count), self._to_seconds(ttl, default=window_seconds))

    async def set_lock(self, key: str, seconds: int) -> bool:
        return bool(await self._redis.set(key, "1", ex=seconds, nx=True))

    async def lock_ttl(self, key: str) -> int | None:
        ttl = int(await self._redis.ttl(key))
        if ttl == _NO_SUCH_KEY:
            return None
        if ttl == _NO_EXPIRY:
            # Not something we ever write. Remove it rather than lock an account forever.
            await self._redis.delete(key)
            return None
        return self._to_seconds(ttl)

    async def remember(self, key: str, seconds: int) -> None:
        # Plain SET with an expiry and no NX: unlike a lock, a marker's lifetime restarts.
        await self._redis.set(key, "1", ex=seconds)

    async def is_remembered(self, key: str) -> bool:
        return bool(await self._redis.exists(key))

    async def delete(self, key: str) -> None:
        await self._redis.delete(key)

    @staticmethod
    def _to_seconds(ttl: int, default: int = 1) -> int:
        """A TTL as whole seconds; Redis reports 0 in the last second and negatives as flags."""
        return ttl if ttl > 0 else default
