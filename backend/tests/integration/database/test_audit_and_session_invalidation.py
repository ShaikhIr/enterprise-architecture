"""
Integration tests for cross-cutting master infrastructure (task 15.3).

These tests exercise the *real* persistence stack against PostgreSQL:

* **Audit (Req 20.1):** the ``before_flush`` audit listener — registered
  globally on the SQLAlchemy ``Session`` class — automatically writes an
  ``audit_logs`` row capturing actor, action, and old/new values for every
  master CRUD operation. Verified here for an INSERT and an UPDATE of an Entity
  master.
* **Session invalidation (Req 7.3):** deactivating a Vendor invalidates the
  vendor portal user's sessions within the 5-second time budget and blocks new
  logins for that portal user.

Like the sibling smoke/migration tests, each test runs end-to-end inside a
single event loop (``asyncio.run``) against a freshly-created, throwaway
PostgreSQL database whose schema is built from the ORM metadata. This keeps the
tests hermetic and side-steps cross-event-loop connection-pool reuse: the global
application engine binds pooled connections to whichever loop first touched
them, which breaks under pytest-asyncio's per-test loops. Using a fresh
per-test engine that is disposed in the same loop avoids that entirely. The
``fresh_database`` fixture skips the test when no PostgreSQL server is reachable.
"""

from __future__ import annotations

import asyncio
import json
import time
from uuid import UUID, uuid4

from sqlalchemy import select
from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

# Importing the models package registers every ORM model on ``Base.metadata``
# so ``create_all`` builds the full master schema.
import src.infrastructure.database.models  # noqa: F401

# Importing the session module has the side effect of registering the global
# ``before_flush`` audit listener on the SQLAlchemy ``Session`` class (exactly
# as application startup does). Without this import the listener is never
# attached and no audit rows would be written. Module import is cached, so the
# listener is registered exactly once.
import src.infrastructure.database.session  # noqa: F401
from src.application.services.masters.vendor_service import (
    VendorCreateInput,
    VendorService,
)
from src.config.settings import settings
from src.domain.entities.masters.entity import EntityEntity
from src.domain.entities.user import User
from src.domain.enums.masters import VendorStatus
from src.infrastructure.database.audit_context import (
    clear_audit_context,
    set_audit_context,
)
from src.infrastructure.database.models.audit_log_model import AuditLogModel
from src.infrastructure.database.models.base_model import Base
from src.infrastructure.database.repositories.masters.entity_repository_impl import (
    EntityRepositoryImpl,
)
from src.infrastructure.database.repositories.masters.vendor_repository_impl import (
    VendorRepositoryImpl,
)
from src.infrastructure.database.repositories.user_repository_impl import (
    UserRepositoryImpl,
)
from src.infrastructure.security.auth_manager import (
    AuthManager,
    UserInactiveError,
)
from src.infrastructure.security.jwt_provider import JWTProvider

# Session-invalidation time budget for vendor deactivation (Req 7.3).
SESSION_INVALIDATION_BUDGET_SECONDS = 5.0


class RecordingInvalidator:
    """Session invalidator that records which user ids it was asked to clear."""

    def __init__(self) -> None:
        self.invalidated: list[UUID] = []

    async def invalidate_user_sessions(self, user_id: UUID) -> None:
        self.invalidated.append(user_id)


async def _create_schema(engine) -> None:
    """Build the full master schema from the ORM metadata."""
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)


# ─────────────────────────────────────────────────────────────────────────────
# Audit logging (Req 20.1)
# ─────────────────────────────────────────────────────────────────────────────


async def _run_audit_insert_then_update(url: str) -> None:
    """INSERT writes new_value; UPDATE writes both old_value and new_value.

    Validates Requirement 20.1: a master create/update records an audit entry
    capturing the actor, the operation type, and the old/new values of the
    changed fields. The ``before_flush`` listener writes the rows automatically.
    """
    engine = create_async_engine(url, poolclass=None)
    try:
        await _create_schema(engine)
        factory = async_sessionmaker(
            engine, class_=AsyncSession, expire_on_commit=False
        )

        entity_id = uuid4()
        actor_id = uuid4()
        unique_name = f"Audit Test Entity {entity_id}"

        # --- CREATE (INSERT) under a known actor context ---
        set_audit_context(actor_id=actor_id, actor_username="audit-actor")
        try:
            async with factory() as session:
                repo = EntityRepositoryImpl(session)
                await repo.create(
                    EntityEntity(
                        id=entity_id,
                        entity_name=unique_name,
                        company_code=f"AC-{entity_id.hex[:8]}",
                        is_active=True,
                        created_by="audit-actor",
                        modified_by="audit-actor",
                    )
                )
                await session.commit()
        finally:
            clear_audit_context()

        # The INSERT must have produced exactly one audit row.
        async with factory() as session:
            rows = (
                (
                    await session.execute(
                        select(AuditLogModel)
                        .where(AuditLogModel.resource_id == str(entity_id))
                        .where(AuditLogModel.action == "INSERT")
                    )
                )
                .scalars()
                .all()
            )

        assert len(rows) == 1, "exactly one INSERT audit row expected"
        insert_row = rows[0]
        assert insert_row.resource_type == "entities"
        assert insert_row.actor_username == "audit-actor"
        assert insert_row.actor_id == actor_id
        assert insert_row.old_value is None  # nothing existed before
        assert insert_row.new_value is not None
        new_snapshot = json.loads(insert_row.new_value)
        assert new_snapshot["entity_name"] == unique_name
        assert new_snapshot["is_active"] == "True"

        # --- UPDATE: rename + deactivate under a different actor ---
        updated_name = f"{unique_name} (renamed)"
        set_audit_context(actor_id=uuid4(), actor_username="updater")
        try:
            async with factory() as session:
                repo = EntityRepositoryImpl(session)
                entity = await repo.get_by_id(entity_id)
                assert entity is not None
                entity.entity_name = updated_name
                entity.deactivate("updater")
                await repo.update(entity)
                await session.commit()
        finally:
            clear_audit_context()

        async with factory() as session:
            rows = (
                (
                    await session.execute(
                        select(AuditLogModel)
                        .where(AuditLogModel.resource_id == str(entity_id))
                        .where(AuditLogModel.action == "UPDATE")
                    )
                )
                .scalars()
                .all()
            )

        assert len(rows) == 1, "exactly one UPDATE audit row expected"
        update_row = rows[0]
        assert update_row.actor_username == "updater"
        assert update_row.old_value is not None
        assert update_row.new_value is not None

        old_snapshot = json.loads(update_row.old_value)
        new_snapshot = json.loads(update_row.new_value)
        # Old/new values reflect the change that occurred.
        assert old_snapshot["entity_name"] == unique_name
        assert new_snapshot["entity_name"] == updated_name
        assert old_snapshot["is_active"] == "True"
        assert new_snapshot["is_active"] == "False"

        # Changed columns are tracked in extra_data.
        assert update_row.extra_data is not None
        changed = json.loads(update_row.extra_data)["changed_columns"]
        assert "entity_name" in changed
        assert "is_active" in changed
    finally:
        await engine.dispose()


