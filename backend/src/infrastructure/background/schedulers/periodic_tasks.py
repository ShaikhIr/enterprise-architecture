"""Celery Beat periodic task scheduling.

Hosts the daily Agreement expiry sweep (Requirement 13.4). When the daily job
runs, every Agreement whose Status is ``Active`` and whose To Date is earlier
than the current date is transitioned to ``Expired``.

Design notes
------------
* **Idempotent.** The task only transitions Agreements still matching the
  ``Active`` + past-due predicate, so a duplicate trigger, a retry, or a second
  run on the same day performs no double work (already-``Expired`` Agreements are
  not re-selected). See ``AgreementService.expire_due_agreements``.
* **Single transaction with a system audit actor.** The sweep runs inside one
  database transaction attributed to the ``system`` audit actor (via the
  audit-context contextvar). On failure the transaction rolls back, leaving the
  affected Agreements unchanged, and Celery re-attempts on retry / the next
  scheduled run (per the design's scheduler error-handling model).
* **Beat registration is intentionally NOT done here.** Wiring this task into the
  Celery beat schedule is handled separately (task 15.2); this module only
  defines the task so it can be invoked and later scheduled.
"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Callable
from contextlib import AbstractAsyncContextManager
from datetime import UTC, date, datetime
from typing import Any

from celery import shared_task  # type: ignore[import-untyped]
from sqlalchemy.ext.asyncio import AsyncSession

from src.application.services.masters.agreement_service import AgreementService
from src.infrastructure.database.audit_context import (
    clear_audit_context,
    set_audit_context,
)
from src.infrastructure.database.repositories.masters.agreement_repository_impl import (
    AgreementRepositoryImpl,
)
from src.infrastructure.database.repositories.masters.product_repository_impl import (
    ProductRepositoryImpl,
)
from src.infrastructure.database.repositories.masters.vendor_repository_impl import (
    VendorRepositoryImpl,
)
from src.infrastructure.database.session import async_session_factory

logger = logging.getLogger(__name__)

# Audit actor recorded for changes made by the scheduler (no human request).
_SYSTEM_ACTOR = "system"


def _build_agreement_service(session: AsyncSession) -> AgreementService:
    """Construct an :class:`AgreementService` wired to the given session."""
    return AgreementService(
        session=session,
        agreement_repo=AgreementRepositoryImpl(session),
        vendor_repo=VendorRepositoryImpl(session),
        product_repo=ProductRepositoryImpl(session),
    )


async def _expire_due_agreements_async(
    today: date,
    *,
    session_factory: Callable[
        [], AbstractAsyncContextManager[AsyncSession]
    ] = async_session_factory,
    build_service: Callable[[AsyncSession], AgreementService] = _build_agreement_service,
) -> int:
    """Run the Agreement expiry sweep in one transaction as the system actor.

    The ``session_factory`` and ``build_service`` seams are injectable purely to
    keep the orchestration unit-testable; production callers use the defaults.
    """
    set_audit_context(actor_username=_SYSTEM_ACTOR)
    try:
        async with session_factory() as session:
            try:
                expired_count: int = await build_service(
                    session
                ).expire_due_agreements(today)
                await session.commit()
                return expired_count
            except Exception:
                await session.rollback()
                raise
    finally:
        clear_audit_context()


@shared_task(  # type: ignore[misc]
    name="masters.expire_due_agreements",
    bind=True,
    max_retries=3,
    default_retry_delay=60,
)
def expire_due_agreements_task(self: Any, run_date: str | None = None) -> int:
    """Daily task: expire active Agreements past their To Date (Req 13.4).

    Parameters
    ----------
    run_date:
        Optional ISO-8601 date (``YYYY-MM-DD``) used as "today"; defaults to the
        current UTC date. Mainly useful for backfills and tests.

    Returns the number of Agreements expired. The work is idempotent and runs in
    a single transaction; on failure it rolls back and is retried.
    """
    today = (
        date.fromisoformat(run_date)
        if run_date
        else datetime.now(UTC).date()
    )
    try:
        expired_count = asyncio.run(_expire_due_agreements_async(today))
        logger.info(
            "Agreement expiry sweep complete: %s expired (run_date=%s)",
            expired_count,
            today.isoformat(),
        )
        return expired_count
    except Exception as exc:  # pragma: no cover - exercised via retry semantics
        logger.exception(
            "Agreement expiry sweep failed (run_date=%s); scheduling retry",
            today.isoformat(),
        )
        raise self.retry(exc=exc) from exc
