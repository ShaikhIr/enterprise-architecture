"""Remove customer_type from customers, customer_id from invoice_headers, add city to vendors.

Revision ID: a1b2c3d4e5f6
Revises: f3a4b5c6d7e8
Create Date: 2026-07-02
"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID

revision: str = "a1b2c3d4e5f6"
down_revision: Union[str, None] = "d8e9f0a1b2c3"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Remove customer_type from customers table
    op.drop_column("customers", "customer_type")

    # Remove customer_id FK and column from invoice_headers
    op.drop_index("ix_invoice_headers_customer_id", table_name="invoice_headers")
    op.drop_constraint(
        "invoice_headers_customer_id_fkey", "invoice_headers", type_="foreignkey"
    )
    op.drop_column("invoice_headers", "customer_id")

    # Add city column to vendors
    op.add_column("vendors", sa.Column("city", sa.String(100), nullable=True))


def downgrade() -> None:
    # Remove city from vendors
    op.drop_column("vendors", "city")

    # Re-add customer_id to invoice_headers
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
        "ix_invoice_headers_customer_id", "invoice_headers", ["customer_id"]
    )

    # Re-add customer_type to customers
    op.add_column(
        "customers",
        sa.Column("customer_type", sa.String(40), nullable=True),
    )
