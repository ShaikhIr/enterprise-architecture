"""Add commission claim tables and drop old stub.

Creates four new tables for the Commission Claim Management feature:
  - claim_headers          — top-level claim aggregate
  - claim_lines            — per-invoice commission rows (CASCADE FK to claim_headers)
  - claim_audit_logs       — append-only audit trail
  - claim_number_sequences — per-financial-year sequence counter

Also drops the old ``commission_claims`` stub table that was created as a
placeholder before the full schema was designed.

Requirements: 13.3

Revision ID: h5c6d7e8f9a0
Revises: g4b5c6d7e8f9
Create Date: 2026-07-07
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB, UUID

revision = "h5c6d7e8f9a0"
down_revision = "g4b5c6d7e8f9"
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Create all four commission claim tables and drop the old stub."""

    # ── 1. Drop old stub table ────────────────────────────────────────────────
    # The commission_claims table was a placeholder created in migration
    # e2f3a4b5c6d7. It is replaced by the four tables below.
    op.execute("DROP TABLE IF EXISTS commission_claims")

    # ── 2. claim_headers ─────────────────────────────────────────────────────
    op.create_table(
        "claim_headers",
        # PK + audit columns from BaseModel / AuditMixin
        sa.Column("id", UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column(
            "created_by",
            sa.String(255),
            server_default="system",
            nullable=False,
        ),
        sa.Column(
            "created_date",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "modified_by",
            sa.String(255),
            server_default="system",
            nullable=False,
        ),
        sa.Column(
            "modified_date",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        # Domain columns
        sa.Column(
            "vendor_id",
            UUID(as_uuid=True),
            sa.ForeignKey("vendors.id"),
            nullable=False,
        ),
        sa.Column("claim_number", sa.String(20), unique=True, nullable=True),
        sa.Column("claim_date", sa.Date, nullable=False),
        sa.Column(
            "status",
            sa.String(30),
            server_default="Draft",
            nullable=False,
        ),
        sa.Column("workflow_instance_id", UUID(as_uuid=True), nullable=True),
        # Header totals — recalculated on every line change
        sa.Column(
            "total_claim_amount",
            sa.Numeric(16, 2),
            server_default="0",
            nullable=False,
        ),
        sa.Column(
            "total_commission_amount",
            sa.Numeric(16, 2),
            server_default="0",
            nullable=False,
        ),
        sa.Column(
            "total_gst_amount",
            sa.Numeric(16, 2),
            server_default="0",
            nullable=False,
        ),
        sa.Column(
            "total_tds_amount",
            sa.Numeric(16, 2),
            server_default="0",
            nullable=False,
        ),
        sa.Column(
            "total_ld_amount",
            sa.Numeric(16, 2),
            server_default="0",
            nullable=False,
        ),
        sa.Column(
            "total_retention_amount",
            sa.Numeric(16, 2),
            server_default="0",
            nullable=False,
        ),
        # Post-closure fields
        sa.Column(
            "gstn_verification_status",
            sa.String(20),
            server_default="Pending",
            nullable=False,
        ),
        sa.Column("gst_invoice_number", sa.String(100), nullable=True),
        sa.Column("gst_invoice_upload_date", sa.Date, nullable=True),
        sa.Column("sap_p2p_booking_reference", sa.String(100), nullable=True),
    )
    # Individual column indexes
    op.create_index("ix_claim_headers_vendor_id", "claim_headers", ["vendor_id"])
    op.create_index("ix_claim_headers_claim_number", "claim_headers", ["claim_number"])
    op.create_index("ix_claim_headers_status", "claim_headers", ["status"])
    # Composite index: (vendor_id, status) — supports vendor-scoped list queries
    op.create_index(
        "ix_claim_headers_vendor_status",
        "claim_headers",
        ["vendor_id", "status"],
    )

    # ── 3. claim_lines ───────────────────────────────────────────────────────
    op.create_table(
        "claim_lines",
        # PK + audit columns from BaseModel / AuditMixin
        sa.Column("id", UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column(
            "created_by",
            sa.String(255),
            server_default="system",
            nullable=False,
        ),
        sa.Column(
            "created_date",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "modified_by",
            sa.String(255),
            server_default="system",
            nullable=False,
        ),
        sa.Column(
            "modified_date",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        # FK to parent header — ON DELETE CASCADE so lines are wiped with header
        sa.Column(
            "claim_header_id",
            UUID(as_uuid=True),
            sa.ForeignKey("claim_headers.id", ondelete="CASCADE"),
            nullable=False,
        ),
        # FKs to other master tables
        sa.Column(
            "invoice_header_id",
            UUID(as_uuid=True),
            sa.ForeignKey("invoice_headers.id"),
            nullable=False,
        ),
        sa.Column(
            "product_detail_id",
            UUID(as_uuid=True),
            sa.ForeignKey("product_master.id"),
            nullable=False,
        ),
        sa.Column(
            "customer_id",
            UUID(as_uuid=True),
            sa.ForeignKey("customers.id"),
            nullable=False,
        ),
        # Invoice-sourced input fields
        sa.Column("bill_amount_excl_gst", sa.Numeric(14, 2), nullable=False),
        sa.Column(
            "amount_deducted",
            sa.Numeric(14, 2),
            server_default="0",
            nullable=False,
        ),
        sa.Column(
            "tds_value",
            sa.Numeric(14, 2),
            server_default="0",
            nullable=False,
        ),
        sa.Column(
            "ld_charges",
            sa.Numeric(14, 2),
            server_default="0",
            nullable=False,
        ),
        sa.Column(
            "retention_amount",
            sa.Numeric(14, 2),
            server_default="0",
            nullable=False,
        ),
        # 7-step formula outputs — all persisted for audit (Req 3.10)
        sa.Column(
            "net_amount",
            sa.Numeric(14, 2),
            server_default="0",
            nullable=False,
        ),
        sa.Column(
            "commission_payable_base",
            sa.Numeric(14, 2),
            server_default="0",
            nullable=False,
        ),
        sa.Column("due_date", sa.Date, nullable=False),
        sa.Column("payment_clearing_date", sa.Date, nullable=False),
        sa.Column(
            "delay_days",
            sa.Integer,
            server_default="0",
            nullable=False,
        ),
        sa.Column(
            "applicable_commission_percent",
            sa.Numeric(7, 4),
            server_default="0",
            nullable=False,
        ),
        sa.Column(
            "commission_amount",
            sa.Numeric(14, 2),
            server_default="0",
            nullable=False,
        ),
        sa.Column(
            "gst_on_commission",
            sa.Numeric(14, 2),
            server_default="0",
            nullable=False,
        ),
        sa.Column(
            "final_line_claim_amount",
            sa.Numeric(14, 2),
            server_default="0",
            nullable=False,
        ),
        # POD & remarks
        sa.Column("pod_document_id", UUID(as_uuid=True), nullable=True),
        sa.Column(
            "remarks",
            sa.Text,
            server_default="",
            nullable=False,
        ),
        # Unique constraint: one invoice per claim (prevents duplicates)
        sa.UniqueConstraint(
            "claim_header_id",
            "invoice_header_id",
            name="uq_claim_line_invoice",
        ),
    )
    # Indexes on claim_lines
    op.create_index(
        "ix_claim_lines_header",
        "claim_lines",
        ["claim_header_id"],
    )
    op.create_index(
        "ix_claim_lines_invoice_header_id",
        "claim_lines",
        ["invoice_header_id"],
    )

    # ── 4. claim_audit_logs ──────────────────────────────────────────────────
    op.create_table(
        "claim_audit_logs",
        # PK + audit columns from BaseModel / AuditMixin
        sa.Column("id", UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column(
            "created_by",
            sa.String(255),
            server_default="system",
            nullable=False,
        ),
        sa.Column(
            "created_date",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "modified_by",
            sa.String(255),
            server_default="system",
            nullable=False,
        ),
        sa.Column(
            "modified_date",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        # Domain columns
        sa.Column(
            "claim_header_id",
            UUID(as_uuid=True),
            sa.ForeignKey("claim_headers.id"),
            nullable=False,
        ),
        sa.Column("action", sa.String(50), nullable=False),
        sa.Column("actor_username", sa.String(255), nullable=False),
        sa.Column("actor_user_id", UUID(as_uuid=True), nullable=False),
        sa.Column(
            "timestamp_utc",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column("from_status", sa.String(30), nullable=True),
        sa.Column("to_status", sa.String(30), nullable=True),
        sa.Column("workflow_step_name", sa.String(100), nullable=True),
        sa.Column("remarks", sa.Text, nullable=True),
        # JSONB dict: {"field_name": {"old": ..., "new": ...}} for field-edit events
        sa.Column("field_changes", JSONB, nullable=True),
    )
    # Composite index: (claim_header_id, timestamp_utc) — supports paged audit queries
    op.create_index(
        "ix_claim_audit_logs_header_ts",
        "claim_audit_logs",
        ["claim_header_id", "timestamp_utc"],
    )
    # Individual index on claim_header_id for simple FK lookups
    op.create_index(
        "ix_claim_audit_logs_claim_header_id",
        "claim_audit_logs",
        ["claim_header_id"],
    )

    # ── 5. claim_number_sequences ────────────────────────────────────────────
    op.create_table(
        "claim_number_sequences",
        # PK + audit columns from BaseModel / AuditMixin
        sa.Column("id", UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column(
            "created_by",
            sa.String(255),
            server_default="system",
            nullable=False,
        ),
        sa.Column(
            "created_date",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "modified_by",
            sa.String(255),
            server_default="system",
            nullable=False,
        ),
        sa.Column(
            "modified_date",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        # One row per Indian financial year, e.g. "2025-26"
        sa.Column(
            "financial_year",
            sa.String(10),
            unique=True,
            nullable=False,
        ),
        sa.Column(
            "last_sequence",
            sa.Integer,
            server_default="0",
            nullable=False,
        ),
    )
    # Unique index on financial_year — also enforces the unique constraint
    op.create_index(
        "ix_claim_number_seq_fy",
        "claim_number_sequences",
        ["financial_year"],
        unique=True,
    )


def downgrade() -> None:
    """Drop all four commission claim tables and restore the old stub."""

    # Drop indexes before tables (some databases require this)
    op.drop_index("ix_claim_number_seq_fy", table_name="claim_number_sequences")
    op.drop_index(
        "ix_claim_audit_logs_claim_header_id", table_name="claim_audit_logs"
    )
    op.drop_index("ix_claim_audit_logs_header_ts", table_name="claim_audit_logs")
    op.drop_index("ix_claim_lines_invoice_header_id", table_name="claim_lines")
    op.drop_index("ix_claim_lines_header", table_name="claim_lines")
    op.drop_index("ix_claim_headers_vendor_status", table_name="claim_headers")
    op.drop_index("ix_claim_headers_status", table_name="claim_headers")
    op.drop_index("ix_claim_headers_claim_number", table_name="claim_headers")
    op.drop_index("ix_claim_headers_vendor_id", table_name="claim_headers")

    # Drop tables in reverse dependency order
    op.drop_table("claim_number_sequences")
    op.drop_table("claim_audit_logs")
    op.drop_table("claim_lines")
    op.drop_table("claim_headers")

    # Restore the old stub table so that downgrade is fully reversible
    op.create_table(
        "commission_claims",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "claim_number",
            sa.String(50),
            unique=True,
            nullable=False,
        ),
        sa.Column("employee_id", UUID(as_uuid=True), nullable=False, index=True),
        sa.Column("employee_name", sa.String(255), nullable=False),
        sa.Column("amount", sa.Numeric(12, 2), nullable=False),
        sa.Column("company", sa.String(100), nullable=False),
        sa.Column(
            "department",
            sa.String(100),
            server_default="",
            nullable=False,
        ),
        sa.Column(
            "region",
            sa.String(100),
            server_default="",
            nullable=False,
        ),
        sa.Column(
            "description",
            sa.Text,
            server_default="",
            nullable=False,
        ),
        sa.Column(
            "status",
            sa.String(30),
            server_default="DRAFT",
            nullable=False,
            index=True,
        ),
        sa.Column("workflow_instance_id", UUID(as_uuid=True), nullable=True),
        sa.Column(
            "created_by",
            sa.String(255),
            server_default="system",
            nullable=False,
        ),
        sa.Column(
            "created_date",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "modified_by",
            sa.String(255),
            server_default="system",
            nullable=False,
        ),
        sa.Column(
            "modified_date",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
    )
