"""drop_darwinbox_employees_table

The Darwinbox integration and the employee directory that read from it have been
removed, so the table they owned goes with them.

Done as a new revision rather than by editing the three migrations that built the
table (`f3a4b5c6d7e8` create, `b2c3d4e5f6a7` widen, `e4f5a6b7c8d9` drop redundant
constraint): those sit mid-chain with four revisions after them, and deployed
databases have already recorded them. Rewriting history would strand any
environment that is already migrated.

This revision is deliberately one-way. Recreating the table faithfully would mean
restating 41 columns and their server defaults here, duplicating a definition
whose ORM model no longer exists to check it against — and a table restored
without the feature code that used it has no value. To go back, downgrade past
`f3a4b5c6d7e8` instead, where the real definition still lives.

Revision ID: c9d0e1f2a3b4
Revises: b8c9d0e1f2a3
Create Date: 2026-08-03 14:00:00.000000

"""
from collections.abc import Sequence

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "c9d0e1f2a3b4"
down_revision: str | None = "b8c9d0e1f2a3"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

TABLE = "darwinbox_employees"


def upgrade() -> None:
    # IF EXISTS so the revision is safe on an environment where the table was
    # never created, or was already dropped by hand.
    op.execute(f"DROP TABLE IF EXISTS {TABLE} CASCADE")


def downgrade() -> None:
    raise NotImplementedError(
        f"Dropping {TABLE} is not reversible: the Darwinbox feature and its ORM "
        "model were removed in the same change, so there is no definition left to "
        "recreate the table from. Downgrade past f3a4b5c6d7e8 to reach a revision "
        "that still defines it."
    )
