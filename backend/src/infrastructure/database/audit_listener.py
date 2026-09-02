"""
Automatic audit logging via SQLAlchemy session events.

Hooks into `before_flush` to capture before/after snapshots for every INSERT,
UPDATE and DELETE that passes through the ORM unit of work.

Coverage is opt-out, not opt-in: every mapped class is audited unless its table
name appears in `EXCLUDED_TABLES`. A model therefore cannot silently drop out of
the audit trail by inheriting a different base class.

Known limits, by design:
  - Core-level DML (`session.execute(delete(...))`, `session.execute(update(...))`,
    raw `text(...)`) emits no unit-of-work events and is NOT captured. Repositories
    must mutate and delete through the ORM to stay auditable.
  - Audit rows are written inside the caller's transaction, so a rollback discards
    the change and its audit row together. That keeps the trail consistent with
    what actually persisted.
  - Snapshots are taken before flush, so database-generated values (server
    defaults, sequences) are not yet visible. Primary keys are assigned by the
    domain layer, so `resource_id` is populated.

Usage:
    from src.infrastructure.database.audit_listener import register_audit_listener
    register_audit_listener()

To attribute changes to a user, set the audit context (see `audit_context.py`).
The API does this in `get_current_user`; unattributed writes are recorded as
"system" (background/scripts) or "anonymous" (unauthenticated request).
"""

import json
import logging
from collections.abc import Iterator
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import event, inspect
from sqlalchemy.orm import Session

from src.infrastructure.database.audit_context import get_audit_context
from src.infrastructure.database.models.audit_log_model import AuditLogModel

logger = logging.getLogger(__name__)

# Tables never audited. `audit_logs` must stay here to prevent recursion;
# anything else added is a deliberate decision to stop recording a table.
EXCLUDED_TABLES: frozenset[str] = frozenset({"audit_logs"})

# Column values replaced with a placeholder. The fact that the field changed
# stays auditable; the secret itself must never land in the trail.
REDACTED_FIELDS: frozenset[str] = frozenset(
    {
        "password_hash",
        "password",
        "refresh_token",
        "access_token",
        "token",
        "secret",
        "client_secret",
        "api_key",
    }
)

# Row bookkeeping already carried by audit_logs.created_at / actor_username.
# Excluded from snapshots and from change detection, so a bare touch of
# modified_date does not produce an audit row with no real delta.
NOISE_FIELDS: frozenset[str] = frozenset({"created_date", "modified_date"})

_REDACTED_PLACEHOLDER = "***"

# Guards against double registration if the module is imported more than once.
_listener_registered = False


def _serialize_value(value: Any) -> str | None:
    """Convert a column value to a JSON-safe representation."""
    if value is None:
        return None
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, bytes):
        return "<binary>"
    return str(value)


def _column_keys(instance: Any) -> list[str]:
    """
    Auditable column attribute names for an instance.

    Only mapped columns are walked, never relationships. Reading `attr.value` on
    an unloaded relationship during a flush triggers a lazy load, which costs a
    query per attribute and emits IO at a point where the session is mid-flush.
    """
    mapper = inspect(type(instance))
    return [prop.key for prop in mapper.column_attrs if prop.key not in NOISE_FIELDS]


def _snapshot(instance: Any) -> dict[str, Any]:
    """Serialize an instance's column values, redacting secrets."""
    result: dict[str, Any] = {}
    for key in _column_keys(instance):
        if key in REDACTED_FIELDS:
            result[key] = _REDACTED_PLACEHOLDER
            continue
        result[key] = _serialize_value(getattr(instance, key, None))
    return result


def _changed_columns(instance: Any) -> list[str]:
    """Return the column names whose value differs from the loaded state."""
    state = inspect(instance)
    return [
        key for key in _column_keys(instance) if state.attrs[key].history.has_changes()
    ]


def _old_values(instance: Any) -> dict[str, Any]:
    """
    Previous committed state of an instance.

    Changed columns use their history value; unchanged columns use the current
    value, so `old_value` is a full before-snapshot rather than a sparse delta.
    """
    state = inspect(instance)
    old: dict[str, Any] = {}
    for key in _column_keys(instance):
        if key in REDACTED_FIELDS:
            old[key] = _REDACTED_PLACEHOLDER
            continue
        history = state.attrs[key].history
        if history.deleted:
            old[key] = _serialize_value(history.deleted[0])
        else:
            old[key] = _serialize_value(getattr(instance, key, None))
    return old


