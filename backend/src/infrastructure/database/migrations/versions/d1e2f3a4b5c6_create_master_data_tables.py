"""create_master_data_tables

Creates the compliance master data hierarchy:
countries -> states -> categories_of_law -> legislations -> rules
plus the independent task_types lookup.

Foreign keys use ON DELETE RESTRICT so reference data cannot be orphaned;
records are retired via `is_active` instead.

Revision ID: d1e2f3a4b5c6
Revises: b2c3d4e5f6a7
Create Date: 2026-07-30 10:00:00.000000

"""
from collections.abc import Sequence
from typing import Any

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "d1e2f3a4b5c6"
down_revision: str | None = "b2c3d4e5f6a7"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _audit_columns() -> list[sa.Column[Any]]:
    """Audit columns shared by every master table (mirrors AuditMixin)."""
    return [
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("created_by", sa.String(length=255), nullable=False),
        sa.Column("created_date", sa.DateTime(timezone=True), nullable=False),
        sa.Column("modified_by", sa.String(length=255), nullable=False),
        sa.Column("modified_date", sa.DateTime(timezone=True), nullable=False),
    ]


def upgrade() -> None:
    # ─── countries ───
    op.create_table(
        "countries",
        sa.Column("code", sa.String(length=10), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("iso3_code", sa.String(length=10), nullable=True),
        sa.Column("dial_code", sa.String(length=10), nullable=True),
        sa.Column("currency_code", sa.String(length=10), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False),
        *_audit_columns(),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_countries_code"), "countries", ["code"], unique=True)
    op.create_index(op.f("ix_countries_name"), "countries", ["name"], unique=True)

    # ─── states ───
    op.create_table(
        "states",
        sa.Column("code", sa.String(length=20), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("country_id", sa.UUID(), nullable=False),
        sa.Column("is_union_territory", sa.Boolean(), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False),
        *_audit_columns(),
        sa.ForeignKeyConstraint(["country_id"], ["countries.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("country_id", "name", name="uq_states_country_name"),
    )
    op.create_index(op.f("ix_states_code"), "states", ["code"], unique=True)
    op.create_index(op.f("ix_states_name"), "states", ["name"], unique=False)
    op.create_index(
        op.f("ix_states_country_id"), "states", ["country_id"], unique=False
    )

    # ─── categories_of_law ───
    op.create_table(
        "categories_of_law",
        sa.Column("code", sa.String(length=50), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("state_id", sa.UUID(), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False),
        *_audit_columns(),
        sa.ForeignKeyConstraint(["state_id"], ["states.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("state_id", "name", name="uq_categories_of_law_state_name"),
    )
    op.create_index(
        op.f("ix_categories_of_law_code"), "categories_of_law", ["code"], unique=True
    )
    op.create_index(
        op.f("ix_categories_of_law_name"), "categories_of_law", ["name"], unique=False
    )
    op.create_index(
        op.f("ix_categories_of_law_state_id"),
        "categories_of_law",
        ["state_id"],
        unique=False,
    )

    # ─── legislations ───
    op.create_table(
        "legislations",
        sa.Column("code", sa.String(length=50), nullable=False),
        sa.Column("name", sa.String(length=500), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("category_of_law_id", sa.UUID(), nullable=False),
        sa.Column("state_id", sa.UUID(), nullable=True),
        sa.Column("country_id", sa.UUID(), nullable=False),
        sa.Column("legislation_number", sa.String(length=100), nullable=True),
        sa.Column("effective_date", sa.Date(), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False),
        *_audit_columns(),
        sa.ForeignKeyConstraint(
            ["category_of_law_id"], ["categories_of_law.id"], ondelete="RESTRICT"
        ),
        sa.ForeignKeyConstraint(["state_id"], ["states.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["country_id"], ["countries.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_legislations_code"), "legislations", ["code"], unique=True)
    op.create_index(op.f("ix_legislations_name"), "legislations", ["name"], unique=False)
    op.create_index(
        op.f("ix_legislations_category_of_law_id"),
        "legislations",
        ["category_of_law_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_legislations_state_id"), "legislations", ["state_id"], unique=False
    )
    op.create_index(
        op.f("ix_legislations_country_id"), "legislations", ["country_id"], unique=False
    )

    # ─── rules ───
    op.create_table(
        "rules",
        sa.Column("code", sa.String(length=50), nullable=False),
        sa.Column("name", sa.String(length=500), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("legislation_id", sa.UUID(), nullable=False),
        sa.Column("state_id", sa.UUID(), nullable=True),
        sa.Column("country_id", sa.UUID(), nullable=False),
        sa.Column("rule_number", sa.String(length=100), nullable=True),
        sa.Column("effective_date", sa.Date(), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False),
        *_audit_columns(),
        sa.ForeignKeyConstraint(
            ["legislation_id"], ["legislations.id"], ondelete="RESTRICT"
        ),
        sa.ForeignKeyConstraint(["state_id"], ["states.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["country_id"], ["countries.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_rules_code"), "rules", ["code"], unique=True)
    op.create_index(op.f("ix_rules_name"), "rules", ["name"], unique=False)
    op.create_index(
        op.f("ix_rules_legislation_id"), "rules", ["legislation_id"], unique=False
    )
    op.create_index(op.f("ix_rules_state_id"), "rules", ["state_id"], unique=False)
    op.create_index(op.f("ix_rules_country_id"), "rules", ["country_id"], unique=False)

    # ─── task_types ───
    op.create_table(
        "task_types",
        sa.Column("code", sa.String(length=50), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False),
        *_audit_columns(),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_task_types_code"), "task_types", ["code"], unique=True)
    op.create_index(op.f("ix_task_types_name"), "task_types", ["name"], unique=True)


def downgrade() -> None:
    op.drop_index(op.f("ix_task_types_name"), table_name="task_types")
    op.drop_index(op.f("ix_task_types_code"), table_name="task_types")
    op.drop_table("task_types")

    op.drop_index(op.f("ix_rules_country_id"), table_name="rules")
    op.drop_index(op.f("ix_rules_state_id"), table_name="rules")
    op.drop_index(op.f("ix_rules_legislation_id"), table_name="rules")
    op.drop_index(op.f("ix_rules_name"), table_name="rules")
    op.drop_index(op.f("ix_rules_code"), table_name="rules")
    op.drop_table("rules")

    op.drop_index(op.f("ix_legislations_country_id"), table_name="legislations")
    op.drop_index(op.f("ix_legislations_state_id"), table_name="legislations")
    op.drop_index(
        op.f("ix_legislations_category_of_law_id"), table_name="legislations"
    )
    op.drop_index(op.f("ix_legislations_name"), table_name="legislations")
    op.drop_index(op.f("ix_legislations_code"), table_name="legislations")
    op.drop_table("legislations")

    op.drop_index(op.f("ix_categories_of_law_state_id"), table_name="categories_of_law")
    op.drop_index(op.f("ix_categories_of_law_name"), table_name="categories_of_law")
    op.drop_index(op.f("ix_categories_of_law_code"), table_name="categories_of_law")
    op.drop_table("categories_of_law")

    op.drop_index(op.f("ix_states_country_id"), table_name="states")
    op.drop_index(op.f("ix_states_name"), table_name="states")
    op.drop_index(op.f("ix_states_code"), table_name="states")
    op.drop_table("states")

    op.drop_index(op.f("ix_countries_name"), table_name="countries")
    op.drop_index(op.f("ix_countries_code"), table_name="countries")
    op.drop_table("countries")
