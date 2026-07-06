"""move_entity_id_to_user_details

Adds entity_id FK column to user_details table so that the entity assignment
lives alongside the rest of the employee profile data rather than on the users
table.  The users.entity_id column is kept for now (existing data) but the
application layer now reads/writes via user_details.

Revision ID: c270ad3ed755
Revises: f3a4b5c6d7e8
Create Date: 2026-07-01 16:36:24.558679
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = 'c270ad3ed755'
down_revision: Union[str, None] = 'f3a4b5c6d7e8'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Add entity_id column to user_details
    op.add_column(
        'user_details',
        sa.Column('entity_id', postgresql.UUID(as_uuid=True), nullable=True),
    )
    op.create_index('ix_user_details_entity_id', 'user_details', ['entity_id'])
    op.create_foreign_key(
        'fk_user_details_entity_id_entities',
        'user_details',
        'entities',
        ['entity_id'],
        ['id'],
        ondelete='SET NULL',
    )

    # Migrate existing entity_id values from users -> user_details
    op.execute("""
        UPDATE user_details ud
        SET entity_id = u.entity_id
        FROM users u
        WHERE ud.user_id = u.id
          AND u.entity_id IS NOT NULL
          AND ud.entity_id IS NULL
    """)


def downgrade() -> None:
    op.drop_constraint('fk_user_details_entity_id_entities', 'user_details', type_='foreignkey')
    op.drop_index('ix_user_details_entity_id', table_name='user_details')
    op.drop_column('user_details', 'entity_id')
