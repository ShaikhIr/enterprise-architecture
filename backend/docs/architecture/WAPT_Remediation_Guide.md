# WAPT Remediation Guide

How to fix the four SecurityHQ WAPT findings in a FastAPI + React (PrimeReact) + nginx
application. This document is self-contained: every new file is given in full and every
change to an existing file is spelled out. You do not need any other repository.

Assumed stack (adapt names where yours differ): Python 3.12, FastAPI, async SQLAlchemy,
structlog, pytest + pytest-asyncio, React 19, TypeScript, Redux Toolkit, Axios, PrimeReact
10.6+, Vitest + MSW, nginx.

---

## 1. The findings

| ID | Severity | Finding | Fixed in |
|----|----------|---------|----------|
| EMC-WA-1 | Medium | No rate limiting on `POST /api/v1/auth/login` | Sections 3 and 4.1 |
| EMC-WA-2 | Low | nginx version visible on the 404 page (`/assets/`) | Section 5 |
| EMC-WA-3 | Low | CSP contains `'unsafe-inline'` in `style-src` | Sections 4.2 and 5 |
| EMC-WA-4 | Low | `Cross-Origin-Embedder-Policy` and `Cross-Origin-Resource-Policy` missing | Section 5 |

**Order of work:** backend (WA-1), then frontend, then nginx (WA-2/3/4). The frontend nonce
change (4.2) must be deployed **before or together with** the nginx change, otherwise the
strict CSP breaks the UI.

## 2. End result

**WA-1.** For `POST /auth/login`:

- 5 attempts at one account from one IP within 5 minutes: further attempts from that IP for
  that account get HTTP 429 with `Retry-After: 900` (15 minutes).
- 20 attempts at one account across many IPs the account has **never logged in from**: the
  account is locked for such IPs for 15 minutes. IPs the account has logged in from before
  ("familiar" IPs) are not counted and not locked, so an attacker cannot lock the real user out
  of their usual network.
- 50 failed logins from one IP (any username): that IP gets 429 until the window ends.
- A throttled request never reaches bcrypt or the AD service.
- Failed logins are written to `audit_logs`; each lockout writes exactly one `LOGIN_LOCKED` row.
- The 429 body is the same generic message for every account, so it reveals nothing.

**WA-2/3/4.** nginx hides its version, serves generic error pages, sends
`style-src 'self' 'nonce-<random>'` (no `unsafe-inline`), and adds
`Cross-Origin-Embedder-Policy: require-corp` and `Cross-Origin-Resource-Policy: same-origin`.

---

## 3. Backend (EMC-WA-1)

### 3.1 Dependency

`redis` must be a **core** dependency (the counters must be shared by every API replica, or an
attacker spreads guesses across replicas). In `pyproject.toml`, under `[project] dependencies`:

```toml
"redis==5.1.1",
```

If it was previously only in an optional extra (e.g. `background`), remove it from there and
promote it. Then reinstall (`pip install -e ".[dev]"`).

### 3.2 New file: `src/application/ports/login_attempt_store.py`

```python
"""
Login-attempt counter port.

The seam between "how many times has this account or address tried to log in" and "where
that count lives". The throttle service depends on this interface and never on Redis, so the
policy stays testable against a fake and the storage (Redis shared by every replica, or a
per-process fallback) can change without touching it.

Everything here is an expiring counter, an expiring flag or an expiring marker. Atomicity is
the implementation's job: `increment` must add one and report the new value as a single
step, because the throttle's guarantee (at most N guesses are ever evaluated, however many
arrive at once) rests on it.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass

__all__ = ["CounterState", "ILoginAttemptStore"]


@dataclass(frozen=True)
class CounterState:
    """A counter's value and how long it has left before it expires."""

    count: int
    ttl_seconds: int


class ILoginAttemptStore(ABC):
    """Expiring counters and flags that back the login throttle."""

    @abstractmethod
    async def peek(self, key: str) -> CounterState | None:
        """The counter's current state without changing it; None when it does not exist."""
        ...

    @abstractmethod
    async def increment(self, key: str, window_seconds: int) -> CounterState:
        """
        Atomically add one to the counter and return its new state.

        A counter that does not exist yet is created with a lifetime of `window_seconds`;
        incrementing an existing one never extends that lifetime, so the window is fixed from
        the first attempt rather than sliding forward with every one.
        """
        ...

    @abstractmethod
    async def set_lock(self, key: str, seconds: int) -> bool:
        """
        Set an expiring flag unless it is already set.

        Returns True only for the caller that actually set it, which is how exactly one of
        several concurrent requests becomes the one that starts (and reports) a lockout.
        An existing flag is left alone, so a lockout is never extended.
        """
        ...

    @abstractmethod
    async def lock_ttl(self, key: str) -> int | None:
        """Seconds left on the flag, or None when it is not set."""
        ...

    @abstractmethod
    async def remember(self, key: str, seconds: int) -> None:
        """
        Set an expiring marker, or restart the lifetime of one that already exists.

        The opposite of `set_lock`, which never touches a flag that is set. A marker records
        a fact that stays true for as long as it keeps being confirmed (this address has
        logged in successfully), so each confirmation pushes the expiry out again.
        """
        ...

    @abstractmethod
    async def is_remembered(self, key: str) -> bool:
        """True while the marker exists."""
        ...

    @abstractmethod
    async def delete(self, key: str) -> None:
        """Remove a counter, flag or marker. Removing one that does not exist is not an error."""
        ...
```

### 3.3 New file: `src/application/services/login_throttle_service.py`

