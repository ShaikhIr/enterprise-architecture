"""
Middleware that seeds the audit context from the incoming request.

Captures only what is knowable before routing — client IP and user-agent — and
marks the actor as "anonymous". The authenticated identity is attached later by
the `get_current_user` dependency via `set_audit_actor`.

Splitting it this way is not a style choice. Starlette middleware runs before
FastAPI resolves dependencies, so at this point no token has been verified and
there is no user to record. An earlier version of this middleware read
`request.state.user_id` / `.username`, which nothing ever set, so every
automatically captured audit row was attributed to "anonymous".
"""

import logging

from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.requests import Request
from starlette.responses import Response

from src.infrastructure.database.audit_context import (
    reset_audit_context,
    set_audit_context,
)

logger = logging.getLogger(__name__)

# Actor recorded for requests that never authenticate. Distinct from the default
# "system", which marks writes from scripts, seeders and background work.
ANONYMOUS_ACTOR = "anonymous"


def _client_ip(request: Request) -> str:
    """Best-effort client IP, preferring the first hop of X-Forwarded-For."""
    forwarded_for = request.headers.get("x-forwarded-for", "")
    if forwarded_for:
        return forwarded_for.split(",")[0].strip()
    if request.client:
        return request.client.host
    return ""


class AuditContextMiddleware(BaseHTTPMiddleware):
    """Seeds request-scoped audit data and restores the previous context on exit."""

    async def dispatch(
        self, request: Request, call_next: RequestResponseEndpoint
    ) -> Response:
        token = set_audit_context(
            actor_username=ANONYMOUS_ACTOR,
            ip_address=_client_ip(request),
            # audit_logs.user_agent is String(512); truncate rather than let a
            # long header fail the insert and take the whole transaction with it.
            user_agent=request.headers.get("user-agent", "")[:512],
        )
        try:
            return await call_next(request)
        finally:
            reset_audit_context(token)
