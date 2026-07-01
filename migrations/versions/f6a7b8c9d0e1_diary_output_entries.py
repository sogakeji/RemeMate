"""allow diary output entries without word

Revision ID: f6a7b8c9d0e1
Revises: e5f6a7b8c9d0
Create Date: 2026-07-01
"""
from alembic import op


revision = 'f6a7b8c9d0e1'
down_revision = 'e5f6a7b8c9d0'
branch_labels = None
depends_on = None


def upgrade():
    op.execute("ALTER TABLE output_entries ALTER COLUMN word_id DROP NOT NULL;")


def downgrade():
    op.execute("DELETE FROM output_entries WHERE word_id IS NULL;")
    op.execute("ALTER TABLE output_entries ALTER COLUMN word_id SET NOT NULL;")
