"""merge_freight_master_branches

Revision ID: 92ff5465bc69
Revises: a1b2c3d4e5f6, g4b5c6d7e8f9
Create Date: 2026-06-30 18:13:04.255923

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '92ff5465bc69'
down_revision: Union[str, None] = ('a1b2c3d4e5f6', 'g4b5c6d7e8f9')
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
