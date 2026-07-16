"""
ClaimAuditEntry domain entity.

Represents an immutable audit log entry for a commission claim action.
Once created, audit entries are never updated or deleted — immutability is
enforced at the repository interface level (Requirements 14.1–14.3).
"""

from dataclasses import dataclass
from datetime import datetime
from uuid import UUID


@dataclass
class ClaimAuditEntry:
    """
    Immutable record of a single action taken on a commission claim.

    Every workflow transition, field edit, and lifecycle event (Create,
    Line Added, Submitted, Approved, etc.) produces one entry.

    Fields
    ------
    id : UUID
        Unique identifier for this audit entry.
    claim_header_id : UUID
        The claim this entry belongs to.
    action : str
        Human-readable action label — one of: Create, Line Added, Line Edited,
        Submitted, Approved, Referred Back, Rejected, Field Edited, Closed,
        SAP Booking Reference Recorded.
    actor_username : str
        Denormalised username of the user who performed the action.
    actor_user_id : UUID
        ID of the user who performed the action.
    timestamp_utc : datetime
        UTC timestamp when the action occurred.
    from_status : str | None
        Claim status before the action (None for non-transition events such as
        "Line Added").
    to_status : str | None
        Claim status after the action (None for non-transition events).
    workflow_step_name : str | None
        Name of the workflow step active at the time of the action, if
        applicable (e.g. "L1 Verification").
    remarks : str | None
        Approver/actor remarks supplied with the action, if any.
    field_changes : dict | None
        For field-edit events, a mapping of changed fields to their old and
        new values: ``{"field_name": {"old": <old_value>, "new": <new_value>}}``.
    created_by : str
        Set to the actor's username by the service layer at write time.
    created_date : datetime
        UTC timestamp of row insertion (populated by service / infrastructure).
    modified_by : str
        Always the same as ``created_by`` — audit rows are never updated.
    modified_date : datetime
        Always the same as ``created_date`` — audit rows are never updated.

    Requirements: 14.1, 14.2, 14.3
    """

    id: UUID
    claim_header_id: UUID
    action: str
    actor_username: str
    actor_user_id: UUID
    timestamp_utc: datetime

    # Status-transition fields (None for non-transition events)
    from_status: str | None
    to_status: str | None

    # Workflow context (None when action is not workflow-driven)
    workflow_step_name: str | None

    # Free-text remarks (required for approve / refer-back / reject actions)
    remarks: str | None

    # Field-level diff for "Field Edited" events
    # Format: {"field_name": {"old": <old_value>, "new": <new_value>}}
    field_changes: dict | None

    # Audit / tracking fields (mirrors the AuditMixin pattern on ORM models)
    created_by: str
    created_date: datetime
    modified_by: str
    modified_date: datetime
