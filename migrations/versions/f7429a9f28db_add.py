"""add

Revision ID: f7429a9f28db
Revises: fe681cf5d5b3
Create Date: 2026-06-24 06:50:51.209985

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'f7429a9f28db'
down_revision = 'fe681cf5d5b3'
branch_labels = None
depends_on = None


def upgrade():
    # IF NOT EXISTS 保证可重入（review 2026-06-23 M7）。
    op.execute(
        "ALTER TABLE user_quota "
        "ADD COLUMN IF NOT EXISTS imports_today integer NOT NULL DEFAULT 0;"
    )


def downgrade():
    op.execute("ALTER TABLE user_quota DROP COLUMN IF EXISTS imports_today;")
