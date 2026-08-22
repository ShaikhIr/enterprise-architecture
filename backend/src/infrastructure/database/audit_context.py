"""
Request-scoped audit context using Python contextvars.

Stores the current actor (user) info so that the audit listener
can attribute changes to the correct user without passing context
through every function call.

Populated in two stages, because the actor is not known when the request first
arrives:

1. `AuditContextMiddleware` seeds the request-scoped data (IP, user-agent) that
   is available before routing.
2. The authentication dependency (`get_current_user`) calls `set_audit_actor` to
   attach the resolved identity, preserving what stage 1 captured.

Stage 2 has to be a dependency rather than middleware: Starlette middleware runs
before FastAPI resolves dependencies, so no middleware can know who the caller
is. The dependency runs in the same task context as the request handler and its
database session, so the listener sees the identity at flush time.

    # Middleware, at request start:
    token = set_audit_context(ip_address=..., user_agent=..., actor_username="anonymous")
    try:
        ...
    finally:
        reset_audit_context(token)

    # Auth dependency, once the user is known:
    set_audit_actor(actor_id=user.id, actor_username=user.username)
"""

from contextvars import ContextVar, Token
from dataclasses import dataclass, field, replace
from uuid import UUID


@dataclass(frozen=True)
class AuditContext:
    """Immutable snapshot of who is performing the current operation."""

    actor_id: UUID | None = field(default=None)
    actor_username: str = field(default="system")
    ip_address: str = field(default="")
    user_agent: str = field(default="")
    tenant_id: UUID | None = field(default=None)


# Default context for background jobs / system operations
_DEFAULT_CONTEXT = AuditContext()

# Context variable — one value per async task / thread
_audit_context_var: ContextVar[AuditContext] = ContextVar(
    "audit_context", default=_DEFAULT_CONTEXT
)


def set_audit_context(
    *,
    actor_id: UUID | None = None,
    actor_username: str = "system",
    ip_address: str = "",
    user_agent: str = "",
    tenant_id: UUID | None = None,
) -> Token[AuditContext]:
    """
    Replace the audit context for the current request/task.

    Returns the contextvar token so the caller can restore the previous value
    with `reset_audit_context`, which is what keeps request contexts from
    leaking into each other on a reused worker task.
    """
    ctx = AuditContext(
        actor_id=actor_id,
        actor_username=actor_username,
        ip_address=ip_address,
        user_agent=user_agent,
        tenant_id=tenant_id,
    )
    return _audit_context_var.set(ctx)


def set_audit_actor(
    *,
    actor_id: UUID | None,
    actor_username: str,
    tenant_id: UUID | None = None,
) -> None:
    """
    Attach the resolved actor to the context already seeded by the middleware.

    Only the identity fields are overwritten; `ip_address` and `user_agent` are
    carried over. `tenant_id` is left untouched when not supplied, so a caller
    that does not know the tenant cannot blank out one that was already set.
    """
    current = _audit_context_var.get()
    _audit_context_var.set(
        replace(
            current,
            actor_id=actor_id,
            actor_username=actor_username,
            tenant_id=current.tenant_id if tenant_id is None else tenant_id,
        )
    )


def get_audit_context() -> AuditContext:
    """Get the current audit context. Returns default 'system' context if not set."""
    return _audit_context_var.get()


def reset_audit_context(token: Token[AuditContext]) -> None:
    """Restore the context that was in place before `set_audit_context`."""
    _audit_context_var.reset(token)


def clear_audit_context() -> None:
    """Reset audit context to default (e.g., at end of request)."""
    _audit_context_var.set(_DEFAULT_CONTEXT)