```python
"""
Login throttling: brute-force and credential-stuffing protection for POST /auth/login.

Three limits, checked in this order before any password is verified (so a throttled request
costs no bcrypt and never reaches the corporate AD service):

1. Lockouts already in force. Attempts made while one holds touch no counter, so they
   neither extend it nor use up the caller's other budgets.
2. Failures per client IP. A coarse guard against one address spraying many usernames.
   Counted after the fact and only for failures, so successful logins from a shared office
   or proxy address never use it up.
3. Attempts per account, reserved *before* verification: first per account from this IP
   (small, so one address cannot keep guessing), then per account across all *unfamiliar*
   IPs (larger, so a botnet spreading guesses over many addresses is still capped).
   Reserving up front is what makes the cap hold under concurrency: a burst of parallel
   guesses is counted one by one before any of them is evaluated, so at most the limit's
   worth ever run.

Two things keep the limit from being turned against the real user.

The per-IP part of the account limit. A lockout keyed on the username alone lets anyone who
knows it (`admin`) keep that account locked for everyone. Keyed per IP, the attacker is
locked out and the real user, on a different address, is not.

Familiar addresses. A spread-out attack does reach the cross-IP cap, and a cap that locked the
account for everyone would then lock out its owner too. So that cap only applies to addresses
the account has not logged in from. An address becomes familiar when a login from it
succeeds, which a guesser cannot fake, and stays so for `familiar_ip_ttl_seconds` after the
latest one. A familiar address is neither counted toward the cross-IP cap nor locked by it,
but it keeps its own per-IP budget, so it is not unlimited guessing either. The two groups
are counted separately, as in Microsoft's "smart lockout". What remains is the owner arriving
from a brand-new address during an attack, who waits the lockout out.

Unknown usernames are counted exactly like real ones, so a response never reveals whether an
account exists (none of them has a familiar address). A successful login clears that account's
count for the address it came from, and nothing else: it must not refill the budget of a
guesser who is spreading attempts over other addresses.

No HTTP concepts here: callers get `LoginThrottledError` and decide how to present it.
"""

import hashlib
import unicodedata
from dataclasses import dataclass
from enum import StrEnum

import structlog

from src.application.ports.login_attempt_store import ILoginAttemptStore

__all__ = [
    "LoginAttemptTicket",
    "LoginThrottlePolicy",
    "LoginThrottleService",
    "LoginThrottledError",
    "ThrottleReason",
]

logger = structlog.get_logger(__name__)

_MAX_IP_LENGTH = 64
_MAX_LOG_NAME_LENGTH = 64
# What an address that could not be resolved is called. Many different clients can end up
# under it, so it is never remembered as familiar to anyone.
_UNKNOWN_IP = "unknown"


class ThrottleReason(StrEnum):
    """Which limit refused an attempt. For logs and audit only, never sent to the client."""

    ACCOUNT_IP_LOCKOUT = "account_ip_lockout"
    # The account is locked for addresses it has never had a successful login from.
    ACCOUNT_UNFAMILIAR_LOCKOUT = "account_unfamiliar_lockout"
    IP_LIMIT = "ip_limit"


class LoginThrottledError(Exception):
    """Raised instead of verifying credentials when an attempt is over a limit."""

    def __init__(
        self,
        retry_after_seconds: int,
        reason: ThrottleReason,
        *,
        lockout_started: bool = False,
        account: str = "",
        client_ip: str = "",
    ) -> None:
        super().__init__(f"Login throttled ({reason}); retry in {retry_after_seconds}s")
        self.retry_after_seconds = max(1, retry_after_seconds)
        self.reason = reason
        # True for exactly the one request that started a lockout (the caller audits it).
        self.lockout_started = lockout_started
        self.account = account
        self.client_ip = client_ip


@dataclass(frozen=True)
class LoginThrottlePolicy:
    """The limits. Every number comes from settings; nothing here is a magic constant."""

    enabled: bool = True
    window_seconds: int = 300
    max_attempts_per_account_ip: int = 5
    # Across all addresses the account has not logged in from. Familiar ones are not counted.
    max_attempts_per_account: int = 20
    max_failures_per_ip: int = 50
    lockout_seconds: int = 900
    # How long an address stays familiar after a successful login (30 days). 0 turns the
    # exemption off: every address is then a stranger, and nothing is recorded.
    familiar_ip_ttl_seconds: int = 2_592_000


@dataclass(frozen=True)
class LoginAttemptTicket:
    """One admitted attempt, carrying the keys its outcome must be recorded against."""

    account_ip_key: str
    # Attempts at this account from addresses it has no successful login from.
    unfamiliar_key: str
    ip_key: str
    account_ip_lock_key: str
    unfamiliar_lock_key: str
    # Present while this address has a successful login for this account on record.
    familiar_key: str
    # Normalised and escaped, safe to log. The client chooses this string.
    account_label: str
    client_ip: str


class LoginThrottleService:
    """Decides whether a login attempt may be evaluated, and records how it went."""

    def __init__(self, store: ILoginAttemptStore, policy: LoginThrottlePolicy) -> None:
        self._store = store
        self._policy = policy

    async def begin_attempt(self, username: str, client_ip: str) -> LoginAttemptTicket:
        """
        Admit an attempt, or raise `LoginThrottledError` when a limit refuses it.

        Call before looking up the user or verifying anything. An admitted attempt has been
        reserved against the account; report the outcome with `record_success` or
        `record_failure` using the returned ticket.
        """
        ticket = self._ticket(username, client_ip)
        if not self._policy.enabled:
            return ticket

        familiar = await self._is_familiar(ticket)

        locked = await self._active_lockout(ticket, familiar=familiar)
        if locked is not None:
            raise locked

        ip_state = await self._store.peek(ticket.ip_key)
        if ip_state is not None and ip_state.count >= self._policy.max_failures_per_ip:
            raise self._refusal(ThrottleReason.IP_LIMIT, ip_state.ttl_seconds, ticket)

        window = self._policy.window_seconds
        per_ip = await self._store.increment(ticket.account_ip_key, window)
        if per_ip.count > self._policy.max_attempts_per_account_ip:
            raise await self._start_lockout(
                ticket.account_ip_lock_key, ThrottleReason.ACCOUNT_IP_LOCKOUT, ticket
            )
        if not familiar:
            overall = await self._store.increment(ticket.unfamiliar_key, window)
            if overall.count > self._policy.max_attempts_per_account:
                raise await self._start_lockout(
                    ticket.unfamiliar_lock_key,
                    ThrottleReason.ACCOUNT_UNFAMILIAR_LOCKOUT,
                    ticket,
                )
        return ticket

    async def record_failure(self, ticket: LoginAttemptTicket) -> None:
        """Count a failed attempt against the client IP. The account side was reserved already."""
        if not self._policy.enabled:
            return
        state = await self._store.increment(ticket.ip_key, self._policy.window_seconds)
        if state.count == self._policy.max_failures_per_ip:
            logger.warning(
                "login_ip_limit_reached",
                client_ip=ticket.client_ip,
                max_failures=self._policy.max_failures_per_ip,
                window_seconds=self._policy.window_seconds,
            )

    async def record_success(self, ticket: LoginAttemptTicket) -> None:
        """
        Forget this address's earlier typos, and remember the address as familiar.

        Only the count for this address is cleared. The count of attempts from strangers is
        left to run out on its own: a success here says nothing about the guesses other
        addresses have been making, and clearing it would hand a spread-out guesser a fresh
        budget every time the real user signed in.
        """
        if not self._policy.enabled:
            return
        await self._store.delete(ticket.account_ip_key)
        if self._remembers_addresses(ticket):
            await self._store.remember(ticket.familiar_key, self._policy.familiar_ip_ttl_seconds)

    # ─── internals ───

    def _remembers_addresses(self, ticket: LoginAttemptTicket) -> bool:
        """Whether this attempt's address can be (or have been) recorded as familiar."""
        return self._policy.familiar_ip_ttl_seconds > 0 and ticket.client_ip != _UNKNOWN_IP

    async def _is_familiar(self, ticket: LoginAttemptTicket) -> bool:
        if not self._remembers_addresses(ticket):
            return False
        return await self._store.is_remembered(ticket.familiar_key)

    async def _active_lockout(
        self, ticket: LoginAttemptTicket, *, familiar: bool
    ) -> LoginThrottledError | None:
        """
        The lockout with the most time left, if one applies to this attempt.

        The lockout on strangers does not apply to a familiar address, which is the whole
        point of telling them apart.
        """
        candidates = [(ticket.account_ip_lock_key, ThrottleReason.ACCOUNT_IP_LOCKOUT)]
        if not familiar:
            candidates.append(
                (ticket.unfamiliar_lock_key, ThrottleReason.ACCOUNT_UNFAMILIAR_LOCKOUT)
            )
        longest: tuple[int, ThrottleReason] | None = None
        for key, reason in candidates:
            remaining = await self._store.lock_ttl(key)
            if remaining is not None and (longest is None or remaining > longest[0]):
                longest = (remaining, reason)
        if longest is None:
            return None
        return self._refusal(longest[1], longest[0], ticket)

    async def _start_lockout(
        self, lock_key: str, reason: ThrottleReason, ticket: LoginAttemptTicket
    ) -> LoginThrottledError:
        """Lock the scope. Only the request that actually sets the flag reports it."""
        started = await self._store.set_lock(lock_key, self._policy.lockout_seconds)
        if started:
            retry_after = self._policy.lockout_seconds
            logger.warning(
                "login_lockout_started",
                scope=reason.value,
                account=ticket.account_label,
                client_ip=ticket.client_ip,
                lockout_seconds=retry_after,
            )
        else:
            # A concurrent request set it between our counter check and now.
            retry_after = await self._store.lock_ttl(lock_key) or self._policy.lockout_seconds
        return self._refusal(reason, retry_after, ticket, lockout_started=started)

    @staticmethod
    def _refusal(
        reason: ThrottleReason,
        retry_after: int,
        ticket: LoginAttemptTicket,
        *,
        lockout_started: bool = False,
    ) -> LoginThrottledError:
        return LoginThrottledError(
            retry_after,
            reason,
            lockout_started=lockout_started,
            account=ticket.account_label,
            client_ip=ticket.client_ip,
        )

    @staticmethod
    def _ticket(username: str, client_ip: str) -> LoginAttemptTicket:
        account = _normalise_account(username)
        digest = hashlib.sha256(account.encode("utf-8")).hexdigest()[:32]
        ip = client_ip.strip()[:_MAX_IP_LENGTH] or _UNKNOWN_IP
        return LoginAttemptTicket(
            account_ip_key=f"login:count:account_ip:{digest}:{ip}",
            unfamiliar_key=f"login:count:account_unfamiliar:{digest}",
            ip_key=f"login:count:ip:{ip}",
            account_ip_lock_key=f"login:lock:account_ip:{digest}:{ip}",
            unfamiliar_lock_key=f"login:lock:account_unfamiliar:{digest}",
            familiar_key=f"login:familiar:{digest}:{ip}",
            account_label=ascii(account)[1:-1][:_MAX_LOG_NAME_LENGTH],
            client_ip=ip,
        )


def _normalise_account(username: str) -> str:
    """
    The account an attempt is aimed at, folded so spelling variants share one budget.

    The user lookup is an exact match, so `Admin`, `admin ` and a full-width `ＡＤＭＩＮ` are
    different (mostly non-existent) accounts to it. Folding them into one key only ever
    merges budgets, so it can make the limit stricter but never lets a variant dodge it.
    """
    return unicodedata.normalize("NFKC", username).strip().casefold()
```

### 3.4 New file: `src/infrastructure/cache/redis_login_attempt_store.py`

```python
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
```

### 3.5 New file: `src/infrastructure/cache/in_memory_login_attempt_store.py`

Used when `REDIS_URL` is empty, as the fallback when Redis is down, and in tests.

```python
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
```

### 3.6 New file: `src/infrastructure/cache/resilient_login_attempt_store.py`

```python
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
```

### 3.7 New file: `src/api/client_ip.py`

Finds the real client address for rate limiting, resistant to a forged `X-Forwarded-For`.

