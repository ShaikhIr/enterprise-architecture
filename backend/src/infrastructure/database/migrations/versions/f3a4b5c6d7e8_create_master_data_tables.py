"""Create master data tables (product_type, pack_size, type_of_pallet).

Revision ID: f3a4b5c6d7e8
Revises: e2f3a4b5c6d7
Create Date: 2026-06-26
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID

revision = "f3a4b5c6d7e8"
down_revision = "e2f3a4b5c6d7"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Product Type Master
    op.create_table(
        "product_type_master",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("product_type_name", sa.String(100), unique=True, nullable=False, index=True),
        sa.Column("is_active", sa.Boolean, server_default=sa.text("true"), nullable=False),
        sa.Column("created_by", sa.String(255), server_default="system", nullable=False),
        sa.Column("created_date", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("modified_by", sa.String(255), server_default="system", nullable=False),
        sa.Column("modified_date", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )

    # Pack Style Master
    op.create_table(
        "pack_style_master",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("pack_style", sa.String(100), unique=True, nullable=False, index=True),
        sa.Column("is_active", sa.Boolean, server_default=sa.text("true"), nullable=False),
        sa.Column("created_by", sa.String(255), server_default="system", nullable=False),
        sa.Column("created_date", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("modified_by", sa.String(255), server_default="system", nullable=False),
        sa.Column("modified_date", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )

    # Type of Pallet Master
    op.create_table(
        "type_of_pallet_master",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("name", sa.String(100), unique=True, nullable=False, index=True),
        sa.Column("length", sa.Integer, nullable=True),
        sa.Column("width", sa.Integer, nullable=True),
        sa.Column("height", sa.Integer, nullable=True),
        sa.Column("gross_weight_per_pack_type", sa.Integer, nullable=True),
        sa.Column("volumetric_weight", sa.Integer, nullable=True),
        sa.Column("is_active", sa.Boolean, server_default=sa.text("true"), nullable=False),
        sa.Column("created_by", sa.String(255), server_default="system", nullable=False),
        sa.Column("created_date", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("modified_by", sa.String(255), server_default="system", nullable=False),
        sa.Column("modified_date", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )


def downgrade() -> None:
    op.drop_table("type_of_pallet_master")
    op.drop_table("pack_style_master")
    op.drop_table("product_type_master")
