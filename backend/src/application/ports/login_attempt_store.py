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
