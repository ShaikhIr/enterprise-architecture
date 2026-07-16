"""Rename product_detail_id to product_master_id + update claim_lines unique constraint.

Renames the FK column `product_detail_id` → `product_master_id` in:
  - agreements
  - invoice_lines
  - claim_lines

Also updates the unique constraint on claim_lines from
  (claim_header_id, invoice_header_id)
to
  (claim_header_id, invoice_header_id, product_master_id)
to support one claim line per product per invoice.

Revision ID: i6d7e8f9a0b1
Revises: h5c6d7e8f9a0
Create Date: 2026-07-10
"""

from alembic import op

revision = "i6d7e8f9a0b1"
down_revision = "h5c6d7e8f9a0"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # ── 1. agreements table ───────────────────────────────────────────────────
    op.alter_column("agreements", "product_detail_id", new_column_name="product_master_id")

    # ── 2. invoice_lines table ────────────────────────────────────────────────
    op.alter_column("invoice_lines", "product_detail_id", new_column_name="product_master_id")

    # ── 3. claim_lines table ──────────────────────────────────────────────────
    op.alter_column("claim_lines", "product_detail_id", new_column_name="product_master_id")

    # Drop old unique constraint (claim_header_id, invoice_header_id)
    op.drop_constraint("uq_claim_line_invoice", "claim_lines", type_="unique")

    # Create new unique constraint (claim_header_id, invoice_header_id, product_master_id)
    op.create_unique_constraint(
        "uq_claim_line_invoice_product",
        "claim_lines",
        ["claim_header_id", "invoice_header_id", "product_master_id"],
    )


def downgrade() -> None:
    # ── Revert claim_lines ────────────────────────────────────────────────────
    op.drop_constraint("uq_claim_line_invoice_product", "claim_lines", type_="unique")
    op.create_unique_constraint(
        "uq_claim_line_invoice",
        "claim_lines",
        ["claim_header_id", "invoice_header_id"],
    )
    op.alter_column("claim_lines", "product_master_id", new_column_name="product_detail_id")

    # ── Revert invoice_lines ──────────────────────────────────────────────────
    op.alter_column("invoice_lines", "product_master_id", new_column_name="product_detail_id")

    # ── Revert agreements ─────────────────────────────────────────────────────
    op.alter_column("agreements", "product_master_id", new_column_name="product_detail_id")
