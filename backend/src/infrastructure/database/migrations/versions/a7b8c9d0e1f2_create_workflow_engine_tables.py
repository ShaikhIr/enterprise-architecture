"""create_workflow_engine_tables

Creates the workflow engine schema in two halves:

Configuration and runtime
    workflow_definitions -> workflow_statuses -> workflow_transitions
    workflow_instances -> workflow_history

Approval routing
    approval_matrices -> approval_rules, approval_assignments
    approval_tasks

Delete behaviour is deliberate. Configuration children CASCADE from their
definition, because removing a workflow should take its own states and edges with
it. Runtime rows hold RESTRICT references onto configuration, so a definition or
state that something is sitting in cannot be deleted out from under it — the
service layer turns that into a 409 with a reason before the constraint fires.

Revision ID: a7b8c9d0e1f2
Revises: e4f5a6b7c8d9
Create Date: 2026-08-03 10:00:00.000000

"""
from collections.abc import Sequence
from typing import Any

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

# revision identifiers, used by Alembic.
revision: str = "a7b8c9d0e1f2"
down_revision: str | None = "e4f5a6b7c8d9"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _audit_columns() -> list[sa.Column[Any]]:
    """Audit columns shared by every workflow table (mirrors AuditMixin)."""
    return [
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("created_by", sa.String(length=255), nullable=False),
        sa.Column("created_date", sa.DateTime(timezone=True), nullable=False),
        sa.Column("modified_by", sa.String(length=255), nullable=False),
        sa.Column("modified_date", sa.DateTime(timezone=True), nullable=False),
    ]