```python
"""
Client address resolution for security decisions.

Used for rate limiting, where a wrong answer has teeth: believe a forged header and an
attacker gets a fresh budget with every request. So this is stricter than the left-most
`X-Forwarded-For` hop that the audit code reads, which the client controls.

How `X-Forwarded-For` is built: each proxy appends the address it saw the request come
from. Entries on the right were added by our own infrastructure and can be trusted; entries
on the left may have been sent by the client. With `trusted_proxy_hops = N` the client is the
Nth entry counting from the right.

    client -> router -> nginx -> api          X-Forwarded-For: <forged...>, <client>, <router>
                                              (the socket peer is nginx)
    trusted_proxy_hops = 2  ->  <client>

0 (the default) ignores the header altogether and uses the socket peer. That cannot be
forged, but behind a reverse proxy it is the proxy's own address, so every user shares one.
Set it to the number of proxies in front of the API. If the chain is shorter than expected
(a request that skipped a proxy), the header is not trusted and the peer is used instead.

This only holds when the API is reachable solely through that chain. A request sent to it
directly can carry any header it likes, so keep the API off the public network.

IPv6 clients are bucketed by /64. A single subscriber is routinely handed a whole /64, so
keying on the full address would give an attacker 2**64 fresh budgets.
"""

import ipaddress
from typing import Final

import structlog
from starlette.requests import Request

__all__ = ["UNKNOWN_CLIENT", "check_proxy_configuration", "resolve_client_ip"]

logger = structlog.get_logger(__name__)

UNKNOWN_CLIENT: Final = "unknown"
_IPV6_BUCKET_PREFIX: Final = 64
_FORWARDING_HEADERS: Final = ("x-forwarded-for", "forwarded", "x-real-ip")

IPAddress = ipaddress.IPv4Address | ipaddress.IPv6Address

# Which misconfiguration warnings this process has already given. Each is worth saying once.
_reported: set[str] = set()


def resolve_client_ip(request: Request, trusted_proxy_hops: int) -> str:
    """The address to rate-limit this request under; never raises, never empty."""
    if trusted_proxy_hops > 0:
        chain = _forwarded_chain(request)
        if len(chain) >= trusted_proxy_hops:
            claimed = _parse(chain[-trusted_proxy_hops])
            if claimed is not None:
                return _bucket(claimed)
    peer = _parse(request.client.host) if request.client else None
    return _bucket(peer) if peer is not None else UNKNOWN_CLIENT


def check_proxy_configuration(request: Request, trusted_proxy_hops: int) -> None:
    """
    Warn, once each, when the requests themselves show `trusted_proxy_hops` is wrong.

    Nothing else tells an operator. A wrong value does not fail, it quietly changes what the
    per-IP limits mean: too low and everyone behind the proxy shares one address, so a few
    failed logins block them all together. The requests give it away, though. A forwarding
    header arriving while the setting is 0 means a proxy exists; a chain shorter than the
    setting means the count is too high (or a request skipped the proxy).

    Never changes the answer `resolve_client_ip` gives, and logs at most once per condition
    per process, so a probe cannot use it to fill the log.
    """
    peer = request.client.host if request.client else UNKNOWN_CLIENT
    if trusted_proxy_hops == 0:
        present = [name for name in _FORWARDING_HEADERS if name in request.headers]
        if present:
            _warn_once(
                "hops_too_low",
                "trusted_proxy_hops_too_low",
                peer=peer,
                forwarding_headers=present,
                detail=(
                    "A request carried a forwarding header while TRUSTED_PROXY_HOPS is 0, "
                    "so the API sees the proxy's address as the client. Every user behind "
                    "it shares one rate-limit address. Set TRUSTED_PROXY_HOPS to the "
                    "number of proxies in front of the API."
                ),
            )
    elif len(_forwarded_chain(request)) < trusted_proxy_hops:
        _warn_once(
            "chain_too_short",
            "trusted_proxy_chain_shorter_than_hops",
            peer=peer,
            trusted_proxy_hops=trusted_proxy_hops,
            forwarded_entries=len(_forwarded_chain(request)),
            detail=(
                "X-Forwarded-For has fewer entries than TRUSTED_PROXY_HOPS, so it was not "
                "trusted and the socket peer is used instead. Either the setting is higher "
                "than the real number of proxies, or a request reached the API without "
                "passing through them."
            ),
        )


def _warn_once(key: str, event: str, **fields: object) -> None:
    if key in _reported:
        return
    _reported.add(key)
    logger.warning(event, **fields)


def _forwarded_chain(request: Request) -> list[str]:
    """Every `X-Forwarded-For` entry in order. Proxies may send several header lines."""
    entries: list[str] = []
    for line in request.headers.getlist("x-forwarded-for"):
        entries.extend(part.strip() for part in line.split(",") if part.strip())
    return entries


def _parse(text: str) -> IPAddress | None:
    """An IP from a header or socket value, tolerating a port and brackets; else None."""
    candidate = text.strip()
    if candidate.startswith("["):  # [v6]:port
        closing = candidate.find("]")
        if closing == -1:
            return None
        candidate = candidate[1:closing]
    elif candidate.count(":") == 1:  # v4:port (a bare v6 address has several colons)
        candidate = candidate.split(":", 1)[0]
    try:
        address: IPAddress = ipaddress.ip_address(candidate)
    except ValueError:
        return None
    if isinstance(address, ipaddress.IPv6Address) and address.ipv4_mapped is not None:
        return address.ipv4_mapped
    return address


def _bucket(address: IPAddress) -> str:
    if isinstance(address, ipaddress.IPv4Address):
        return str(address)
    # Rebuilt from the integer so an interface scope (fe80::1%eth0) cannot split a bucket.
    network = ipaddress.IPv6Network((int(address), _IPV6_BUCKET_PREFIX), strict=False)
    return str(network)
```

### 3.8 Edit: `src/config/settings.py`

Add these fields to the `Settings` class (next to `REDIS_URL`). If `REDIS_URL` has no
description yet, add one saying it also holds the login-throttle counters.

```python
    # ─── Login throttling (brute-force / credential-stuffing protection) ───
    LOGIN_THROTTLE_ENABLED: bool = Field(
        default=True,
        description=(
            "Master switch. Leave on; it exists so a misconfigured limit can be turned off "
            "without a deploy while it is corrected."
        ),
    )
    LOGIN_ATTEMPT_WINDOW_SECONDS: int = Field(
        default=300,
        ge=10,
        le=86_400,
        description="How long attempts are remembered. Fixed from the first attempt, not sliding.",
    )
    LOGIN_MAX_ATTEMPTS_PER_ACCOUNT_IP: int = Field(
        default=5,
        ge=1,
        le=1_000,
        description=(
            "Attempts at one account from one IP per window before that account is locked "
            "for that IP."
        ),
    )
    LOGIN_MAX_ATTEMPTS_PER_ACCOUNT: int = Field(
        default=20,
        ge=1,
        le=10_000,
        description=(
            "Attempts at one account, from all addresses it has no successful login from, "
            "together per window before it is locked for such addresses. Familiar addresses "
            "are neither counted nor locked by it."
        ),
    )
    LOGIN_FAMILIAR_IP_TTL_SECONDS: int = Field(
        default=2_592_000,
        ge=0,
        le=31_536_000,
        description=(
            "How long an address stays familiar to an account after a successful login from "
            "it (each login restarts the time). Default 30 days. 0 turns the exemption off."
        ),
    )
    LOGIN_MAX_FAILURES_PER_IP: int = Field(
        default=50,
        ge=1,
        le=100_000,
        description="Failed logins from one IP per window, across all usernames.",
    )
    LOGIN_LOCKOUT_SECONDS: int = Field(
        default=900,
        ge=10,
        le=86_400,
        description="How long a lockout lasts. Fixed: attempts during it do not extend it.",
    )
    TRUSTED_PROXY_HOPS: int = Field(
        default=0,
        ge=0,
        le=10,
        description=(
            "How many reverse proxies sit between the internet and this API. 0 ignores "
            "X-Forwarded-For. Example: load balancer -> nginx -> api is 2. See section 3.16."
        ),
    )
```

### 3.9 Edit: `src/domain/entities/audit_log.py`

In the `AuditAction` enum, after `LOGIN_FAILED`:

```python
    LOGIN_FAILED = "LOGIN_FAILED"
    # An account (or address) was locked after repeated failed logins. One entry per
    # lockout, not one per refused attempt: see LoginThrottleService.
    LOGIN_LOCKED = "LOGIN_LOCKED"
```

### 3.10 Edit: `src/infrastructure/security/audit_service.py`

Add this method to `AuditService`, after `log_login` (adapt `self.log(...)` keyword names if
yours differ):

```python
    async def log_login_locked(
        self,
        *,
        username: str,
        ip_address: str = "",
        user_agent: str = "",
        reason: str = "",
    ) -> None:
        """
        Log that repeated failed logins locked an account (or an account for one address).

        Written once when the lockout starts, never per refused attempt: an attacker who
        keeps hammering a locked account would otherwise fill `audit_logs` for free.
        """
        await self.log(
            actor_username=username,
            action=AuditAction.LOGIN_LOCKED,
            resource_type="Authentication",
            resource_id=username,
            ip_address=ip_address,
            user_agent=user_agent,
            metadata={"reason": reason} if reason else None,
        )
```