def _resource_id(instance: Any) -> str:
    """Extract the primary key value from a model instance."""
    pk_columns = inspect(type(instance)).primary_key
    if not pk_columns:
        return ""
    value = getattr(instance, pk_columns[0].key, None)
    return str(value) if value is not None else ""


def _table_name(instance: Any) -> str | None:
    """Table name of a mapped instance, or None if it is not mapped."""
    table = getattr(instance, "__tablename__", None)
    return table if isinstance(table, str) else None


def _create_audit_entry(
    action: str,
    table_name: str,
    resource_id: str,
    old_value: dict[str, Any] | None,
    new_value: dict[str, Any] | None,
    changed_columns: list[str] | None = None,
) -> AuditLogModel:
    """Build an AuditLogModel row for a detected change."""
    ctx = get_audit_context()

    extra_data = None
    if changed_columns:
        extra_data = json.dumps({"changed_columns": changed_columns})

    # actor_id and tenant_id are bigint FK columns; pass the int through. The
    # row id is DB-assigned (autoincrement), so it is not set here.
    return AuditLogModel(
        actor_id=ctx.actor_id,
        actor_username=ctx.actor_username,
        action=action,
        resource_type=table_name,
        resource_id=resource_id,
        tenant_id=ctx.tenant_id,
        old_value=json.dumps(old_value) if old_value else None,
        new_value=json.dumps(new_value) if new_value else None,
        ip_address=ctx.ip_address,
        user_agent=ctx.user_agent,
        extra_data=extra_data,
        created_at=datetime.now(UTC),
    )


def _auditable(session: Session) -> Iterator[tuple[Any, str, str]]:
    """
    Yield (instance, table_name, action) for every auditable change in a flush.

    The collections are copied because the caller adds audit rows to the same
    session while iterating.
    """
    for collection, action in (
        (session.new, "INSERT"),
        (session.dirty, "UPDATE"),
        (session.deleted, "DELETE"),
    ):
        for instance in list(collection):
            table_name = _table_name(instance)
            if table_name is None or table_name in EXCLUDED_TABLES:
                continue
            yield instance, table_name, action


def _build_entry(
    session: Session, instance: Any, table_name: str, action: str
) -> AuditLogModel | None:
    """Build the audit row for one changed instance, or None if there is nothing to record."""
    if action == "INSERT":
        return _create_audit_entry(
            action=action,
            table_name=table_name,
            resource_id=_resource_id(instance),
            old_value=None,
            new_value=_snapshot(instance),
        )

    if action == "DELETE":
        return _create_audit_entry(
            action=action,
            table_name=table_name,
            resource_id=_resource_id(instance),
            old_value=_snapshot(instance),
            new_value=None,
        )

    # UPDATE: `session.dirty` is pessimistic — it lists anything that received an
    # attribute set, whether or not the value actually differs.
    if not session.is_modified(instance, include_collections=False):
        return None
    changed_columns = _changed_columns(instance)
    if not changed_columns:
        return None

    return _create_audit_entry(
        action=action,
        table_name=table_name,
        resource_id=_resource_id(instance),
        old_value=_old_values(instance),
        new_value=_snapshot(instance),
        changed_columns=changed_columns,
    )


def _before_flush(session: Session, flush_context: Any, instances: Any) -> None:
    """
    SQLAlchemy event handler: capture audit snapshots before flush.

    Failures are contained per instance and never propagated. A broken snapshot
    must not abort the business transaction that triggered it; the loss is
    logged at ERROR so it is visible in monitoring.
    """
    entries: list[AuditLogModel] = []

    for instance, table_name, action in _auditable(session):
        try:
            entry = _build_entry(session, instance, table_name, action)
        except Exception:
            logger.error(
                "Audit capture failed for %s %s; change is NOT audited",
                action,
                type(instance).__name__,
                exc_info=True,
            )
            continue
        if entry is not None:
            entries.append(entry)

    # Objects added during before_flush are picked up by the same flush, so the
    # audit rows land in the caller's transaction.
    for entry in entries:
        session.add(entry)


def register_audit_listener() -> None:
    """
    Register the before_flush audit listener on the sync Session class.

    Async sessions delegate flush to an internal sync Session, so listening on
    `Session` itself covers both sync and async usage, including the per-test
    session factories built in the test fixtures.

    Idempotent: repeated calls are ignored, so a re-imported module cannot cause
    duplicate audit rows.
    """
    global _listener_registered
    if _listener_registered:
        return

    event.listen(Session, "before_flush", _before_flush)
    _listener_registered = True
    logger.info("Automatic audit logging registered on Session class")
