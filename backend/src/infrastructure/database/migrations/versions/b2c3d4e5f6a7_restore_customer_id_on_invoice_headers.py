"""Restore customer_id FK on invoice_headers (invoice maps to customer, not just vendor).

Revision ID: b2c3d4e5f6a7
Revises: a1b2c3d4e5f6
Create Date: 2026-07-02
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import UUID

revision: str = "b2c3d4e5f6a7"
down_revision: Union[str, None] = "a1b2c3d4e5f6"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Re-add customer_id as nullable first (existing rows have no customer yet)
    op.add_column(
        "invoice_headers",
        sa.Column("customer_id", UUID(as_uuid=True), nullable=True),
    )
    op.create_foreign_key(
        "invoice_headers_customer_id_fkey",
        "invoice_headers",
        "customers",
        ["customer_id"],
        ["id"],
    )
    op.create_index(
        "ix_invoice_headers_customer_id",
        "invoice_headers",
        ["customer_id"],
    )


def downgrade() -> None:
    op.drop_index("ix_invoice_headers_customer_id", table_name="invoice_headers")
    op.drop_constraint(
        "invoice_headers_customer_id_fkey",
        "invoice_headers",
        type_="foreignkey",
    )
    op.drop_column("invoice_headers", "customer_id")
