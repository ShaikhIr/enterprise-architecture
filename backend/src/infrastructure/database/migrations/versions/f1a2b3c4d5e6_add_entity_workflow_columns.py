"""add entity workflow columns

Adds entity-based approval workflow support:
- invoice_headers.entity_id      → FK to entities
- entities.workflow_definition_id → FK to workflow_definitions
- claim_headers.entity_id        → FK to entities
- approval_matrices.workflow_definition_id → FK to workflow_definitions

All operations are guarded with IF NOT EXISTS so the migration is safe to
re-run and consistent with columns already provisioned in running environments.

Revision ID: f1a2b3c4d5e6
Revises: i6d7e8f9a0b1
Create Date: 2026-07-14
"""

from alembic import op

# revision identifiers
revision = "f1a2b3c4d5e6"
down_revision = "i6d7e8f9a0b1"
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Add entity/workflow FK columns (idempotent)."""
    # invoice_headers.entity_id
    op.execute("""
        ALTER TABLE invoice_headers
        ADD COLUMN IF NOT EXISTS entity_id UUID REFERENCES entities(id)
    """)
    op.execute("""
        CREATE INDEX IF NOT EXISTS ix_invoice_headers_entity_id
        ON invoice_headers(entity_id)
    """)

    # entities.workflow_definition_id
    op.execute("""
        ALTER TABLE entities
        ADD COLUMN IF NOT EXISTS workflow_definition_id UUID
        REFERENCES workflow_definitions(id)
    """)

    # claim_headers.entity_id
    op.execute("""
        ALTER TABLE claim_headers
        ADD COLUMN IF NOT EXISTS entity_id UUID REFERENCES entities(id)
    """)
    op.execute("""
        CREATE INDEX IF NOT EXISTS ix_claim_headers_entity_id
        ON claim_headers(entity_id)
    """)

    # approval_matrices.workflow_definition_id
    op.execute("""
        ALTER TABLE approval_matrices
        ADD COLUMN IF NOT EXISTS workflow_definition_id UUID
        REFERENCES workflow_definitions(id)
    """)
    op.execute("""
        CREATE INDEX IF NOT EXISTS ix_approval_matrices_workflow_definition_id
        ON approval_matrices(workflow_definition_id)
    """)


def downgrade() -> None:
    """Drop the entity/workflow FK columns."""
    op.execute("DROP INDEX IF EXISTS ix_approval_matrices_workflow_definition_id")
    op.execute("ALTER TABLE approval_matrices DROP COLUMN IF EXISTS workflow_definition_id")
    op.execute("DROP INDEX IF EXISTS ix_claim_headers_entity_id")
    op.execute("ALTER TABLE claim_headers DROP COLUMN IF EXISTS entity_id")
    op.execute("ALTER TABLE entities DROP COLUMN IF EXISTS workflow_definition_id")
    op.execute("DROP INDEX IF EXISTS ix_invoice_headers_entity_id")
    op.execute("ALTER TABLE invoice_headers DROP COLUMN IF EXISTS entity_id")
