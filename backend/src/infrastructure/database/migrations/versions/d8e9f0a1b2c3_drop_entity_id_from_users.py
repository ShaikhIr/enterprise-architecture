"""drop_entity_id_from_users

Removes the entity_id FK column from the users table.
Entity assignment now lives exclusively in user_details.entity_id.

Revision ID: d8e9f0a1b2c3
Revises: c270ad3ed755
Create Date: 2026-07-01 17:00:00.000000
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = 'd8e9f0a1b2c3'
down_revision: Union[str, None] = 'c270ad3ed755'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.drop_index('ix_users_entity_id', table_name='users', if_exists=True)
    op.drop_constraint('fk_users_entity_id_entities', 'users', type_='foreignkey')
    op.drop_column('users', 'entity_id')


def downgrade() -> None:
    op.add_column(
        'users',
        sa.Column('entity_id', postgresql.UUID(as_uuid=True), nullable=True),
    )
    op.create_foreign_key(
        'fk_users_entity_id_entities',
        'users', 'entities',
        ['entity_id'], ['id'],
        ondelete='SET NULL',
    )
    op.create_index('ix_users_entity_id', 'users', ['entity_id'])
