"""Collapse product hierarchy into single product_master table.

Drops the former two-table hierarchy (product_masters + product_details) and
replaces it with a single ``product_master`` table that carries both the
base-product identity fields (basic_material_code, product_name) and the
SKU/variant fields (child_code, variant_description, hsn_code, pack_size,
unit_of_measure, mrp, rate, gst_percent, status).

Foreign keys in ``agreements`` and ``invoice_lines`` that previously pointed
to ``product_details.id`` are re-pointed to ``product_master.id``.

NOTE: This migration drops all existing product data in both tables.
      Back up product_masters and product_details before running if needed.

Revision ID: g4b5c6d7e8f9
Revises: f3a4b5c6d7e8
Create Date: 2026-07-06
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID

revision: str = "g4b5c6d7e8f9"
down_revision: Union[str, None] = "b2c3d4e5f6a7"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _audit_columns() -> list[sa.Column]:
    return [
        sa.Column("created_by", sa.String(255), server_default="system", nullable=False),
        sa.Column(
            "created_date",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column("modified_by", sa.String(255), server_default="system", nullable=False),
        sa.Column(
            "modified_date",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
    ]


def upgrade() -> None:
    # ------------------------------------------------------------------ #
    # 1. Drop FK constraints on dependents before dropping source tables
    # ------------------------------------------------------------------ #

    # agreements.product_detail_id -> product_details.id
    op.drop_constraint(
        "agreements_product_detail_id_fkey",
        "agreements",
        type_="foreignkey",
    )
    # invoice_lines.product_detail_id -> product_details.id
    op.drop_constraint(
        "invoice_lines_product_detail_id_fkey",
        "invoice_lines",
        type_="foreignkey",
    )

    # ------------------------------------------------------------------ #
    # 2. Drop old tables (product_details first — FK child, then product_masters)
    # ------------------------------------------------------------------ #
    op.drop_index("ix_product_details_child_code", table_name="product_details")
    op.drop_index("ix_product_details_product_master_id", table_name="product_details")
    op.drop_table("product_details")

    op.drop_index("ix_product_masters_basic_material_code", table_name="product_masters")
    op.drop_table("product_masters")

    # ------------------------------------------------------------------ #
    # 3. Create merged product_master table
    # ------------------------------------------------------------------ #
    op.create_table(
        "product_master",
        sa.Column("id", UUID(as_uuid=True), nullable=False),
        sa.Column("basic_material_code", sa.String(50), nullable=False),
        sa.Column("product_name", sa.String(255), nullable=False),
        sa.Column("child_code", sa.String(50), nullable=False),
        sa.Column("variant_description", sa.Text(), nullable=True),
        sa.Column("hsn_code", sa.String(20), nullable=True),
        sa.Column("pack_size", sa.String(50), nullable=True),
        sa.Column("unit_of_measure", sa.String(20), nullable=True),
        sa.Column("mrp", sa.Numeric(12, 2), nullable=True),
        sa.Column("rate", sa.Numeric(12, 2), nullable=True),
        sa.Column("gst_percent", sa.Numeric(5, 2), nullable=True),
        sa.Column("status", sa.String(20), server_default="Active", nullable=False),
        *_audit_columns(),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_product_master_child_code",
        "product_master",
        ["child_code"],
        unique=True,
    )
    op.create_index(
        "ix_product_master_basic_material_code",
        "product_master",
        ["basic_material_code"],
    )

    # ------------------------------------------------------------------ #
    # 4. Re-add FK constraints on dependents pointing to product_master
    #    First clear any orphaned rows from agreements and invoice_lines
    #    (their product_detail_id values pointed at the now-dropped
    #    product_details table, so they are no longer valid).
    # ------------------------------------------------------------------ #
    op.execute("DELETE FROM invoice_lines")
    op.execute("DELETE FROM agreements")

    op.create_foreign_key(
        "agreements_product_detail_id_fkey",
        "agreements",
        "product_master",
        ["product_detail_id"],
        ["id"],
    )
    op.create_foreign_key(
        "invoice_lines_product_detail_id_fkey",
        "invoice_lines",
        "product_master",
        ["product_detail_id"],
        ["id"],
    )


def downgrade() -> None:
    # ------------------------------------------------------------------ #
    # 1. Drop FK constraints on dependents
    # ------------------------------------------------------------------ #
    op.drop_constraint(
        "agreements_product_detail_id_fkey",
        "agreements",
        type_="foreignkey",
    )
    op.drop_constraint(
        "invoice_lines_product_detail_id_fkey",
        "invoice_lines",
        type_="foreignkey",
    )

    # ------------------------------------------------------------------ #
    # 2. Drop merged table
    # ------------------------------------------------------------------ #
    op.drop_index("ix_product_master_child_code", table_name="product_master")
    op.drop_index("ix_product_master_basic_material_code", table_name="product_master")
    op.drop_table("product_master")

    # ------------------------------------------------------------------ #
    # 3. Re-create original two tables (empty — data was dropped in upgrade)
    # ------------------------------------------------------------------ #
    op.create_table(
        "product_masters",
        sa.Column("id", UUID(as_uuid=True), nullable=False),
        sa.Column("basic_material_code", sa.String(50), nullable=False),
        sa.Column("product_name", sa.String(255), nullable=False),
        sa.Column("therapeutic_category", sa.String(255), nullable=True),
        sa.Column("status", sa.String(20), server_default="Active", nullable=False),
        sa.Column("created_by", sa.String(255), server_default="system", nullable=False),
        sa.Column("created_date", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("modified_by", sa.String(255), server_default="system", nullable=False),
        sa.Column("modified_date", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_product_masters_basic_material_code",
        "product_masters",
        ["basic_material_code"],
        unique=True,
    )

    op.create_table(
        "product_details",
        sa.Column("id", UUID(as_uuid=True), nullable=False),
        sa.Column("child_code", sa.String(50), nullable=False),
        sa.Column("product_master_id", UUID(as_uuid=True), nullable=False),
        sa.Column("variant_description", sa.Text(), nullable=True),
        sa.Column("hsn_code", sa.String(20), nullable=True),
        sa.Column("pack_size", sa.String(50), nullable=True),
        sa.Column("unit_of_measure", sa.String(20), nullable=True),
        sa.Column("mrp", sa.Numeric(12, 2), nullable=True),
        sa.Column("rate", sa.Numeric(12, 2), nullable=True),
        sa.Column("gst_percent", sa.Numeric(5, 2), nullable=True),
        sa.Column("status", sa.String(20), server_default="Active", nullable=False),
        sa.Column("created_by", sa.String(255), server_default="system", nullable=False),
        sa.Column("created_date", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("modified_by", sa.String(255), server_default="system", nullable=False),
        sa.Column("modified_date", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(
            ["product_master_id"],
            ["product_masters.id"],
            ondelete="RESTRICT",
        ),
    )
    op.create_index(
        "ix_product_details_child_code",
        "product_details",
        ["child_code"],
        unique=True,
    )
    op.create_index(
        "ix_product_details_product_master_id",
        "product_details",
        ["product_master_id"],
    )

    # Re-add FK constraints pointing back to product_details
    op.create_foreign_key(
        "agreements_product_detail_id_fkey",
        "agreements",
        "product_details",
        ["product_detail_id"],
        ["id"],
    )
    op.create_foreign_key(
        "invoice_lines_product_detail_id_fkey",
        "invoice_lines",
        "product_details",
        ["product_detail_id"],
        ["id"],
    )