def upgrade() -> None:
    # ─── workflow_definitions ───
    op.create_table(
        "workflow_definitions",
        sa.Column("code", sa.String(length=100), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("entity_type", sa.String(length=100), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False),
        *_audit_columns(),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_workflow_definitions_code", "workflow_definitions", ["code"], unique=True
    )
    op.create_index(
        "ix_workflow_definitions_name", "workflow_definitions", ["name"], unique=True
    )
    op.create_index(
        "ix_workflow_definitions_entity_type", "workflow_definitions", ["entity_type"]
    )

    # ─── workflow_statuses ───
    op.create_table(
        "workflow_statuses",
        sa.Column("workflow_definition_id", sa.UUID(), nullable=False),
        sa.Column("code", sa.String(length=50), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("is_initial", sa.Boolean(), nullable=False),
        sa.Column("is_terminal", sa.Boolean(), nullable=False),
        sa.Column("sequence", sa.Integer(), nullable=False),
        *_audit_columns(),
        sa.ForeignKeyConstraint(
            ["workflow_definition_id"],
            ["workflow_definitions.id"],
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "workflow_definition_id",
            "code",
            name="uq_workflow_statuses_definition_code",
        ),
    )
    op.create_index(
        "ix_workflow_statuses_workflow_definition_id",
        "workflow_statuses",
        ["workflow_definition_id"],
    )
    op.create_index("ix_workflow_statuses_code", "workflow_statuses", ["code"])

    # ─── workflow_transitions ───
    op.create_table(
        "workflow_transitions",
        sa.Column("workflow_definition_id", sa.UUID(), nullable=False),
        sa.Column("from_status_id", sa.UUID(), nullable=False),
        sa.Column("to_status_id", sa.UUID(), nullable=False),
        sa.Column("action_code", sa.String(length=50), nullable=False),
        sa.Column("guard_expression", sa.Text(), nullable=True),
        sa.Column("requires_comment", sa.Boolean(), nullable=False),
        sa.Column("auto_execute", sa.Boolean(), nullable=False),
        sa.Column("priority", sa.Integer(), nullable=False),
        *_audit_columns(),
        sa.ForeignKeyConstraint(
            ["workflow_definition_id"],
            ["workflow_definitions.id"],
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["from_status_id"], ["workflow_statuses.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["to_status_id"], ["workflow_statuses.id"], ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "workflow_definition_id",
            "from_status_id",
            "action_code",
            name="uq_workflow_transitions_from_action",
        ),
    )
    op.create_index(
        "ix_workflow_transitions_workflow_definition_id",
        "workflow_transitions",
        ["workflow_definition_id"],
    )
    op.create_index(
        "ix_workflow_transitions_from_status_id",
        "workflow_transitions",
        ["from_status_id"],
    )
    op.create_index(
        "ix_workflow_transitions_to_status_id", "workflow_transitions", ["to_status_id"]
    )
    op.create_index(
        "ix_workflow_transitions_action_code", "workflow_transitions", ["action_code"]
    )

    # ─── workflow_instances ───
    op.create_table(
        "workflow_instances",
        sa.Column("workflow_definition_id", sa.UUID(), nullable=False),
        sa.Column("entity_type", sa.String(length=100), nullable=False),
        sa.Column("entity_id", sa.UUID(), nullable=False),
        sa.Column("current_status_id", sa.UUID(), nullable=False),
        sa.Column("initiated_by", sa.UUID(), nullable=False),
        sa.Column("priority", sa.Integer(), nullable=False),
        sa.Column("due_date", sa.DateTime(timezone=True), nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("extra_data", JSONB, nullable=False),
        *_audit_columns(),
        sa.ForeignKeyConstraint(
            ["workflow_definition_id"],
            ["workflow_definitions.id"],
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["current_status_id"], ["workflow_statuses.id"], ondelete="RESTRICT"
        ),
        sa.ForeignKeyConstraint(["initiated_by"], ["users.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_workflow_instances_workflow_definition_id",
        "workflow_instances",
        ["workflow_definition_id"],
    )
    op.create_index(
        "ix_workflow_instances_entity_type", "workflow_instances", ["entity_type"]
    )
    op.create_index(
        "ix_workflow_instances_entity_id", "workflow_instances", ["entity_id"]
    )
    op.create_index(
        "ix_workflow_instances_current_status_id",
        "workflow_instances",
        ["current_status_id"],
    )
    op.create_index(
        "ix_workflow_instances_initiated_by", "workflow_instances", ["initiated_by"]
    )
    op.create_index(
        "ix_workflow_instances_completed_at", "workflow_instances", ["completed_at"]
    )
    # "Which workflow is this record in?" is the hot lookup for every business
    # screen that shows a status badge, so it gets a composite index.
    op.create_index(
        "ix_workflow_instances_entity",
        "workflow_instances",
        ["entity_type", "entity_id"],
    )

    # ─── workflow_history ───
    # No audit columns: history rows are append-only, so modified_by/date would
    # always mirror the created pair.
    op.create_table(
        "workflow_history",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("instance_id", sa.UUID(), nullable=False),
        sa.Column("from_status_id", sa.UUID(), nullable=True),
        sa.Column("to_status_id", sa.UUID(), nullable=False),
        sa.Column("action_code", sa.String(length=50), nullable=False),
        sa.Column("actor_id", sa.UUID(), nullable=True),
        sa.Column("actor_username", sa.String(length=255), nullable=False),
        sa.Column("comments", sa.Text(), nullable=False),
        sa.Column("extra_data", JSONB, nullable=False),
        sa.Column("ip_address", sa.String(length=45), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["instance_id"], ["workflow_instances.id"], ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_workflow_history_instance_id", "workflow_history", ["instance_id"]
    )
    op.create_index(
        "ix_workflow_history_action_code", "workflow_history", ["action_code"]
    )
    op.create_index("ix_workflow_history_created_at", "workflow_history", ["created_at"])

    # ─── approval_matrices ───
    op.create_table(
        "approval_matrices",
        sa.Column("code", sa.String(length=100), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("entity_type", sa.String(length=100), nullable=False),
        sa.Column("priority", sa.Integer(), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False),
        *_audit_columns(),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_approval_matrices_code", "approval_matrices", ["code"], unique=True
    )
    op.create_index(
        "ix_approval_matrices_name", "approval_matrices", ["name"], unique=True
    )
    op.create_index(
        "ix_approval_matrices_entity_type", "approval_matrices", ["entity_type"]
    )

    # ─── approval_rules ───
    op.create_table(
        "approval_rules",
        sa.Column("matrix_id", sa.UUID(), nullable=False),
        sa.Column("field", sa.String(length=100), nullable=False),
        sa.Column("operator", sa.String(length=20), nullable=False),
        sa.Column("value", sa.String(length=500), nullable=False),
        sa.Column("data_type", sa.String(length=20), nullable=False),
        sa.Column("logical_group", sa.String(length=50), nullable=False),
        *_audit_columns(),
        sa.ForeignKeyConstraint(
            ["matrix_id"], ["approval_matrices.id"], ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_approval_rules_matrix_id", "approval_rules", ["matrix_id"])

    # ─── approval_assignments ───
    op.create_table(
        "approval_assignments",
        sa.Column("matrix_id", sa.UUID(), nullable=False),
        sa.Column("assignment_type", sa.String(length=20), nullable=False),
        sa.Column("user_id", sa.UUID(), nullable=True),
        sa.Column("role_id", sa.UUID(), nullable=True),
        sa.Column("level", sa.Integer(), nullable=False),
        *_audit_columns(),
        sa.ForeignKeyConstraint(
            ["matrix_id"], ["approval_matrices.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["role_id"], ["roles.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_approval_assignments_matrix_id", "approval_assignments", ["matrix_id"]
    )
    op.create_index(
        "ix_approval_assignments_user_id", "approval_assignments", ["user_id"]
    )
    op.create_index(
        "ix_approval_assignments_role_id", "approval_assignments", ["role_id"]
    )

    # ─── approval_tasks ───
    op.create_table(
        "approval_tasks",
        sa.Column("instance_id", sa.UUID(), nullable=False),
        sa.Column("matrix_id", sa.UUID(), nullable=True),
        sa.Column("assignee_id", sa.UUID(), nullable=False),
        sa.Column("level", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("action_taken", sa.String(length=50), nullable=True),
        sa.Column("due_date", sa.DateTime(timezone=True), nullable=True),
        sa.Column("comments", sa.Text(), nullable=True),
        *_audit_columns(),
        sa.ForeignKeyConstraint(
            ["instance_id"], ["workflow_instances.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["matrix_id"], ["approval_matrices.id"], ondelete="SET NULL"
        ),
        sa.ForeignKeyConstraint(["assignee_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "instance_id",
            "assignee_id",
            "level",
            name="uq_approval_tasks_instance_assignee_level",
        ),
    )
    op.create_index("ix_approval_tasks_instance_id", "approval_tasks", ["instance_id"])
    op.create_index("ix_approval_tasks_matrix_id", "approval_tasks", ["matrix_id"])
    op.create_index("ix_approval_tasks_assignee_id", "approval_tasks", ["assignee_id"])
    op.create_index("ix_approval_tasks_status", "approval_tasks", ["status"])
    op.create_index("ix_approval_tasks_due_date", "approval_tasks", ["due_date"])


def downgrade() -> None:
    # Reverse dependency order.
    op.drop_table("approval_tasks")
    op.drop_table("approval_assignments")
    op.drop_table("approval_rules")
    op.drop_table("approval_matrices")
    op.drop_table("workflow_history")
    op.drop_table("workflow_instances")
    op.drop_table("workflow_transitions")
    op.drop_table("workflow_statuses")
    op.drop_table("workflow_definitions")