### 3.11 Edit: `src/api/v1/dependencies.py`

Add imports at the top:

```python
from functools import lru_cache

from fastapi import Request            # add to the existing fastapi import

from src.api.client_ip import check_proxy_configuration, resolve_client_ip
from src.application.ports.login_attempt_store import ILoginAttemptStore
from src.application.services.login_throttle_service import (
    LoginThrottlePolicy,
    LoginThrottleService,
)
```

Add these three functions (anywhere before `get_current_user`):

```python
def get_client_ip(request: Request) -> str:
    """
    The address to rate-limit this request under.

    Not the address written to the audit log: that one reads the left-most X-Forwarded-For
    hop, which the client controls. This one comes from the socket peer, or from
    X-Forwarded-For counted from the right by TRUSTED_PROXY_HOPS, so a forged header cannot
    move it. See `src.api.client_ip`.
    """
    from src.config.settings import settings

    check_proxy_configuration(request, settings.TRUSTED_PROXY_HOPS)
    return resolve_client_ip(request, settings.TRUSTED_PROXY_HOPS)


@lru_cache(maxsize=1)
def _login_attempt_store() -> ILoginAttemptStore:
    """
    The process-wide login-attempt store.

    One per process rather than per request: the counters have to outlive a request, and a
    Redis client wants its connection pool reused. Redis when REDIS_URL is set, falling back
    to per-process counters if it is unreachable; per-process alone when it is empty.
    """
    from redis.asyncio import Redis

    from src.config.settings import settings
    from src.infrastructure.cache.in_memory_login_attempt_store import (
        InMemoryLoginAttemptStore,
    )
    from src.infrastructure.cache.redis_login_attempt_store import RedisLoginAttemptStore
    from src.infrastructure.cache.resilient_login_attempt_store import (
        ResilientLoginAttemptStore,
    )

    in_process = InMemoryLoginAttemptStore()
    if not settings.REDIS_URL:
        return in_process
    # Short timeouts: when Redis is down, a login should not wait on it. The resilient
    # wrapper then stops trying for a while instead of paying the timeout on every call.
    client = Redis.from_url(
        settings.REDIS_URL,
        decode_responses=True,
        socket_connect_timeout=1.0,
        socket_timeout=1.0,
    )
    return ResilientLoginAttemptStore(RedisLoginAttemptStore(client), in_process)


def get_login_throttle_service() -> LoginThrottleService:
    """Provide the login throttle, configured from settings."""
    from src.config.settings import settings

    policy = LoginThrottlePolicy(
        enabled=settings.LOGIN_THROTTLE_ENABLED,
        window_seconds=settings.LOGIN_ATTEMPT_WINDOW_SECONDS,
        max_attempts_per_account_ip=settings.LOGIN_MAX_ATTEMPTS_PER_ACCOUNT_IP,
        max_attempts_per_account=settings.LOGIN_MAX_ATTEMPTS_PER_ACCOUNT,
        max_failures_per_ip=settings.LOGIN_MAX_FAILURES_PER_IP,
        lockout_seconds=settings.LOGIN_LOCKOUT_SECONDS,
        familiar_ip_ttl_seconds=settings.LOGIN_FAMILIAR_IP_TTL_SECONDS,
    )
    return LoginThrottleService(_login_attempt_store(), policy)
```

Layering note: the controller must not import SQLAlchemy or build infrastructure objects
inline. That is why the Redis/in-memory wiring lives here, in `dependencies.py`, and the
controller only receives `LoginThrottleService` through `Depends()`.

### 3.12 Edit: `src/api/v1/endpoints/auth_controller.py` (the login route)

Imports to add:

```python
from fastapi.responses import JSONResponse

from src.api.v1.dependencies import get_client_ip, get_login_throttle_service   # add to existing import
from src.application.services.login_throttle_service import (
    LoginThrottledError,
    LoginThrottleService,
)
```

Module-level additions:

```python
# One message for every throttled attempt, whichever limit refused it and whether or not the
# account exists, so the response reveals nothing about either.
THROTTLED_DETAIL = "Too many login attempts. Please try again later."

# Why a rejected login was rejected, for the audit trail. Never sent to the client.
_REJECTION_REASONS: dict[type[AuthenticationError], str] = {
    InvalidCredentialsError: "Invalid credentials",
    UserInactiveError: "User inactive",
    UserBlockedError: "User blocked",
}


def _login_refused(
    status_code: int, detail: str, *, retry_after: int | None = None
) -> JSONResponse:
    """
    The error response for a login attempt, returned rather than raised.

    Raising HTTPException makes `get_db_session` roll the request back, which would discard
    the audit row written a moment earlier: a failed login would be logged and then
    un-logged. Returning the response lets the session commit. The body and status are what
    HTTPException produced, so clients see no difference.
    """
    headers = {"Retry-After": str(retry_after)} if retry_after is not None else None
    return JSONResponse(status_code=status_code, content={"detail": detail}, headers=headers)
```

Keep the existing `_get_client_ip` helper unchanged. It is for audit rows only; the throttle
uses `get_client_ip`. Do not merge them.

The route. Keep whatever the existing code does after a successful login (user lookup, audit,
cookie, token response); only the parts shown change:

```python
@router.post(
    "/login",
    response_model=TokenResponse,
    response_model_exclude_none=True,
    status_code=status.HTTP_200_OK,
    summary="Authenticate user",
    description=(
        "Validate credentials and set the refresh cookie; returns the access token. "
        "Repeated failures are throttled per account and per client IP: once a limit is "
        "reached the endpoint answers 429 without checking the password, and `Retry-After` "
        "says how many seconds to wait."
    ),
    responses={
        status.HTTP_429_TOO_MANY_REQUESTS: {
            "description": "Too many attempts. Wait `Retry-After` seconds before retrying.",
            "headers": {
                "Retry-After": {
                    "description": "Seconds until another attempt is accepted.",
                    "schema": {"type": "integer"},
                }
            },
        }
    },
)
@log_execution
async def login(
    request: LoginRequest,
    http_request: Request,
    response: Response,
    auth_manager: AuthManager = Depends(get_auth_manager),
    user_repo: IUserRepository = Depends(get_user_repository),
    audit: AuditService = Depends(get_audit_service),
    throttle: LoginThrottleService = Depends(get_login_throttle_service),
    throttle_ip: str = Depends(get_client_ip),
) -> TokenResponse | JSONResponse:
    ip = _get_client_ip(http_request)
    user_agent = http_request.headers.get("user-agent", "")

    # 1. Before anything is looked up or verified: a throttled request must cost no bcrypt
    #    and must never reach the corporate AD service.
    try:
        ticket = await throttle.begin_attempt(request.username, throttle_ip)
    except LoginThrottledError as e:
        if e.lockout_started:
            await audit.log_login_locked(
                username=request.username, ip_address=ip, user_agent=user_agent,
                reason=f"Locked for {e.retry_after_seconds}s after repeated failed "
                f"logins ({e.reason.value})",
            )
        return _login_refused(
            status.HTTP_429_TOO_MANY_REQUESTS, THROTTLED_DETAIL, retry_after=e.retry_after_seconds
        )

    # 2. Credentials. A failure is counted and audited, and RETURNED (not raised).
    try:
        result = await auth_manager.login(
            username=request.username,
            password=request.password,
        )
    except (InvalidCredentialsError, UserInactiveError, UserBlockedError) as e:
        await throttle.record_failure(ticket)
        await audit.log_login(
            user_id=None, username=request.username, success=False,
            ip_address=ip, user_agent=user_agent, reason=_REJECTION_REASONS[type(e)],
        )
        return _login_refused(e.status_code, e.message)

    # 3. Success: forget this address's typos, remember the address as familiar.
    await throttle.record_success(ticket)

    # ... existing success path unchanged: success audit row, refresh cookie, TokenResponse
```

If your `login` currently has one `except` per exception type that each `raise
HTTPException(...)`, replace them all with the single block above.

### 3.13 Edit: `src/main.py`

Imports: ensure `get_logger` is imported from your structured logger module.

Add this function above `lifespan`, and call it from `lifespan` after logging is configured:

