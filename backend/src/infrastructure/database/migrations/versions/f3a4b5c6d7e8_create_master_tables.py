"""Create LACM master tables.

Creates all master tables (Entity, Vendor, Customer, Product Master,
Agreement, Vendor-Customer Mapping, Invoice Header/Line) plus the
``users.entity_id`` link column, mirroring the SQLAlchemy ORM models under
``src/infrastructure/database/models/masters`` and the design data model.

The product hierarchy has been collapsed from two tables (product_masters +
product_details) into a single ``product_master`` table that carries both
the base-product identity fields and the SKU/variant fields.

Foreign keys apply the design's ON DELETE rules:
- ``agreements.prior_agreement_id`` -> ``agreements.id`` ON DELETE SET NULL
- ``invoice_lines.invoice_header_id`` -> ``invoice_headers.id`` ON DELETE CASCADE
- ``users.entity_id`` -> ``entities.id`` ON DELETE SET NULL

Revision ID: f3a4b5c6d7e8
Revises: e2f3a4b5c6d7
Create Date: 2026-06-25
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID

# revision identifiers, used by Alembic.
revision: str = "f3a4b5c6d7e8"
down_revision: Union[str, None] = "e2f3a4b5c6d7"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _audit_columns() -> list[sa.Column]:
    """Audit columns provided by ``BaseModel``/``AuditMixin`` on every model."""
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
    # Entity master
    # ------------------------------------------------------------------ #
    op.create_table(
        "entities",
        sa.Column("id", UUID(as_uuid=True), nullable=False),
        sa.Column("entity_name", sa.String(255), nullable=False),
        sa.Column("short_code", sa.String(50), nullable=True),
        sa.Column("company_code", sa.String(50), nullable=True),
        sa.Column("is_active", sa.Boolean(), server_default=sa.text("true"), nullable=False),
        *_audit_columns(),
        sa.PrimaryKeyConstraint("id"),
    )
    # Trimmed, case-insensitive uniqueness on entity_name and company_code.
    op.create_index(
        "uq_entities_entity_name_ci",
        "entities",
        [sa.text("lower(trim(entity_name))")],
        unique=True,
    )
    op.create_index(
        "uq_entities_company_code_ci",
        "entities",
        [sa.text("lower(trim(company_code))")],
        unique=True,
    )

    # users.entity_id link column (ON DELETE SET NULL).
    op.add_column(
        "users",
        sa.Column("entity_id", UUID(as_uuid=True), nullable=True),
    )
    op.create_foreign_key(
        "fk_users_entity_id_entities",
        "users",
        "entities",
        ["entity_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_index("ix_users_entity_id", "users", ["entity_id"])

    # ------------------------------------------------------------------ #
    # Vendor master
    # ------------------------------------------------------------------ #
    op.create_table(
        "vendors",
        sa.Column("id", UUID(as_uuid=True), nullable=False),
        sa.Column("vendor_code", sa.String(50), nullable=False),
        sa.Column("vendor_name", sa.String(255), nullable=False),
        sa.Column("vendor_email", sa.String(255), nullable=False),
        sa.Column("vendor_contact", sa.String(20), nullable=True),
        sa.Column("vendor_address", sa.Text(), nullable=True),
        sa.Column("gstn_number", sa.String(15), nullable=True),
        sa.Column("pan_number", sa.String(10), nullable=True),
        sa.Column("bank_account_no", sa.String(30), nullable=True),
        sa.Column("bank_ifsc", sa.String(11), nullable=True),
        sa.Column("bank_name", sa.String(100), nullable=True),
        sa.Column("portal_user_id", UUID(as_uuid=True), nullable=True),
        sa.Column("status", sa.String(20), server_default="Active", nullable=False),
        *_audit_columns(),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(["portal_user_id"], ["users.id"]),
    )
    op.create_index("ix_vendors_vendor_code", "vendors", ["vendor_code"], unique=True)
    op.create_index("ix_vendors_vendor_email", "vendors", ["vendor_email"], unique=True)
    op.create_index("ix_vendors_portal_user_id", "vendors", ["portal_user_id"])

    # ------------------------------------------------------------------ #
    # Customer master
    # ------------------------------------------------------------------ #
    op.create_table(
        "customers",
        sa.Column("id", UUID(as_uuid=True), nullable=False),
        sa.Column("customer_code", sa.String(50), nullable=False),
        sa.Column("customer_name", sa.String(255), nullable=False),
        sa.Column("customer_type", sa.String(40), nullable=True),
        sa.Column("address", sa.Text(), nullable=True),
        sa.Column("gstn_number", sa.String(15), nullable=True),
        sa.Column("contact_person", sa.String(100), nullable=True),
        sa.Column("contact_number", sa.String(20), nullable=True),
        sa.Column("contact_email", sa.String(255), nullable=True),
        sa.Column("status", sa.String(20), server_default="Active", nullable=False),
        *_audit_columns(),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("customer_code", name="uq_customers_customer_code"),
    )

    # ------------------------------------------------------------------ #
    # Product Master (merged product_details — single table)
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
    # Agreement master
    # ------------------------------------------------------------------ #
    op.create_table(
        "agreements",
        sa.Column("id", UUID(as_uuid=True), nullable=False),
        sa.Column("vendor_id", UUID(as_uuid=True), nullable=False),
        sa.Column("product_detail_id", UUID(as_uuid=True), nullable=False),
        sa.Column("from_date", sa.Date(), nullable=False),
        sa.Column("to_date", sa.Date(), nullable=False),
        sa.Column("slab_in_days", sa.Integer(), nullable=False),
        sa.Column("reduction_percent", sa.Numeric(5, 2), nullable=False),
        sa.Column("max_commission_percent", sa.Numeric(5, 2), nullable=False),
        sa.Column("min_commission_percent", sa.Numeric(5, 2), nullable=False),
        sa.Column("credit_days", sa.Integer(), server_default="0", nullable=False),
        sa.Column("agreement_type", sa.String(20), server_default="Original", nullable=False),
        sa.Column("prior_agreement_id", UUID(as_uuid=True), nullable=True),
        sa.Column("agreement_document_ref", sa.String(512), nullable=True),
        sa.Column("status", sa.String(20), server_default="Active", nullable=False),
        *_audit_columns(),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(["vendor_id"], ["vendors.id"]),
        sa.ForeignKeyConstraint(["product_detail_id"], ["product_master.id"]),
        sa.ForeignKeyConstraint(
            ["prior_agreement_id"],
            ["agreements.id"],
            ondelete="SET NULL",
        ),
    )
    op.create_index("ix_agreements_vendor_id", "agreements", ["vendor_id"])
    op.create_index("ix_agreements_product_detail_id", "agreements", ["product_detail_id"])
    op.create_index("ix_agreements_prior_agreement_id", "agreements", ["prior_agreement_id"])
    op.create_index(
        "ix_agreements_vendor_detail_status",
        "agreements",
        ["vendor_id", "product_detail_id", "status"],
    )

    # ------------------------------------------------------------------ #
    # Vendor-Customer Mapping
    # ------------------------------------------------------------------ #
    op.create_table(
        "vendor_customer_mappings",
        sa.Column("id", UUID(as_uuid=True), nullable=False),
        sa.Column("vendor_id", UUID(as_uuid=True), nullable=False),
        sa.Column("customer_id", UUID(as_uuid=True), nullable=False),
        sa.Column("validity_from", sa.Date(), nullable=False),
        sa.Column("validity_to", sa.Date(), nullable=False),
        sa.Column("status", sa.String(20), server_default="Active", nullable=False),
        *_audit_columns(),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(["vendor_id"], ["vendors.id"]),
        sa.ForeignKeyConstraint(["customer_id"], ["customers.id"]),
    )
    op.create_index(
        "ix_vendor_customer_mappings_vendor_customer_status",
        "vendor_customer_mappings",
        ["vendor_id", "customer_id", "status"],
    )

    # ------------------------------------------------------------------ #
    # Invoice Header / Invoice Line
    # ------------------------------------------------------------------ #
    op.create_table(
        "invoice_headers",
        sa.Column("id", UUID(as_uuid=True), nullable=False),
        sa.Column("invoice_number", sa.String(50), nullable=False),
        sa.Column("invoice_date", sa.Date(), nullable=False),
        sa.Column("vendor_id", UUID(as_uuid=True), nullable=False),
        sa.Column("customer_id", UUID(as_uuid=True), nullable=False),
        sa.Column("bill_amount_excl_gst", sa.Numeric(14, 2), nullable=False),
        sa.Column("bill_amount_incl_tax", sa.Numeric(14, 2), nullable=True),
        sa.Column("amount_deducted", sa.Numeric(14, 2), server_default="0", nullable=False),
        sa.Column("tds_value", sa.Numeric(14, 2), server_default="0", nullable=False),
        sa.Column("due_date", sa.Date(), nullable=True),
        sa.Column("payment_clearing_date", sa.Date(), nullable=True),
        sa.Column("sap_clearing_document_no", sa.String(50), nullable=True),
        sa.Column("invoice_status", sa.String(20), server_default="Open", nullable=False),
        *_audit_columns(),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(["vendor_id"], ["vendors.id"]),
        sa.ForeignKeyConstraint(["customer_id"], ["customers.id"]),
    )
    op.create_index(
        "ix_invoice_headers_invoice_number",
        "invoice_headers",
        ["invoice_number"],
        unique=True,
    )
    op.create_index("ix_invoice_headers_vendor_id", "invoice_headers", ["vendor_id"])
    op.create_index("ix_invoice_headers_customer_id", "invoice_headers", ["customer_id"])

    op.create_table(
        "invoice_lines",
        sa.Column("id", UUID(as_uuid=True), nullable=False),
        sa.Column("invoice_header_id", UUID(as_uuid=True), nullable=False),
        sa.Column("product_detail_id", UUID(as_uuid=True), nullable=False),
        sa.Column("quantity", sa.Numeric(14, 3), nullable=True),
        sa.Column("line_amount", sa.Numeric(14, 2), nullable=True),
        sa.Column("vat_gst_amount", sa.Numeric(14, 2), nullable=True),
        *_audit_columns(),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(
            ["invoice_header_id"],
            ["invoice_headers.id"],
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(["product_detail_id"], ["product_master.id"]),
    )
    op.create_index(
        "ix_invoice_lines_invoice_header_id",
        "invoice_lines",
        ["invoice_header_id"],
    )
    op.create_index(
        "ix_invoice_lines_product_detail_id",
        "invoice_lines",
        ["product_detail_id"],
    )


def downgrade() -> None:
    # Drop in reverse dependency order.
    op.drop_table("invoice_lines")
    op.drop_table("invoice_headers")
    op.drop_table("vendor_customer_mappings")
    op.drop_table("agreements")
    op.drop_table("product_master")
    op.drop_table("customers")
    op.drop_table("vendors")

    op.drop_index("ix_users_entity_id", table_name="users")
    op.drop_constraint("fk_users_entity_id_entities", "users", type_="foreignkey")
    op.drop_column("users", "entity_id")

    op.drop_table("entities")
