"""
Unit tests for the daily Agreement expiry scheduler task
(``src.infrastructure.background.schedulers.periodic_tasks``).

These tests exercise the Celery task's async orchestration core in isolation:
the system audit-actor context, the single-transaction commit/rollback handling,
the propagated expiry count, and idempotency on re-run. The expiry *rule* itself
is exercised through the real :class:`AgreementService` driven by an in-memory
fake repository that implements the agreement repository port, so no database is
required.

_Validates: Requirement 13.4_
"""

from __future__ import annotations

import asyncio
from datetime import date
from uuid import UUID, uuid4

import pytest

from src.application.services.masters.agreement_service import AgreementService
from src.domain.entities.masters.agreement import AgreementEntity
from src.domain.enums.masters import AgreementStatus, AgreementType
from src.domain.repositories.masters.agreement_repository import IAgreementRepository
from src.infrastructure.background.schedulers import periodic_tasks
from src.infrastructure.database.audit_context import get_audit_context


class FakeAgreementRepository(IAgreementRepository):
    """In-memory agreement repository implementing the port used by the sweep."""

    def __init__(self) -> None:
        self.store: dict[UUID, AgreementEntity] = {}

    async def get_by_id(self, agreement_id: UUID) -> AgreementEntity | None:
        return self.store.get(agreement_id)

    async def create(self, agreement: AgreementEntity) -> AgreementEntity:
        self.store[agreement.id] = agreement
        return agreement

    async def update(self, agreement: AgreementEntity) -> AgreementEntity:
        self.store[agreement.id] = agreement
        return agreement

    async def delete(self, agreement_id: UUID) -> None:
        self.store.pop(agreement_id, None)

    async def list_all(
        self, skip: int = 0, limit: int = 20, vendor_id: UUID | None = None
    ) -> list[AgreementEntity]:
        return list(self.store.values())[skip : skip + limit]

    async def count_all(self, vendor_id: UUID | None = None) -> int:
        return len(self.store)

    async def find_overlapping_active(
        self,
        vendor_id: UUID,
        product_detail_id: UUID,
        from_date: date,
        to_date: date,
        exclude_id: UUID | None = None,
    ) -> list[AgreementEntity]:
        return []

    async def list_due_for_expiry(self, today: date) -> list[AgreementEntity]:
        return [
            a
            for a in self.store.values()
            if a.status == AgreementStatus.Active
            and a.to_date is not None
            and a.to_date < today
        ]

    async def exists_expired_for_vendor_and_detail(
        self, vendor_id: UUID, product_detail_id: UUID, on_date: date
    ) -> bool:
        return False


class FakeSession:
    """Minimal async-session stand-in recording transaction calls."""

    def __init__(self) -> None:
        self.commits = 0
        self.rollbacks = 0

    async def __aenter__(self) -> FakeSession:
        return self

    async def __aexit__(self, exc_type, exc, tb) -> bool:
        return False

    async def commit(self) -> None:
        self.commits += 1

    async def rollback(self) -> None:
        self.rollbacks += 1


def _make_agreement(to_date: date, status: AgreementStatus) -> AgreementEntity:
    return AgreementEntity(
        id=uuid4(),
        vendor_id=uuid4(),
        product_detail_id=uuid4(),
        from_date=date(2024, 1, 1),
        to_date=to_date,
        agreement_type=AgreementType.Original,
        status=status,
        created_by="tester",
        modified_by="tester",
    )


def _run(repo: FakeAgreementRepository, session: FakeSession, today: date):
    """Invoke the task's async core wired to the supplied fakes."""
    observed = {}

    def build_service(_session) -> AgreementService:
        # Capture the audit actor active while the sweep runs.
        observed["actor"] = get_audit_context().actor_username
        return AgreementService(
            session=_session,
            agreement_repo=repo,
            vendor_repo=None,  # unused by the expiry sweep
            product_repo=None,  # unused by the expiry sweep
        )

    count = asyncio.run(
        periodic_tasks._expire_due_agreements_async(
            today,
            session_factory=lambda: session,
            build_service=build_service,
        )
    )
    return count, observed


def test_expires_only_past_due_active_agreements_and_commits():
    repo = FakeAgreementRepository()
    session = FakeSession()

    past_due_active = _make_agreement(date(2024, 5, 31), AgreementStatus.Active)
    future_active = _make_agreement(date(2024, 12, 31), AgreementStatus.Active)
    already_expired = _make_agreement(date(2023, 1, 1), AgreementStatus.Expired)
    for a in (past_due_active, future_active, already_expired):
        repo.store[a.id] = a

    count, observed = _run(repo, session, date(2024, 6, 1))

    assert count == 1
    assert repo.store[past_due_active.id].status == AgreementStatus.Expired
    assert repo.store[future_active.id].status == AgreementStatus.Active
    assert repo.store[already_expired.id].status == AgreementStatus.Expired
    # Ran inside a committed transaction attributed to the system actor.
    assert session.commits == 1
    assert session.rollbacks == 0
    assert observed["actor"] == "system"


def test_expired_agreement_records_system_modifier():
    repo = FakeAgreementRepository()
    session = FakeSession()
    agreement = _make_agreement(date(2024, 5, 31), AgreementStatus.Active)
    repo.store[agreement.id] = agreement

    _run(repo, session, date(2024, 6, 1))

    assert repo.store[agreement.id].modified_by == "system"


def test_sweep_is_idempotent_on_rerun():
    repo = FakeAgreementRepository()
    agreement = _make_agreement(date(2024, 5, 31), AgreementStatus.Active)
    repo.store[agreement.id] = agreement

    first_count, _ = _run(repo, FakeSession(), date(2024, 6, 1))
    second_count, _ = _run(repo, FakeSession(), date(2024, 6, 1))

    assert first_count == 1
    assert second_count == 0
    assert repo.store[agreement.id].status == AgreementStatus.Expired


def test_audit_context_is_cleared_after_run():
    repo = FakeAgreementRepository()
    _run(repo, FakeSession(), date(2024, 6, 1))

    # Context resets to the default 'system' background context after the task.
    assert get_audit_context().actor_username == "system"


def test_transaction_rolls_back_on_failure():
    session = FakeSession()

    def build_failing_service(_session):
        class _Boom:
            async def expire_due_agreements(self, today):
                raise RuntimeError("db exploded")

        return _Boom()

    with pytest.raises(RuntimeError, match="db exploded"):
        asyncio.run(
            periodic_tasks._expire_due_agreements_async(
                date(2024, 6, 1),
                session_factory=lambda: session,
                build_service=build_failing_service,
            )
        )

    assert session.commits == 0
    assert session.rollbacks == 1
