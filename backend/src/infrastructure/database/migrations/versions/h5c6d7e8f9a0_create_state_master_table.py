"""Create state_master table.

Revision ID: h5c6d7e8f9a0
Revises: g4b5c6d7e8f9
Create Date: 2026-06-25 16:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = "h5c6d7e8f9a0"
down_revision: Union[str, None] = "g4b5c6d7e8f9"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "state_master",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("country_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("country_master.id", ondelete="CASCADE"), nullable=False, index=True),
        sa.Column("language_key", sa.String(10), nullable=False),
        sa.Column("state_name", sa.String(100), unique=True, nullable=False, index=True),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("created_by", sa.String(255), nullable=False, server_default="system"),
        sa.Column("created_date", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("modified_by", sa.String(255), nullable=False, server_default="system"),
        sa.Column("modified_date", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )


def downgrade() -> None:
    op.drop_table("state_master")
