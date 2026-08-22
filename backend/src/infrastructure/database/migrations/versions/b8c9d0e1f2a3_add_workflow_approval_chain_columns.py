"""add_workflow_approval_chain_columns

Connects the workflow half of the engine to the approval matrix half.

Two columns, both needed because the link could not be inferred:

`workflow_transitions.action_type`
    `action_code` is free text chosen by whoever designs the workflow, so code
    cannot tell "SIGN_OFF" from "APPROVE". This column is the designer's explicit
    statement of what a move means to the approval chain, and it is the only
    signal the coordinator reads. Existing rows are backfilled from `action_code`
    where it already matches a known type, and left as CUSTOM otherwise — CUSTOM
    being the safe default, since it leaves approvals untouched.

`workflow_instances.approval_level`
    Which level the instance is waiting on, 0 for none. Stored rather than derived
    from task history so that a refer-back can reset the chain outright instead of
    the engine having to reinterpret past tasks to spot the reset.

Revision ID: b8c9d0e1f2a3
Revises: a7b8c9d0e1f2
Create Date: 2026-08-03 12:00:00.000000

"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "b8c9d0e1f2a3"
down_revision: str | None = "a7b8c9d0e1f2"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# Action codes that carry an unambiguous meaning. Anything else stays CUSTOM
# rather than being guessed at.
_KNOWN_ACTION_TYPES = (
    "SUBMIT",
    "APPROVE",
    "REJECT",
    "REFER_BACK",
    "CANCEL",
    "CLOSE",
    "ESCALATE",
)


def upgrade() -> None:
    op.add_column(
        "workflow_transitions",
        sa.Column(
            "action_type",
            sa.String(length=20),
            nullable=False,
            server_default="CUSTOM",
        ),
    )
    op.add_column(
        "workflow_instances",
        sa.Column(
            "approval_level", sa.Integer(), nullable=False, server_default="0"
        ),
    )

    # Backfill: where the action code is already one of the known semantics, adopt
    # it. This is the common case for workflows seeded or built before the column
    # existed, and saves re-declaring every transition by hand.
    codes = ", ".join(f"'{code}'" for code in _KNOWN_ACTION_TYPES)
    op.execute(
        f"UPDATE workflow_transitions "  # noqa: S608 - codes are a fixed literal list
        f"SET action_type = action_code "
        f"WHERE action_code IN ({codes})"
    )

    # The server defaults existed only to make the columns addable to populated
    # tables; the ORM supplies both values from here on.
    op.alter_column("workflow_transitions", "action_type", server_default=None)
    op.alter_column("workflow_instances", "approval_level", server_default=None)


def downgrade() -> None:
    op.drop_column("workflow_instances", "approval_level")
    op.drop_column("workflow_transitions", "action_type")
