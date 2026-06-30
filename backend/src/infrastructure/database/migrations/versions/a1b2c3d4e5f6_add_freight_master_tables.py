"""add_freight_master_tables

Revision ID: a1b2c3d4e5f6
Revises: 9ec0ed7e2b96
Create Date: 2026-06-29 15:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'a1b2c3d4e5f6'
down_revision: Union[str, None] = '9ec0ed7e2b96'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table('currency_conversion_rate_master',
        sa.Column('exrt', sa.String(length=50), nullable=True),
        sa.Column('from_currency', sa.String(length=10), nullable=False),
        sa.Column('to_currency', sa.String(length=10), nullable=False),
        sa.Column('valid_from', sa.DateTime(timezone=True), nullable=True),
        sa.Column('exchange_rate', sa.Numeric(precision=12, scale=6), nullable=True),
        sa.Column('ratio_from', sa.Integer(), nullable=True),
        sa.Column('ratio_to', sa.Integer(), nullable=True),
        sa.Column('is_active', sa.Boolean(), nullable=False),
        sa.Column('id', sa.UUID(), nullable=False),
        sa.Column('created_by', sa.String(length=255), nullable=False),
        sa.Column('created_date', sa.DateTime(timezone=True), nullable=False),
        sa.Column('modified_by', sa.String(length=255), nullable=False),
        sa.Column('modified_date', sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index('ix_currency_conversion_from', 'currency_conversion_rate_master', ['from_currency'])
    op.create_index('ix_currency_conversion_to', 'currency_conversion_rate_master', ['to_currency'])

    op.create_table('container_master',
        sa.Column('container_type', sa.String(length=100), nullable=False),
        sa.Column('is_active', sa.Boolean(), nullable=False),
        sa.Column('id', sa.UUID(), nullable=False),
        sa.Column('created_by', sa.String(length=255), nullable=False),
        sa.Column('created_date', sa.DateTime(timezone=True), nullable=False),
        sa.Column('modified_by', sa.String(length=255), nullable=False),
        sa.Column('modified_date', sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index('ix_container_master_type', 'container_master', ['container_type'], unique=True)

    op.create_table('transit_day_master',
        sa.Column('country_name', sa.String(length=100), nullable=False),
        sa.Column('country_code', sa.String(length=10), nullable=True),
        sa.Column('customer_clearance', sa.Integer(), nullable=True),
        sa.Column('transit_days_for_air', sa.Integer(), nullable=True),
        sa.Column('container_load_for_sea', sa.Integer(), nullable=True),
        sa.Column('test_days', sa.Integer(), nullable=True),
        sa.Column('is_active', sa.Boolean(), nullable=False),
        sa.Column('id', sa.UUID(), nullable=False),
        sa.Column('created_by', sa.String(length=255), nullable=False),
        sa.Column('created_date', sa.DateTime(timezone=True), nullable=False),
        sa.Column('modified_by', sa.String(length=255), nullable=False),
        sa.Column('modified_date', sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index('ix_transit_day_country', 'transit_day_master', ['country_name'])

    op.create_table('fixed_charges_master',
        sa.Column('mode_of_shipment', sa.String(length=100), nullable=True),
        sa.Column('pallet_name', sa.String(length=100), nullable=True),
        sa.Column('document_charges', sa.Numeric(precision=12, scale=4), nullable=True),
        sa.Column('shrink_wrap_charges', sa.Numeric(precision=12, scale=4), nullable=True),
        sa.Column('unloading_charges', sa.Numeric(precision=12, scale=4), nullable=True),
        sa.Column('pallet_charges', sa.Numeric(precision=12, scale=4), nullable=True),
        sa.Column('data_logger_charges', sa.Numeric(precision=12, scale=4), nullable=True),
        sa.Column('blanket_charges', sa.Numeric(precision=12, scale=4), nullable=True),
        sa.Column('is_active', sa.Boolean(), nullable=False),
        sa.Column('id', sa.UUID(), nullable=False),
        sa.Column('created_by', sa.String(length=255), nullable=False),
        sa.Column('created_date', sa.DateTime(timezone=True), nullable=False),
        sa.Column('modified_by', sa.String(length=255), nullable=False),
        sa.Column('modified_date', sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint('id')
    )


def downgrade() -> None:
    op.drop_table('fixed_charges_master')
    op.drop_index('ix_transit_day_country', table_name='transit_day_master')
    op.drop_table('transit_day_master')
    op.drop_index('ix_container_master_type', table_name='container_master')
    op.drop_table('container_master')
    op.drop_index('ix_currency_conversion_to', table_name='currency_conversion_rate_master')
    op.drop_index('ix_currency_conversion_from', table_name='currency_conversion_rate_master')
    op.drop_table('currency_conversion_rate_master')
