"""add_master_tables_brand_dosage_shipment_therapeutic

Revision ID: 9ec0ed7e2b96
Revises: e2f3a4b5c6d7
Create Date: 2026-06-26 15:30:40.459417

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '9ec0ed7e2b96'
down_revision: Union[str, None] = 'e2f3a4b5c6d7'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table('brand_master',
        sa.Column('brand_name', sa.String(length=100), nullable=False),
        sa.Column('is_active', sa.Boolean(), nullable=False),
        sa.Column('id', sa.UUID(), nullable=False),
        sa.Column('created_by', sa.String(length=255), nullable=False),
        sa.Column('created_date', sa.DateTime(timezone=True), nullable=False),
        sa.Column('modified_by', sa.String(length=255), nullable=False),
        sa.Column('modified_date', sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_brand_master_brand_name'), 'brand_master', ['brand_name'], unique=True)

    op.create_table('dosage_master',
        sa.Column('dosage', sa.String(length=100), nullable=False),
        sa.Column('is_active', sa.Boolean(), nullable=False),
        sa.Column('id', sa.UUID(), nullable=False),
        sa.Column('created_by', sa.String(length=255), nullable=False),
        sa.Column('created_date', sa.DateTime(timezone=True), nullable=False),
        sa.Column('modified_by', sa.String(length=255), nullable=False),
        sa.Column('modified_date', sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_dosage_master_dosage'), 'dosage_master', ['dosage'], unique=True)

    op.create_table('mode_of_shipment_master',
        sa.Column('mode_name', sa.String(length=100), nullable=False),
        sa.Column('is_active', sa.Boolean(), nullable=False),
        sa.Column('id', sa.UUID(), nullable=False),
        sa.Column('created_by', sa.String(length=255), nullable=False),
        sa.Column('created_date', sa.DateTime(timezone=True), nullable=False),
        sa.Column('modified_by', sa.String(length=255), nullable=False),
        sa.Column('modified_date', sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_mode_of_shipment_master_mode_name'), 'mode_of_shipment_master', ['mode_name'], unique=True)

    op.create_table('therapeutic_category_master',
        sa.Column('therapeutic_category_name', sa.String(length=100), nullable=False),
        sa.Column('is_active', sa.Boolean(), nullable=False),
        sa.Column('id', sa.UUID(), nullable=False),
        sa.Column('created_by', sa.String(length=255), nullable=False),
        sa.Column('created_date', sa.DateTime(timezone=True), nullable=False),
        sa.Column('modified_by', sa.String(length=255), nullable=False),
        sa.Column('modified_date', sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_therapeutic_category_master_therapeutic_category_name'), 'therapeutic_category_master', ['therapeutic_category_name'], unique=True)


def downgrade() -> None:
    op.drop_index(op.f('ix_therapeutic_category_master_therapeutic_category_name'), table_name='therapeutic_category_master')
    op.drop_table('therapeutic_category_master')
    op.drop_index(op.f('ix_mode_of_shipment_master_mode_name'), table_name='mode_of_shipment_master')
    op.drop_table('mode_of_shipment_master')
    op.drop_index(op.f('ix_dosage_master_dosage'), table_name='dosage_master')
    op.drop_table('dosage_master')
    op.drop_index(op.f('ix_brand_master_brand_name'), table_name='brand_master')
    op.drop_table('brand_master')
