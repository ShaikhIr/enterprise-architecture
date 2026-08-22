"""drop_redundant_darwinbox_employee_id_constraint

Migration f3a4b5c6d7e8 created two independent uniqueness guards on
darwinbox_employees.employee_id:

  1. sa.UniqueConstraint('employee_id')  -> darwinbox_employees_employee_id_key
  2. create_index(..., unique=True)      -> ix_darwinbox_employees_employee_id

The ORM model declares only `unique=True, index=True`, which maps to the unique
index (2). The standalone constraint (1) therefore showed up as permanent schema
drift and meant Postgres maintained two unique indexes on the same column,
doubling write cost and storage for no added guarantee.

Dropping the constraint leaves uniqueness fully enforced by the unique index, so
behaviour is unchanged. This makes `alembic check` clean, which lets CI gate on
model/schema drift.

Revision ID: e4f5a6b7c8d9
Revises: d1e2f3a4b5c6
Create Date: 2026-07-31 11:20:00.000000

"""
from collections.abc import Sequence

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "e4f5a6b7c8d9"
down_revision: str | None = "d1e2f3a4b5c6"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

CONSTRAINT_NAME = "darwinbox_employees_employee_id_key"


def upgrade() -> None:
    # IF EXISTS keeps this idempotent across environments that may already
    # have diverged (e.g. a DB created from metadata rather than migrations).
    op.execute(
        f"ALTER TABLE darwinbox_employees DROP CONSTRAINT IF EXISTS {CONSTRAINT_NAME}"
    )


def downgrade() -> None:
    op.create_unique_constraint(CONSTRAINT_NAME, "darwinbox_employees", ["employee_id"])