```python
def log_login_throttle_configuration() -> None:
    """
    Say at startup how login throttling is set up, and warn about the one setting that
    silently changes what it means.

    Behind a reverse proxy the API sees the proxy's address as the client, so with
    TRUSTED_PROXY_HOPS left at 0 every user shares one per-IP budget. COOKIE_SECURE is the
    existing "this is a real deployment" switch, so it is what the warning keys on.
    """
    log = get_logger("login_throttle")
    if not settings.LOGIN_THROTTLE_ENABLED:
        log.warning(
            "login_throttle_disabled",
            detail="LOGIN_THROTTLE_ENABLED is false: login is not protected against guessing",
        )
        return
    log.info(
        "login_throttle_configured",
        window_seconds=settings.LOGIN_ATTEMPT_WINDOW_SECONDS,
        max_attempts_per_account_ip=settings.LOGIN_MAX_ATTEMPTS_PER_ACCOUNT_IP,
        max_attempts_per_account=settings.LOGIN_MAX_ATTEMPTS_PER_ACCOUNT,
        max_failures_per_ip=settings.LOGIN_MAX_FAILURES_PER_IP,
        lockout_seconds=settings.LOGIN_LOCKOUT_SECONDS,
        familiar_ip_ttl_seconds=settings.LOGIN_FAMILIAR_IP_TTL_SECONDS,
        trusted_proxy_hops=settings.TRUSTED_PROXY_HOPS,
        shared_store="redis" if settings.REDIS_URL else "none (per-process counters)",
    )
    if settings.TRUSTED_PROXY_HOPS == 0 and settings.COOKIE_SECURE:
        log.warning(
            "login_throttle_proxy_hops_unset",
            detail=(
                "TRUSTED_PROXY_HOPS is 0, so X-Forwarded-For is ignored. If the API runs "
                "behind a reverse proxy, every user shares the proxy's address and the "
                "per-IP limit applies to all of them together. Set it to the number of "
                "proxies in front of the API."
            ),
        )
```

In `lifespan`, after `configure_logging()`:

```python
    log_login_throttle_configuration()
```

In the `CORSMiddleware` call add (the browser cannot read `Retry-After` cross-origin
otherwise):

```python
    expose_headers=["Retry-After"],
```

### 3.14 Edit: `tests/conftest.py`

In the shared HTTP `client` fixture, give every test its own throttle counters. Without this,
failed logins from one test leak into the next (all tests arrive from the same address) and
login tests start failing at random.

```python
    from src.api.v1.dependencies import get_login_throttle_service
    from src.application.services.login_throttle_service import (
        LoginThrottlePolicy,
        LoginThrottleService,
    )
    from src.infrastructure.cache.in_memory_login_attempt_store import (
        InMemoryLoginAttemptStore,
    )

    throttle_store = InMemoryLoginAttemptStore()
    app.dependency_overrides[get_login_throttle_service] = lambda: LoginThrottleService(
        throttle_store, LoginThrottlePolicy()
    )
```

(Put it next to the existing `app.dependency_overrides[get_db_session] = ...` line.)

### 3.15 Edit: `.env.example`

```dotenv
# ─── Login throttling (brute-force / credential-stuffing protection) ───
# Applies to POST /api/v1/auth/login. Counters live in Redis (REDIS_URL) so every API replica
# shares them. If Redis is unreachable, or REDIS_URL is empty, they fall back to per-process
# counters, which multiply across replicas: run Redis wherever there is more than one process.
LOGIN_THROTTLE_ENABLED=true
LOGIN_ATTEMPT_WINDOW_SECONDS=300
LOGIN_MAX_ATTEMPTS_PER_ACCOUNT_IP=5
LOGIN_MAX_ATTEMPTS_PER_ACCOUNT=20
LOGIN_FAMILIAR_IP_TTL_SECONDS=2592000
LOGIN_MAX_FAILURES_PER_IP=50
LOGIN_LOCKOUT_SECONDS=900
# Number of reverse proxies between the internet and this API (see section 3.16).
#   client -> api                                    0
#   client -> nginx -> api                           1
#   client -> load balancer -> nginx -> api          2   (verify against your deployment)
TRUSTED_PROXY_HOPS=0
```

### 3.16 `TRUSTED_PROXY_HOPS` (easy to get wrong)

The API finds the real client address by counting `X-Forwarded-For` entries **from the
right**. Each proxy appends the address it saw, so the left side may have been written by the
client.

| Chain | Value |
|-------|-------|
| client, API | `0` |
| client, nginx, API | `1` |
| client, load balancer or ingress, nginx, API | `2` |

- Too low (the default `0` behind a proxy): every user shares the proxy's address, so a few
  failed logins lock everyone.
- Too high: the API trusts entries the client wrote, and an attacker can dodge the limits.
- The API must be reachable **only** through that chain.
- If the value looks wrong the app logs `trusted_proxy_hops_too_low` or
  `trusted_proxy_chain_shorter_than_hops` once. **Check the logs for these after every deploy.**

### 3.17 Backend tests (required in the same change)

Follow your repository's testing standard: unit tests for services use hand-written fakes (not
`AsyncMock`), HTTP tests use `app.dependency_overrides` (not `unittest.mock.patch`).

**Fake store** for the service tests: `tests/unit/application/login_throttle_fakes.py`. It
yields to the event loop on every call so concurrency tests mean something, and has a clock
the test moves by hand.

```python
import asyncio
import math

from src.application.ports.login_attempt_store import CounterState, ILoginAttemptStore


class FakeLoginAttemptStore(ILoginAttemptStore):
    """Counters and flags in a dict, expiring against a hand-driven clock."""

    def __init__(self) -> None:
        self.now = 0.0
        self._entries: dict[str, tuple[int, float]] = {}  # key -> (value, expires_at)

    def advance(self, seconds: float) -> None:
        self.now += seconds

    def live_keys(self) -> list[str]:
        return [key for key in list(self._entries) if self._live(key) is not None]

    def count(self, key: str) -> int | None:
        entry = self._live(key)
        return None if entry is None else entry[0]

    async def peek(self, key: str) -> CounterState | None:
        await asyncio.sleep(0)
        entry = self._live(key)
        return None if entry is None else CounterState(entry[0], self._seconds_left(entry[1]))

    async def increment(self, key: str, window_seconds: int) -> CounterState:
        await asyncio.sleep(0)
        entry = self._live(key) or (0, self.now + window_seconds)
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
```

(If `tests/` has no `__init__.py`, tests import it as `from login_throttle_fakes import
FakeLoginAttemptStore`, so keep it in the same folder as the test.)

Write these test files. Use the policy `window=300, per_ip=5, per_account=20, per_ip_failures=50,
lockout=900, familiar_ttl=86400`.

**`tests/unit/application/test_login_throttle_service.py`** (class-grouped, one behaviour each):

- *Account from one IP:* the first 5 attempts are admitted; the 6th raises with reason
  `ACCOUNT_IP_LOCKOUT`, `lockout_started=True`, `retry_after == 900`; later attempts are refused
  with `lockout_started=False`; a lockout is not extended by attempts during it
  (advance 600 s: retry_after is 300; advance 301 more: admitted); retry_after counts down; a
  fresh budget after the lockout; the same account from another IP is **not** locked; another
  account from the same IP is not locked; counts do not carry into the next window.
- *Many IPs (strangers):* 4 addresses × 5 failures, then a 5th new address is refused with
  `ACCOUNT_UNFAMILIAR_LOCKOUT` and `lockout_started=True`; every other unfamiliar address is
  then refused with `lockout_started=False`; when both locks apply the longer one is reported.
- *Familiar addresses:* after a successful login from IP A, a stranger-lockout (spread attack)
  does not block A; a stranger with the correct password **is** still blocked; A is still
  limited to its own 5 attempts (`ACCOUNT_IP_LOCKOUT`) and to the 50-failure IP limit;
  failures from familiar addresses are not counted toward the stranger cap; the owner's
  success does **not** clear the strangers' count; familiarity is per account (bob's
  login does not make the IP familiar to alice); a failed login does not make an address
  familiar; familiarity expires `familiar_ttl` after the last login and each login restarts
  it; `familiar_ip_ttl_seconds=0` disables it and stores nothing; an unresolved address
  (`""`) is never remembered; the marker key does not contain the username; a burst of 50
  parallel attempts from a familiar address admits exactly 5.
- *Failures per IP:* 50 failures with different usernames lock the IP (`IP_LIMIT`,
  `lockout_started=False`); retry_after is the rest of the window; other IPs unaffected;
  **successful logins never use up the IP budget**; budget returns after the window.
- *Success:* clears earlier failures from that address; leaves the IP failure count alone;
  does not clear another account's count.
- *Normalisation:* `admin`, `Admin`, `ADMIN`, ` admin `, full-width `ａｄｍｉｎ` share one
  budget; the username is not stored in clear in any key; nonexistent accounts are throttled
  identically.
- *Concurrency:* 50 parallel `begin_attempt` calls admit exactly 5 and exactly **one** has
  `lockout_started=True`.
- *Disabled:* with `enabled=False` nothing is refused and nothing is stored.
- *Logging:* one `login_lockout_started` warning per lockout, without secrets; one
  `login_ip_limit_reached` when the IP limit is hit; a username containing a newline cannot
  forge a log line (`"\n" not in error.account`, length ≤ 64).

