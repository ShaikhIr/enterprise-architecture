"""Unit tests for the end-of-day Mapping expiry Celery task (Requirement 15).

These tests exercise the task's orchestration contract — run inside a single
transaction as the ``system`` actor, commit on success, roll back and propagate
on failure (Req 15.3), and stay idempotent (Req 15.1/15.2) — using a real
:class:`MappingService` backed by the in-memory fake repositories together with
a lightweight fake async session. No database or broker is required.
"""

from __future__ import annotations

import asyncio
from datetime import date
from uuid import UUID, uuid4

import pytest

from src.application.services.masters.mapping_service import MappingService
from src.domain.entities.masters.mapping import MappingEntity
from src.domain.enums.masters import MappingStatus
from src.infrastructure.background import celery_app as celery_app_module
from src.infrastructure.background.tasks import mapping_tasks
from src.infrastructure.database.audit_context import get_audit_context

# ─── Fakes ───


class FakeMappingRepository:
    """Minimal in-memory IMappingRepository covering the expiry path."""

    def __init__(self) -> None:
        self.store: dict[UUID, MappingEntity] = {}
        self.update_calls = 0

    async def update(self, mapping: MappingEntity) -> MappingEntity:
        self.store[mapping.id] = mapping
        self.update_calls += 1
        return mapping

    async def list_active_due_for_expiry(
        self, today: date
    ) -> list[MappingEntity]:
        return [
            m
            for m in self.store.values()
            if m.status is MappingStatus.Active and m.validity_to < today
        ]


class FakeSession:
    """Async-context-manager stand-in for an AsyncSession.

    Records commit/rollback so tests can assert the transactional contract.
    """

    def __init__(self) -> None:
        self.committed = False
        self.rolled_back = False
        self.closed = False

    async def __aenter__(self) -> "FakeSession":
        return self

    async def __aexit__(self, exc_type, exc, tb) -> bool:
        self.closed = True
        return False

    async def commit(self) -> None:
        self.committed = True

    async def rollback(self) -> None:
        self.rolled_back = True


def _mapping(validity_to: date, status: MappingStatus = MappingStatus.Active) -> MappingEntity:
    return MappingEntity(
        id=uuid4(),
        vendor_id=uuid4(),
        customer_id=uuid4(),
        validity_from=date(2024, 1, 1),
        validity_to=validity_to,
        status=status,
        created_by="tester",
        modified_by="tester",
    )


def _run(repo: FakeMappingRepository, session: FakeSession, today: date) -> int:
    """Invoke the task orchestration with injected fakes."""
    service = MappingService(
        session=session,  # type: ignore[arg-type]
        mapping_repo=repo,  # type: ignore[arg-type]
        vendor_repo=object(),  # type: ignore[arg-type]  # unused on expiry path
        customer_repo=object(),  # type: ignore[arg-type]
    )
    return asyncio.run(
        mapping_tasks.expire_due_mappings(
            today,
            session_factory=lambda: session,
            service_builder=lambda _s: service,
        )
    )


# ─── Tests ───


def test_expires_only_past_due_active_and_commits() -> None:
    """Req 15.1/15.2: only past-due active Mappings expire; tx is committed."""
    repo = FakeMappingRepository()
    past = _mapping(date(2025, 1, 1))
    on_date = _mapping(date(2025, 6, 1))
    future = _mapping(date(2025, 12, 31))
    already = _mapping(date(2024, 1, 1), status=MappingStatus.Expired)
    for m in (past, on_date, future, already):
        repo.store[m.id] = m

    session = FakeSession()
    expired = _run(repo, session, today=date(2025, 6, 1))

    assert expired == 1
    assert repo.store[past.id].status is MappingStatus.Expired
    # On-or-after-date active and already-expired Mappings are left unchanged.
    assert repo.store[on_date.id].status is MappingStatus.Active
    assert repo.store[future.id].status is MappingStatus.Active
    assert repo.store[already.id].status is MappingStatus.Expired
    assert session.committed is True
    assert session.rolled_back is False


def test_idempotent_second_run_expires_nothing() -> None:
    """Re-running after a completed run transitions no further records."""
    repo = FakeMappingRepository()
    past = _mapping(date(2025, 1, 1))
    repo.store[past.id] = past

    first = _run(repo, FakeSession(), today=date(2025, 6, 1))
    second = _run(repo, FakeSession(), today=date(2025, 6, 1))

    assert first == 1
    assert second == 0


def test_rolls_back_and_propagates_on_failure() -> None:
    """Req 15.3: on failure the tx rolls back and the error propagates (for retry)."""

    class BoomService:
        async def expire_due_mappings(self, today: date) -> int:
            raise RuntimeError("boom")

    session = FakeSession()

    with pytest.raises(RuntimeError, match="boom"):
        asyncio.run(
            mapping_tasks.expire_due_mappings(
                date(2025, 6, 1),
                session_factory=lambda: session,
                service_builder=lambda _s: BoomService(),  # type: ignore[arg-type]
            )
        )

    assert session.rolled_back is True
    assert session.committed is False


def test_runs_as_system_actor_then_clears_context() -> None:
    """The job attributes changes to the 'system' actor and clears context after."""
    captured: dict[str, str] = {}

    class CapturingService:
        async def expire_due_mappings(self, today: date) -> int:
            captured["actor"] = get_audit_context().actor_username
            return 0

    asyncio.run(
        mapping_tasks.expire_due_mappings(
            date(2025, 6, 1),
            session_factory=lambda: FakeSession(),
            service_builder=lambda _s: CapturingService(),  # type: ignore[arg-type]
        )
    )

    assert captured["actor"] == "system"
    # Context is reset to its default after the job completes.
    assert get_audit_context().actor_username == "system"


def test_task_registered_with_retry_contract() -> None:
    """The Celery task is registered and configured to retry (idempotent re-run)."""
    task = celery_app_module.celery_app.tasks["masters.expire_due_mappings"]
    assert task is not None
    assert mapping_tasks.expire_due_mappings_task.max_retries == 3
