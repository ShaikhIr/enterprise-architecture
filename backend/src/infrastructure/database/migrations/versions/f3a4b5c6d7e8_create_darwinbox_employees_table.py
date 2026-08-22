"""create_darwinbox_employees_table

Revision ID: f3a4b5c6d7e8
Revises: e2f3a4b5c6d7
Create Date: 2026-07-23 10:00:00.000000

"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = 'f3a4b5c6d7e8'
down_revision: str | None = 'c9d4e2f5a1b7'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        'darwinbox_employees',
        sa.Column('employee_id', sa.String(length=50), nullable=False),
        sa.Column('first_name', sa.String(length=255), nullable=False),
        sa.Column('middle_name', sa.String(length=255), nullable=False),
        sa.Column('last_name', sa.String(length=255), nullable=False),
        sa.Column('full_name', sa.String(length=512), nullable=False),
        sa.Column('company_email_id', sa.String(length=255), nullable=False),
        sa.Column('employee_status', sa.String(length=50), nullable=False),
        sa.Column('designation_title', sa.String(length=255), nullable=False),
        sa.Column('job_level', sa.String(length=255), nullable=False),
        sa.Column('role', sa.String(length=255), nullable=False),
        sa.Column('department', sa.String(length=255), nullable=False),
        sa.Column('business_unit', sa.String(length=255), nullable=False),
        sa.Column('division', sa.String(length=255), nullable=False),
        sa.Column('group_company', sa.String(length=255), nullable=False),
        sa.Column('catalyst_additional_department', sa.String(length=255), nullable=False),
        sa.Column('cost_center_id', sa.String(length=100), nullable=False),
        sa.Column('cost_center', sa.String(length=255), nullable=False),
        sa.Column('office_mobile_no', sa.String(length=50), nullable=False),
        sa.Column('extension_mobile_no', sa.String(length=50), nullable=False),
        sa.Column('personal_mobile_no', sa.String(length=50), nullable=False),
        sa.Column('current_address', sa.String(length=512), nullable=False),
        sa.Column('current_country', sa.String(length=255), nullable=False),
        sa.Column('current_location', sa.String(length=255), nullable=False),
        sa.Column('office_location', sa.String(length=255), nullable=False),
        sa.Column('custom_location', sa.String(length=255), nullable=False),
        sa.Column('office_state', sa.String(length=255), nullable=False),
        sa.Column('office_city', sa.String(length=255), nullable=False),
        sa.Column('direct_manager_employee_id', sa.String(length=50), nullable=False),
        sa.Column('direct_manager_name', sa.String(length=255), nullable=False),
        sa.Column('direct_manager_email', sa.String(length=255), nullable=False),
        sa.Column('territory_code', sa.String(length=100), nullable=False),
        sa.Column('territory_name', sa.String(length=255), nullable=False),
        sa.Column('bank_pan', sa.String(length=50), nullable=False),
        sa.Column('date_of_birth', sa.String(length=50), nullable=False),
        sa.Column('gender', sa.String(length=50), nullable=False),
        sa.Column('date_of_exit', sa.String(length=50), nullable=False),
        sa.Column('id', sa.UUID(), nullable=False),
        sa.Column('created_by', sa.String(length=255), nullable=False),
        sa.Column('created_date', sa.DateTime(timezone=True), nullable=False),
        sa.Column('modified_by', sa.String(length=255), nullable=False),
        sa.Column('modified_date', sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('employee_id'),
    )
    op.create_index(op.f('ix_darwinbox_employees_employee_id'), 'darwinbox_employees', ['employee_id'], unique=True)
    op.create_index(op.f('ix_darwinbox_employees_company_email_id'), 'darwinbox_employees', ['company_email_id'], unique=False)
    op.create_index(op.f('ix_darwinbox_employees_employee_status'), 'darwinbox_employees', ['employee_status'], unique=False)


def downgrade() -> None:
    op.drop_index(op.f('ix_darwinbox_employees_employee_status'), table_name='darwinbox_employees')
    op.drop_index(op.f('ix_darwinbox_employees_company_email_id'), table_name='darwinbox_employees')
    op.drop_index(op.f('ix_darwinbox_employees_employee_id'), table_name='darwinbox_employees')
    op.drop_table('darwinbox_employees')
