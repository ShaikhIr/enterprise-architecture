"""widen_darwinbox_employee_text_columns

Revision ID: b2c3d4e5f6a7
Revises: f3a4b5c6d7e8
Create Date: 2026-07-23 17:20:00.000000

Darwinbox free-form values (addresses, proxy emails, long designations)
can exceed the original VARCHAR limits, causing StringDataRightTruncation
errors during sync. Widen those columns to TEXT so no Darwinbox value can
overflow them. employee_id and employee_status stay bounded (indexed key /
status enum).
"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "b2c3d4e5f6a7"
down_revision: str | None = "f3a4b5c6d7e8"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


# Columns to convert VARCHAR -> TEXT
_TEXT_COLUMNS = [
    "first_name",
    "middle_name",
    "last_name",
    "full_name",
    "company_email_id",
    "designation_title",
    "job_level",
    "role",
    "department",
    "business_unit",
    "division",
    "group_company",
    "catalyst_additional_department",
    "cost_center_id",
    "cost_center",
    "office_mobile_no",
    "extension_mobile_no",
    "personal_mobile_no",
    "current_address",
    "current_country",
    "current_location",
    "office_location",
    "custom_location",
    "office_state",
    "office_city",
    "direct_manager_employee_id",
    "direct_manager_name",
    "direct_manager_email",
    "territory_code",
    "territory_name",
    "bank_pan",
    "date_of_birth",
    "gender",
    "date_of_exit",
]


def upgrade() -> None:
    for col in _TEXT_COLUMNS:
        op.alter_column(
            "darwinbox_employees",
            col,
            type_=sa.Text(),
            existing_nullable=False,
        )


def downgrade() -> None:
    # Revert TEXT -> VARCHAR with the original lengths.
    varchar_lengths = {
        "first_name": 255,
        "middle_name": 255,
        "last_name": 255,
        "full_name": 512,
        "company_email_id": 255,
        "designation_title": 255,
        "job_level": 255,
        "role": 255,
        "department": 255,
        "business_unit": 255,
        "division": 255,
        "group_company": 255,
        "catalyst_additional_department": 255,
        "cost_center_id": 100,
        "cost_center": 255,
        "office_mobile_no": 50,
        "extension_mobile_no": 50,
        "personal_mobile_no": 50,
        "current_address": 512,
        "current_country": 255,
        "current_location": 255,
        "office_location": 255,
        "custom_location": 255,
        "office_state": 255,
        "office_city": 255,
        "direct_manager_employee_id": 50,
        "direct_manager_name": 255,
        "direct_manager_email": 255,
        "territory_code": 100,
        "territory_name": 255,
        "bank_pan": 50,
        "date_of_birth": 50,
        "gender": 50,
        "date_of_exit": 50,
    }
    for col, length in varchar_lengths.items():
        op.alter_column(
            "darwinbox_employees",
            col,
            type_=sa.String(length=length),
            existing_nullable=False,
        )