**`tests/unit/infrastructure/test_in_memory_login_attempt_store.py`** (injectable clock):
increment creates with the window as lifetime and never extends it; expired counters restart;
counters independent; 200 concurrent increments are never lost; `peek` does not change state and
never reports 0 seconds left; `set_lock` has exactly one winner among 50 concurrent callers and
never extends an existing flag; markers: set, expire, restart lifetime when remembered again,
removable, invisible to counters, refreshing one evicts nothing, a refreshed marker is "recent"
for eviction; `delete` of a missing key is fine; bound: `max_keys=0` raises, oldest evicted when
full, expired evicted before live, 10,000 unique keys never exceed the cap, a lock can still be
set when full.

**`tests/unit/infrastructure/test_redis_login_attempt_store.py`**: use a small hand-written
Redis fake (GET, SET with `nx`/`ex`, INCR, TTL, EXISTS, DEL, MULTI/EXEC pipelines) and assert the
**shape** of what is sent: `increment` is one transaction with commands in the order
`set(nx, ex=window)`, `incr`, `ttl` (so a counter can never exist without an expiry);
`peek` is a non-transaction pipeline; `remember` is a plain `SET key 1 EX n` **without** `nx`;
a flag with no expiry is deleted instead of locking forever; a TTL of 0 is reported as 1.

**`tests/unit/infrastructure/test_resilient_login_attempt_store.py`**: any backend exception
degrades to the fallback instead of failing (parametrize over every operation including
`remember` and `is_remembered`); the primary is not retried until the pause is over; one
WARNING per outage; one INFO on recovery; no log output when healthy; markers set before an
outage are not visible to the fallback (fails safe: the address reverts to a stranger).

**`tests/unit/test_client_ip.py`**: hops=0 ignores the header; hops=N takes the Nth entry from
the right; a forged left-most entry is ignored; chain shorter than hops falls back to the
peer; IPv4-mapped IPv6 collapses to IPv4; IPv6 bucketed to /64; garbage/ports/brackets
tolerated; both warnings fire once per process only (reset the module's `_reported` set between
tests).

**`tests/unit/test_login_throttle_startup.py`**: `log_login_throttle_configuration` reports the
settings (including `familiar_ip_ttl_seconds`); warns when hops=0 and `COOKIE_SECURE=true`; no
warning when hops≥1 or `COOKIE_SECURE=false`; one `login_throttle_disabled` warning when off.

**`tests/integration/test_login_throttle_api.py`**: full request path through the ASGI app with
a small policy (3 per account/IP, 6 per account, 5 failures per IP, 60 s lockout) installed via
`app.dependency_overrides[get_login_throttle_service]`. Use a real bcrypt hash with `rounds=4`
so tests stay fast. Cover: 401 ×3 then 429; `Retry-After` header; generic 429 body
(`Too many login attempts. Please try again later.`); the correct password is refused (and no
cookie/token) during a lockout; a refused attempt never calls `auth_manager.login`; a burst of
30 parallel requests runs credentials at most 3 times; a nonexistent account is throttled
exactly like a real one (same statuses, bodies, `Retry-After`); a good login clears the count;
logging in as yourself does not clear someone else's; the same account from another IP still
logs in; one IP trying many usernames is stopped after 5 failures; a spread-out attack is
stopped by the account-wide cap; **the owner on a familiar IP still logs in (HTTP 200) while a
stranger with the right password gets 429**; a familiar IP cannot guess without limit; with no
prior login the owner on a new IP is locked out (pin this known limitation); rotating a forged
`X-Forwarded-For` with hops=0 does not buy a new budget; with hops=1 the proxy-reported
address is what is throttled and a client-prepended entry is ignored; `LOGIN_THROTTLE_ENABLED`
off never refuses; `Retry-After` is in `Access-Control-Expose-Headers`.
Audit trail tests need a session that commits like production (commit on return, rollback on
raise): failed logins are recorded and **the record survives the error response**; a lockout is
recorded exactly once; refused attempts write nothing (25 more attempts add no rows); the
`LOGIN_LOCKED` row names the account and the reason (`account_ip_lockout` /
`account_unfamiliar_lockout`).

Mutation check worth doing once: break each of these and confirm a test fails, otherwise the
test is not guarding anything: the stranger lock applying to familiar IPs; familiar attempts
counted toward the stranger cap; a success clearing the stranger count; a failed login
creating a familiar marker; an unresolved address being remembered; `remember` never called.

---

## 4. Frontend

### 4.1 Login throttling (EMC-WA-1)

**`src/shared/services/apiClient.ts`.** A 401 from `/auth/login` or `/auth/refresh` is that
endpoint's own answer, not an expired session. If the response interceptor refreshes and
replays it, one click on Sign in counts as **two** attempts against the throttle, and a user
with no cookie sees "Missing refresh token" instead of "Invalid username or password".

Before:

```ts
const isAuthRefreshCall = originalRequest?.url?.includes('/auth/refresh');
if (error.response?.status === 401 && !originalRequest._retry && !isAuthRefreshCall) {
```

After (you probably already have an `isSessionEndpoint` helper for the request interceptor;
if not, add it):

```ts
const isSessionEndpoint = (url?: string): boolean =>
  Boolean(url && (url.includes('/auth/login') || url.includes('/auth/refresh')));

// ... in the response interceptor:
const isSessionCall = isSessionEndpoint(originalRequest?.url);
if (error.response?.status === 401 && !originalRequest._retry && !isSessionCall) {
```

**`src/shared/utils/apiError.ts`.** Add:

```ts
/**
 * Seconds the server asked the caller to wait, from a `Retry-After` header that holds a
 * number of seconds. Null when the header is absent or is anything else.
 */
export const getRetryAfterSeconds = (error: unknown): number | null => {
  const headers = (error as { response?: { headers?: Record<string, unknown> } })?.response
    ?.headers;
  const raw = headers?.['retry-after'];
  const seconds = typeof raw === 'string' || typeof raw === 'number' ? Number(raw) : NaN;
  return Number.isFinite(seconds) && seconds > 0 ? Math.ceil(seconds) : null;
};

/** A wait as people say it: "less than a minute", "about a minute", "about 15 minutes". */
export const formatWait = (seconds: number): string => {
  if (seconds < 60) return 'less than a minute';
  const minutes = Math.ceil(seconds / 60);
  return minutes === 1 ? 'about a minute' : `about ${minutes} minutes`;
};
```

**`src/features/authentication/store/authSlice.ts`.** Import the two helpers, add this above
`loginThunk`, and make the thunk's `catch` use it
(`return rejectWithValue(loginErrorMessage(error));`):

```ts
const loginErrorMessage = (error: unknown): string => {
  const status = (error as { response?: { status?: number } })?.response?.status;
  if (status === 429) {
    const seconds = getRetryAfterSeconds(error);
    if (seconds !== null) {
      return `Too many login attempts. Please try again in ${formatWait(seconds)}.`;
    }
    return extractApiError(error, 'Too many login attempts. Please try again later.');
  }
  return extractApiError(error, 'Login failed. Please try again.');
};
```

**Audit log page** (`AuditLogsPage.tsx` or wherever audit actions are listed). Add the filter
option `{ label: 'Login Locked', value: 'LOGIN_LOCKED' }` and treat `LOGIN_LOCKED` like
`LOGIN_FAILED` when choosing the tag severity (`danger`).

### 4.2 Strict CSP (EMC-WA-3)

PrimeReact 10.6+ ships `primereact.min.css` empty and injects its component CSS at runtime as
`<style>` elements. Under a CSP without `'unsafe-inline'` those elements must carry a nonce.
Check your version in `node_modules/primereact/package.json`.

**New file `src/shared/utils/cspNonce.ts`:**

```ts
/**
 * The Content-Security-Policy nonce for this page load, if the server gave us one.
 *
 * The policy is `style-src 'self' 'nonce-<random>'` with no `'unsafe-inline'`, so a
 * `<style>` element only applies if it carries that nonce. PrimeReact creates its component
 * styles at runtime (since 10.6 `primereact.min.css` ships empty), so it needs the nonce to
 * put on each one. The web server writes a fresh value into the page's
 * `<meta name="csp-nonce">` on every response, and the same value into the policy header.
 *
 * Returns undefined when there is no usable nonce: the Vite dev server and the unit tests,
 * where no policy is enforced and none is needed, and a page served without the server's
 * substitution, where the placeholder is still in place. PrimeReact then injects its styles
 * without a nonce, which is exactly right when there is no policy to satisfy.
 */
export const CSP_NONCE_META_NAME = 'csp-nonce';
/** What index.html ships with; the server swaps it for the real value. */
export const CSP_NONCE_PLACEHOLDER = '__CSP_NONCE__';

export const readCspNonce = (doc: Document = document): string | undefined => {
  const content = doc
    .querySelector(`meta[name="${CSP_NONCE_META_NAME}"]`)
    ?.getAttribute('content')
    ?.trim();
  if (!content || content === CSP_NONCE_PLACEHOLDER) return undefined;
  return content;
};
```

**`index.html`**, inside `<head>`:

