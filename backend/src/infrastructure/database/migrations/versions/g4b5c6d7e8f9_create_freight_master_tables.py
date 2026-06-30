"""Create freight master tables (country, city, air, sea, sea_cbm, vehicle_type, local).

Revision ID: g4b5c6d7e8f9
Revises: f3a4b5c6d7e8
Create Date: 2026-06-29
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID

revision = "g4b5c6d7e8f9"
down_revision = "f3a4b5c6d7e8"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Country Master
    op.create_table(
        "country_master",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("country_name", sa.String(200), nullable=False, index=True),
        sa.Column("country_code", sa.String(10), unique=True, nullable=False, index=True),
        sa.Column("is_active", sa.Boolean, server_default=sa.text("true"), nullable=False),
        sa.Column("created_by", sa.String(255), server_default="system", nullable=False),
        sa.Column("created_date", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("modified_by", sa.String(255), server_default="system", nullable=False),
        sa.Column("modified_date", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )

    # City Master
    op.create_table(
        "city_master",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("city_name", sa.String(200), nullable=False, index=True),
        sa.Column("country_id", UUID(as_uuid=True), sa.ForeignKey("country_master.id"), nullable=True),
        sa.Column("is_active", sa.Boolean, server_default=sa.text("true"), nullable=False),
        sa.Column("created_by", sa.String(255), server_default="system", nullable=False),
        sa.Column("created_date", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("modified_by", sa.String(255), server_default="system", nullable=False),
        sa.Column("modified_date", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )

    # Vehicle Type Master (needed before local_master for FK)
    op.create_table(
        "vehicle_type_master",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("from_no_of_pallet_or_box", sa.Integer, nullable=False),
        sa.Column("to_no_of_pallet_or_box", sa.Integer, nullable=False),
        sa.Column("vehicle_type", sa.String(100), nullable=False, index=True),
        sa.Column("is_active", sa.Boolean, server_default=sa.text("true"), nullable=False),
        sa.Column("created_by", sa.String(255), server_default="system", nullable=False),
        sa.Column("created_date", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("modified_by", sa.String(255), server_default="system", nullable=False),
        sa.Column("modified_date", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )

    # Air Master
    op.create_table(
        "air_master",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("to_country_id", UUID(as_uuid=True), sa.ForeignKey("country_master.id"), nullable=False),
        sa.Column("product_type", sa.String(100), nullable=True),
        sa.Column("min_slab", sa.Integer, nullable=False),
        sa.Column("max_slab", sa.Integer, nullable=False),
        sa.Column("slab_name", sa.String(50), nullable=True),
        sa.Column("is_active", sa.Boolean, server_default=sa.text("true"), nullable=False),
        sa.Column("created_by", sa.String(255), server_default="system", nullable=False),
        sa.Column("created_date", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("modified_by", sa.String(255), server_default="system", nullable=False),
        sa.Column("modified_date", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )

    # Air Master Rate
    op.create_table(
        "air_master_rate",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("air_master_id", UUID(as_uuid=True), sa.ForeignKey("air_master.id"), nullable=False),
        sa.Column("rate", sa.Numeric(12, 4), nullable=False),
        sa.Column("valid_from", sa.DateTime(timezone=True), nullable=False),
        sa.Column("valid_till", sa.DateTime(timezone=True), nullable=False),
        sa.Column("is_active", sa.Boolean, server_default=sa.text("true"), nullable=False),
        sa.Column("created_by", sa.String(255), server_default="system", nullable=False),
        sa.Column("created_date", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("modified_by", sa.String(255), server_default="system", nullable=False),
        sa.Column("modified_date", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )

    # Sea Master
    op.create_table(
        "sea_master",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("to_country_id", UUID(as_uuid=True), sa.ForeignKey("country_master.id"), nullable=False),
        sa.Column("product_type", sa.String(100), nullable=True),
        sa.Column("slab_name", sa.String(100), nullable=True),
        sa.Column("currency", sa.String(10), nullable=True),
        sa.Column("is_active", sa.Boolean, server_default=sa.text("true"), nullable=False),
        sa.Column("created_by", sa.String(255), server_default="system", nullable=False),
        sa.Column("created_date", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("modified_by", sa.String(255), server_default="system", nullable=False),
        sa.Column("modified_date", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )

    # Sea Master Rate
    op.create_table(
        "sea_master_rate",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("sea_master_id", UUID(as_uuid=True), sa.ForeignKey("sea_master.id"), nullable=False),
        sa.Column("rate", sa.Numeric(12, 4), nullable=False),
        sa.Column("valid_from", sa.DateTime(timezone=True), nullable=False),
        sa.Column("valid_till", sa.DateTime(timezone=True), nullable=False),
        sa.Column("is_active", sa.Boolean, server_default=sa.text("true"), nullable=False),
        sa.Column("created_by", sa.String(255), server_default="system", nullable=False),
        sa.Column("created_date", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("modified_by", sa.String(255), server_default="system", nullable=False),
        sa.Column("modified_date", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )

    # Sea CBM Master
    op.create_table(
        "sea_cbm_master",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("slab_name", sa.String(100), nullable=True),
        sa.Column("from_cbm", sa.Integer, nullable=False),
        sa.Column("to_cbm", sa.Integer, nullable=False),
        sa.Column("type", sa.String(100), nullable=True),
        sa.Column("total_count", sa.Integer, nullable=True),
        sa.Column("is_active", sa.Boolean, server_default=sa.text("true"), nullable=False),
        sa.Column("created_by", sa.String(255), server_default="system", nullable=False),
        sa.Column("created_date", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("modified_by", sa.String(255), server_default="system", nullable=False),
        sa.Column("modified_date", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )

    # Local Master
    op.create_table(
        "local_master",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("from_city_id", UUID(as_uuid=True), sa.ForeignKey("city_master.id"), nullable=False),
        sa.Column("to_city_id", UUID(as_uuid=True), sa.ForeignKey("city_master.id"), nullable=False),
        sa.Column("product_type", sa.String(100), nullable=True),
        sa.Column("vehicle_type_id", UUID(as_uuid=True), sa.ForeignKey("vehicle_type_master.id"), nullable=True),
        sa.Column("min_slab", sa.String(50), nullable=True),
        sa.Column("max_slab", sa.String(50), nullable=True),
        sa.Column("is_active", sa.Boolean, server_default=sa.text("true"), nullable=False),
        sa.Column("created_by", sa.String(255), server_default="system", nullable=False),
        sa.Column("created_date", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("modified_by", sa.String(255), server_default="system", nullable=False),
        sa.Column("modified_date", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )

    # Local Master Rate
    op.create_table(
        "local_master_rate",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("local_master_id", UUID(as_uuid=True), sa.ForeignKey("local_master.id"), nullable=False),
        sa.Column("rate", sa.Numeric(12, 4), nullable=False),
        sa.Column("valid_from", sa.DateTime(timezone=True), nullable=False),
        sa.Column("valid_till", sa.DateTime(timezone=True), nullable=False),
        sa.Column("is_active", sa.Boolean, server_default=sa.text("true"), nullable=False),
        sa.Column("created_by", sa.String(255), server_default="system", nullable=False),
        sa.Column("created_date", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("modified_by", sa.String(255), server_default="system", nullable=False),
        sa.Column("modified_date", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )


def downgrade() -> None:
    op.drop_table("local_master_rate")
    op.drop_table("local_master")
    op.drop_table("sea_cbm_master")
    op.drop_table("sea_master_rate")
    op.drop_table("sea_master")
    op.drop_table("air_master_rate")
    op.drop_table("air_master")
    op.drop_table("vehicle_type_master")
    op.drop_table("city_master")
    op.drop_table("country_master")