class TestAuditLoggingOnMasterCrud:
    """The before_flush listener records audit rows for master CRUD."""

    def test_insert_then_update_writes_audit_rows_with_old_new_values(
        self, fresh_database
    ):
        """A master INSERT and UPDATE each write an audit row with old/new values."""
        url = fresh_database()
        asyncio.run(_run_audit_insert_then_update(url))


# ─────────────────────────────────────────────────────────────────────────────
# Vendor deactivation → session invalidation + login blocked (Req 7.3)
# ─────────────────────────────────────────────────────────────────────────────


async def _run_deactivation_invalidates_and_blocks(url: str) -> None:
    """A deactivated vendor's portal user cannot log in, and invalidation happens
    within the 5-second budget.

    Validates Requirement 7.3.
    """
    engine = create_async_engine(url, poolclass=None)
    try:
        await _create_schema(engine)
        factory = async_sessionmaker(
            engine, class_=AsyncSession, expire_on_commit=False
        )

        suffix = uuid4().hex[:10]
        vendor_code = f"VINT{suffix}"
        actor = User(
            id=uuid4(),
            username="vendor-admin",
            password_hash="x",
            is_active=True,
        )
        invalidator = RecordingInvalidator()

        # --- Create the vendor (provisions the portal-login user) ---
        set_audit_context(actor_id=actor.id, actor_username=actor.username)
        try:
            async with factory() as session:
                service = VendorService(
                    session=session,
                    vendor_repo=VendorRepositoryImpl(session),
                    user_repo=UserRepositoryImpl(session),
                    session_invalidator=invalidator,
                )
                created = await service.create_vendor(
                    VendorCreateInput(
                        vendor_code=vendor_code,
                        vendor_name="Integration Vendor",
                        vendor_email=f"{suffix}@vendor.example",
                    ),
                    actor,
                )
                await session.commit()
                vendor_id = created.id
                portal_user_id = created.portal_user_id
        finally:
            clear_audit_context()

        assert portal_user_id is not None

        # --- Portal login works *before* deactivation ---
        async with factory() as session:
            auth = AuthManager(UserRepositoryImpl(session), JWTProvider())
            tokens = await auth.login(
                vendor_code, settings.VENDOR_PORTAL_DEFAULT_PASSWORD
            )
            assert tokens.access_token

        # --- Deactivate, measuring the elapsed time (Req 7.3 budget) ---
        set_audit_context(actor_id=actor.id, actor_username=actor.username)
        try:
            async with factory() as session:
                service = VendorService(
                    session=session,
                    vendor_repo=VendorRepositoryImpl(session),
                    user_repo=UserRepositoryImpl(session),
                    session_invalidator=invalidator,
                )
                start = time.perf_counter()
                result = await service.deactivate_vendor(vendor_id, actor)
                await session.commit()
                elapsed = time.perf_counter() - start
        finally:
            clear_audit_context()

        assert result.status is VendorStatus.Inactive
        assert elapsed < SESSION_INVALIDATION_BUDGET_SECONDS, (
            f"session invalidation took {elapsed:.3f}s, "
            f"exceeding the {SESSION_INVALIDATION_BUDGET_SECONDS}s budget"
        )
        # Invalidation targeted exactly the portal user.
        assert invalidator.invalidated == [portal_user_id]

        # --- Portal login is now blocked (is_active=false) ---
        async with factory() as session:
            auth = AuthManager(UserRepositoryImpl(session), JWTProvider())
            try:
                await auth.login(
                    vendor_code, settings.VENDOR_PORTAL_DEFAULT_PASSWORD
                )
                raise AssertionError(
                    "portal login should be blocked after deactivation"
                )
            except UserInactiveError:
                pass  # expected: deactivated portal user cannot authenticate
    finally:
        await engine.dispose()


class TestVendorSessionInvalidation:
    """Deactivation invalidates sessions in budget and blocks portal login."""

    def test_deactivation_invalidates_and_blocks_login_within_budget(
        self, fresh_database
    ):
        """A deactivated vendor cannot log in; invalidation stays within budget."""
        url = fresh_database()
        asyncio.run(_run_deactivation_invalidates_and_blocks(url))