```html
<!-- Per-response nonce, filled in by the web server. See src/shared/utils/cspNonce.ts -->
<meta name="csp-nonce" content="__CSP_NONCE__" />
```

**`src/app/App.tsx`:**

```tsx
import { readCspNonce } from '@shared/utils/cspNonce';

// Read once: it is fixed for the life of the page, and PrimeReact keeps its own copy.
const cspNonce = readCspNonce();

// ...
<PrimeReactProvider value={{ nonce: cspNonce }}>
  <AppRouter />
</PrimeReactProvider>
```

**Remove every inline `style="..."` that is built as a string.** A nonce authorises `<style>`
elements, **not** `style=""` attributes. Search the whole frontend for:

```
dangerouslySetInnerHTML     innerHTML     insertAdjacentHTML     style="
```

React `style={{ ... }}` props are fine (they go through the CSSOM, which CSP does not restrict).
The typical offender is a syntax highlighter that wraps tokens in
`<span style="color:#9C27B0">`. Change it to classes. For a JSON viewer
(`ContentViewerDialog.tsx`):

```ts
.replace(/"([^"]+)"(?=\s*:)/g, '<span class="em-json-key">"$1"</span>')        // keys
.replace(/:\s*"([^"]*)"/g, ': <span class="em-json-string">"$1"</span>')       // string values
.replace(/:\s*(\d+\.?\d*)/g, ': <span class="em-json-number">$1</span>')       // numbers
.replace(/:\s*(true|false|null)/g, ': <span class="em-json-literal">$1</span>') // booleans, null
```

and append to the global stylesheet (`theme-overrides.css`):

```css
.em-json-key {
  color: #9c27b0;
}
.em-json-string {
  color: #2e7d32;
}
.em-json-number {
  color: #1565c0;
}
.em-json-literal {
  color: #e65100;
}
```

If a style attribute slips in later, the browser console shows "Refused to apply inline style".
The fix is a class, never `'unsafe-inline'`.

### 4.3 Frontend tests (required in the same change)

Use your existing helpers (`renderWithProviders`, MSW `server.use`, `selectDropdownOption`).

- **`apiClient` tests:** a rejected login (401) is **not** refreshed and replayed (login
  endpoint called exactly once, refresh endpoint never called); the login's own error body is
  surfaced when there is no refresh cookie, and the session-expired handler is not called; a
  429 passes through untouched with `retry-after` readable on the response; an ordinary
  endpoint with an expired token **still** refreshes and retries once (guard against switching
  off the existing behaviour).
- **`authSlice` tests:** 429 with `Retry-After: 900` gives "Too many login attempts. Please try
  again in about 15 minutes."; 429 without the header falls back to the server's wording;
  a 429 leaves `isAuthenticated=false` and no access token; the message is identical whichever
  account was tried.
- **`LoginPage` test:** one click sends exactly one login request and zero refresh requests,
  and shows the real reason ("Invalid username or password"); a 429 shows the wait time; the
  message clears and the user can try again on the next submit.
- **`apiError` tests:** `getRetryAfterSeconds` (seconds string, numeric, fraction rounds up,
  absent, and null for `soon`, `0`, `-5`, an HTTP-date, empty string, an `Error`, `undefined`);
  `formatWait` (1→"less than a minute", 59→same, 60→"about a minute", 61→"about 2 minutes",
  900→"about 15 minutes", 901→"about 16 minutes").
- **`cspNonce` tests:** returns the meta value; trims whitespace; undefined when the tag is
  missing, when it still holds the placeholder, or when it is empty/blank; reads from a given
  `Document`.
- **JSON viewer test:** one `.em-json-key/string/number/literal` per token kind; the injected
  markup contains **no** `style=` attribute; markup inside the data (`<img onerror=...>`) is
  still escaped, not injected.
- **Audit page test:** `LOGIN_LOCKED` and `LOGIN_FAILED` render as `p-tag-danger`,
  `LOGIN_SUCCESS` as `p-tag-success`; choosing "Login Locked" in the action filter sends
  `action=LOGIN_LOCKED` to the API.

---

## 5. nginx (EMC-WA-2, 3, 4)

These findings are fixed in the nginx that serves the SPA, not in application code. Hand this
section to whoever owns the nginx config (DevOps). Merge the directives below into the existing
config rather than replacing it wholesale; the reference file that follows shows where each
piece goes.

### 5.1 What each piece does

| Directive | Why |
|-----------|-----|
| `server_tokens off;` | WA-2: no version in the `Server` header or nginx's built-in error pages. |
| `error_page ... /_errors/client.html` and `/_errors/server.html` (`internal`, `return 200 '<html>'`) | WA-2: generic pages that name nothing. The **original** status (404, 502, ...) is preserved because `error_page` has no `=code`. |
| `add_header Content-Security-Policy "... style-src 'self' 'nonce-$request_id'; ..." always;` | WA-3. |
| `location = /index.html { sub_filter '__CSP_NONCE__' $request_id; sub_filter_once on; etag off; if_modified_since off; }` | Writes the same nonce into the page that is in the header. |
| `map $uri $app_cache_control { /index.html "no-store"; ... }` | `index.html` must never be cached, or an old nonce meets a new header and every runtime style is lost. |
| `add_header Cross-Origin-Embedder-Policy "require-corp" always;` and `add_header Cross-Origin-Resource-Policy "same-origin" always;` | WA-4. |

Important nginx behaviour: **a `location` that declares its own `add_header` discards every
inherited `add_header`.** That is why the config declares all security headers once at server
level and sets `Cache-Control` through a `map`. Do not add `add_header` inside the
`/index.html` location.

### 5.2 Reference configuration

Replace the values marked `SET`.

```nginx
# Cache-Control is resolved from the request URI so that every security header can be
# declared exactly once, at server level (see the note above about add_header).
map $uri $app_cache_control {
    default            "no-cache";
    # The HTML shell carries a per-response CSP nonce, so no copy of it may ever be reused.
    /index.html        "no-store";
    ~^/assets/         "public, max-age=31536000, immutable";
    ~^/api/            "private, no-store";
}

server {
    listen 80;
    server_name _;

    root /usr/share/nginx/html;        # SET if the build is mounted elsewhere
    index index.html;

    # WA-2: do not advertise the nginx version. If this is one of several server blocks,
    # also set it once in the http {} block of nginx.conf.
    server_tokens off;

    # ---- Security headers ----
    add_header X-Frame-Options "DENY" always;
    add_header X-Content-Type-Options "nosniff" always;
    add_header Strict-Transport-Security "max-age=31536000; includeSubDomains" always;
    add_header Referrer-Policy "strict-origin-when-cross-origin" always;
    add_header Permissions-Policy "camera=(), microphone=(), geolocation=(self)" always;
    add_header Cross-Origin-Opener-Policy "same-origin" always;

    # WA-4. Every sub-resource the app loads is same-origin, so require-corp costs nothing.
    add_header Cross-Origin-Embedder-Policy "require-corp" always;
    add_header Cross-Origin-Resource-Policy "same-origin" always;

    add_header Cache-Control $app_cache_control always;

    # WA-3. style-src is 'self' plus a per-response nonce. NO 'unsafe-inline'.
    # $request_id is 128 random bits, new for every request, and is also written into the
    # page by the sub_filter below, so header and page always agree. It is cryptographically
    # random only when nginx is built with OpenSSL (official images are).
    add_header Content-Security-Policy "default-src 'self'; script-src 'self'; style-src 'self' 'nonce-$request_id'; font-src 'self'; img-src 'self' data: blob:; connect-src 'self'; object-src 'none'; base-uri 'self'; form-action 'self'; frame-ancestors 'none'" always;

    gzip on;
    gzip_vary on;
    gzip_proxied any;
    gzip_comp_level 6;
    gzip_min_length 256;
    # text/html is gzipped by default; listing it again logs a duplicate-MIME warning.
    gzip_types text/css text/javascript application/javascript application/json image/svg+xml;

    # A missing hashed asset must fail loudly, not fall back to index.html with a 200.
    location /assets/ {
        try_files $uri =404;
    }

    # The HTML shell: write this response's nonce into the page. Every SPA route ends up
    # here (the `index` directive and the try_files fallback both redirect to /index.html).
    # No add_header here on purpose. etag/if_modified_since are off so a browser can never
    # revalidate into a 304 that pairs an old body (old nonce) with a new header.
    location = /index.html {
        sub_filter '__CSP_NONCE__' $request_id;
        sub_filter_once on;
        etag off;
        if_modified_since off;
    }

    location / {
        try_files $uri $uri/ /index.html;
    }

    location /api/ {
        proxy_pass http://backend:8000;         # SET: the backend service address

        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;

        # nginx's default 1m rejects uploads before the API sees them. Set this a little
        # above the API's own upload limit so the API's clearer error is the one users get.
        client_max_body_size 26m;            # SET to match the API's upload limit
        # Long requests (bulk imports). nginx's default of 60 s would cut them off.
        proxy_read_timeout 600s;
        proxy_send_timeout 600s;
    }

    # If the app also serves files through another prefix (e.g. /uploads/), add one more
    # `location` like /api/ above, and add that prefix to the `map`.

    # WA-2: generic error pages that name nothing about the server and carry no inline styles.
    error_page 400 403 404 405 408 411 413 414 431 /_errors/client.html;
    error_page 500 501 502 503 504 /_errors/server.html;

    location = /_errors/client.html {
        internal;
        default_type text/html;
        return 200 '<!doctype html>
<html lang="en">
<head><meta charset="utf-8"><title>Request could not be completed</title></head>
<body>
<h1>Request could not be completed</h1>
<p>The page or file you asked for is not available. <a href="/">Return to the application</a>.</p>
</body>
</html>
';
    }

    location = /_errors/server.html {
        internal;
        default_type text/html;
        return 200 '<!doctype html>
<html lang="en">
<head><meta charset="utf-8"><title>Service unavailable</title></head>
<body>
<h1>Service temporarily unavailable</h1>
<p>The service could not complete your request. Please try again shortly.</p>
</body>
</html>
';
    }
}
```

