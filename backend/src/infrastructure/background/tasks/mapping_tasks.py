"""Vendor-Customer Mapping expiry Celery task (Requirement 15).

Defines the idempotent end-of-day job that transitions every active Mapping
past its Validity To date to ``Expired`` (Req 15.1) while leaving every active
Mapping whose Validity To is on or after the current date unchanged (Req 15.2).

The job runs inside a single database transaction attributed to a ``system``
audit actor. On any failure the transaction is rolled back — so the affected
Mappings are left unchanged — and the error is re-raised so Celery retries on a
later run (Req 15.3). The job is idempotent: a re-run only transitions records
still matching the ``Active`` + past-due predicate, so a partially completed
prior run causes no double effect.

Registering this task in the Celery beat schedule is owned by task 15.2; this
module only defines the task.
"""

from __future__ import annotations

import logging
from datetime import date
from typing import Callable, Optional

from src.application.services.masters.mapping_service import MappingService
from src.infrastructure.background.celery_app import celery_app
from src.infrastructure.database.audit_context import (
    clear_audit_context,
    set_audit_context,
)

logger = logging.getLogger(__name__)

# Type aliases for the injectable seams used by tests.
SessionFactory = Callable[[], "object"]
ServiceBuilder = Callable[["object"], MappingService]


def _build_service(session: object) -> MappingService:
    """Construct a :class:`MappingService` bound to ``session``.

    Repository implementations are imported lazily so that importing this
    module (for task discovery) does not eagerly build the database engine.
    """
    from src.infrastructure.database.repositories.masters.customer_repository_impl import (
        CustomerRepositoryImpl,
    )
    from src.infrastructure.database.repositories.masters.mapping_repository_impl import (
        MappingRepositoryImpl,
    )
    from src.infrastructure.database.repositories.masters.vendor_repository_impl import (
        VendorRepositoryImpl,
    )

    return MappingService(
        session=session,  # type: ignore[arg-type]
        mapping_repo=MappingRepositoryImpl(session),  # type: ignore[arg-type]
        vendor_repo=VendorRepositoryImpl(session),  # type: ignore[arg-type]
        customer_repo=CustomerRepositoryImpl(session),  # type: ignore[arg-type]
    )


async def expire_due_mappings(
    today: date,
    *,
    session_factory: Optional[SessionFactory] = None,
    service_builder: Optional[ServiceBuilder] = None,
) -> int:
    """Run the Mapping expiry inside one transaction as the ``system`` actor.

    Opens a session, builds a :class:`MappingService`, and calls
    :meth:`MappingService.expire_due_mappings`. The work is committed atomically
    on success; on any error the transaction is rolled back (Req 15.3) and the
    exception is propagated so the caller (the Celery task) can retry. Returns
    the number of Mappings expired.

    ``session_factory`` and ``service_builder`` are injectable seams; they
    default to the real async session factory and repository-backed service so
    production callers need only pass ``today``.
    """
    if session_factory is None:
        # Imported lazily to avoid constructing the engine at import time.
        from src.infrastructure.database.session import (
            async_session_factory as session_factory,
        )
    if service_builder is None:
        service_builder = _build_service

    set_audit_context(actor_username="system")
    try:
        async with session_factory() as session:
            try:
                service = service_builder(session)
                expired = await service.expire_due_mappings(today)
                await session.commit()
                return expired
            except Exception:
                await session.rollback()
                raise
    finally:
        clear_audit_context()


@celery_app.task(
    bind=True,
    name="masters.expire_due_mappings",
    max_retries=3,
    default_retry_delay=300,
    acks_late=True,
)
def expire_due_mappings_task(self, today_iso: Optional[str] = None) -> int:
    """Celery entry point for the end-of-day Mapping expiry job.

    ``today_iso`` is an optional ISO-8601 date string (kept JSON-serialisable
    for the broker); when omitted the current date is used. Delegates to
    :func:`expire_due_mappings` and, on failure, schedules a Celery retry so the
    job re-attempts on a later run with the affected Mappings left unchanged
    (Req 15.3).
    """
    import asyncio

    today = date.fromisoformat(today_iso) if today_iso else date.today()
    try:
        expired = asyncio.run(expire_due_mappings(today))
        logger.info(
            "End-of-day Mapping expiry complete: %d expired (today=%s)",
            expired,
            today.isoformat(),
        )
        return expired
    except Exception as exc:  # noqa: BLE001 - re-raised via Celery retry
        logger.exception(
            "End-of-day Mapping expiry failed; scheduling retry (today=%s)",
            today.isoformat(),
        )
        raise self.retry(exc=exc)
