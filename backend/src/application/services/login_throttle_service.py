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