### 5.3 Adapt to the project

- `root`, the `proxy_pass` upstream(s), and one `location` per proxied prefix.
- `client_max_body_size` and the proxy timeouts, to match the API's real limits.
- **The CSP allows same-origin resources only** (`img-src` also `data:` and `blob:`). If the
  app loads fonts from a CDN, images from an object store, an external API from the browser,
  or embeds an iframe, the policy and COEP will block them. For each such resource either
  serve it same-origin (preferred) or widen **that one directive** (`font-src`, `img-src`,
  `connect-src`, `frame-src`). **Never widen `style-src` or `script-src` to fix it.**
  Cross-origin resources also need `Cross-Origin-Resource-Policy: cross-origin` on the server
  that serves them, or COEP `require-corp` will block them.

### 5.4 Requirements to confirm with DevOps

- `nginx -V` shows `--with-http_sub_module` and OpenSSL (official images have both). Without
  OpenSSL, `$request_id` is not cryptographically random, which is not acceptable for a nonce.
- No CDN or edge cache sits in front of `index.html`. A cached page pairs an old nonce with a
  new header and the UI loses its styles.
- `nginx -t` passes.
- The `Server: nginx` header (without version) remains. Removing the name entirely is only
  possible at the load balancer or edge, which is outside application scope.

---

## 6. Deployment checklist (per environment)

- [ ] Redis reachable, `REDIS_URL` set
- [ ] `TRUSTED_PROXY_HOPS` equals the real proxy count (section 3.16)
- [ ] `COOKIE_SECURE=true` on HTTPS environments
- [ ] JWT secret is a real secret, not a placeholder
- [ ] Any secret that was ever pasted into a chat, ticket or repository has been **rotated**
- [ ] Frontend with the nonce code deployed **before or with** the new nginx config
- [ ] New nginx config deployed
- [ ] After deploy, backend logs show `login_throttle_configured` and **no**
      `trusted_proxy_hops_too_low` / `trusted_proxy_chain_shorter_than_hops`
- [ ] Smoke test in a browser with the DevTools console open: log in, open a page with a
      dialog and a dropdown, open any JSON/details viewer, upload a file, download a file,
      open any PDF or file preview, and use SSO login if the app has it. Strict CSP and COEP
      can break any of these if it loads a cross-origin resource.

---

## 7. Verification

### 7.1 Automated gates (all must pass)

Record the pass counts **before** you start so you can tell what you added.

Backend (`backend/`): `pytest -q`, `ruff check src scripts tests`, `mypy src tests scripts`,
`alembic check`.
Frontend (`frontend/`): `npm run type-check`, `npm run lint`, `npm test`, `npm run build`.

### 7.2 Reproduce the WAPT attack (WA-1)

Against a running instance, 60 wrong passwords for one user should give 401 five times, then
429 with `Retry-After: 900`:

```powershell
1..60 | ForEach-Object {
  $r = curl.exe -s -o NUL -w "%{http_code}" -X POST http://localhost:8000/api/v1/auth/login `
        -H "Content-Type: application/json" -d '{"username":"admin","password":"wrong"}'
  "$_ : $r"
}
```

Also check:

- Rotating `X-Forwarded-For` while `TRUSTED_PROXY_HOPS=0` does **not** reset the count.
- The real user, logging in from a different IP, still gets in.
- `audit_logs` has the `LOGIN_FAILED` rows (they must survive the error response) and exactly
  one `LOGIN_LOCKED` row for the lockout.

### 7.3 Headers (WA-2/3/4)

```
curl -sI https://<host>/       # CSP has a nonce and no unsafe-inline; COEP and CORP present
curl -s  https://<host>/assets/  # 404 page names no nginx and shows no version
```

Open the app in a browser with DevTools open on several pages. Any "Refused to apply inline
style" or "violates the following Content Security Policy directive" message means something
still injects inline styles or loads a cross-origin resource.

### 7.4 Strongly recommended: prove the CSP in a real browser

If you can run nginx locally, load every route through it with a scripted browser and count
CSP violations (listen for the `securitypolicyviolation` event). Run three variants:

1. today's permissive policy (the baseline),
2. the strict policy **without** the nonce (a **control**: it must break the app with
   hundreds of violations, otherwise your test cannot see the problem),
3. the strict policy with the nonce (must show 0 violations and render identically to the
   baseline).

When comparing screenshots pixel for pixel, pin the rasteriser
(`--disable-gpu --disable-gpu-rasterization --disable-partial-raster --num-raster-threads=1
--disable-lcd-text`); otherwise the same page renders slightly differently from run to run and
the comparison proves nothing.

---

## 8. Known limitations (state these to the security team)

- **No CAPTCHA** (the third recommendation of EMC-WA-1). It needs a provider decision.
- **A real user on a brand-new IP** during an attack on their own account is refused until the
  15-minute lock ends. Closing that needs a second factor or a trusted-device cookie.
- **A wrong `TRUSTED_PROXY_HOPS`** weakens the per-IP logic (section 3.16).
- **Active Directory outages** count as failed logins.
- **Other routes that `raise HTTPException` after writing** lose their writes for the same
  reason as section 3.12 (the session rolls back on any exception). Only login was changed.
- **Audit rows** still record the left-most `X-Forwarded-For`, which the client controls.
- **`Server: nginx`** remains without a version; removing the name is an edge-level change.

---

## 9. Adapting to your project

| If your project differs | Do this |
|-------------------------|---------|
| Entity ids are `int` vs `UUID` | In tests that build a `User(id=...)`, use the id type your entity uses; mypy will tell you. |
| `redis` is only an optional extra | Promote it to a core dependency (3.1). |
| `tests/` has no `__init__.py` | Import the fakes by bare module name (`from login_throttle_fakes import ...`) and keep the fakes file beside the tests. |
| Different fixture names | The integration test needs a `client` bound to the ASGI app and a `db_session`. Rename to yours. |
| Your login route has extra steps or different exception classes | Keep **your** logic and add only the three throttle calls (`begin_attempt` first, `record_failure` on a rejected login, `record_success` on success), and return rather than raise. |
| Your audit service has different `log(...)` parameter names | Adapt `log_login_locked` accordingly. |
| Line endings | If the working tree uses CRLF (`core.autocrlf=true`), edit in place and do not re-save with other endings, or the diff will show every line changed. |
| The project's layering test (e.g. `test_architecture.py`) | It must stay green: `application/` must not import `infrastructure/` or SQLAlchemy. These files already comply. |

---

## 10. Summary checklist for the developer

Backend
- [ ] `redis==5.1.1` is a core dependency
- [ ] New: `login_attempt_store.py` (port), `login_throttle_service.py`, `redis_/in_memory_/resilient_login_attempt_store.py`, `client_ip.py`
- [ ] Edited: `settings.py`, `audit_log.py`, `audit_service.py`, `dependencies.py`, `auth_controller.py` (return, do not raise), `main.py` (+ `expose_headers`), `conftest.py`, `.env.example`
- [ ] All backend tests from 3.17 written; gates in 7.1 green

Frontend
- [ ] `apiClient.ts`: session endpoints are not refreshed and replayed
- [ ] `apiError.ts` + `authSlice.ts`: 429 shows the wait time
- [ ] Audit page: `LOGIN_LOCKED` option and danger tag
- [ ] `cspNonce.ts`, `index.html` meta tag, `App.tsx` provider nonce
- [ ] No string-built `style="..."` anywhere (search listed in 4.2)
- [ ] All frontend tests from 4.3 written; gates in 7.1 green

nginx / deployment
- [ ] Config merged (section 5), `nginx -t` passes, sub_filter and OpenSSL confirmed
- [ ] Section 6 checklist completed, section 7.2 and 7.3 checks done
- [ ] Limitations in section 8 communicated
