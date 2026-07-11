"""add UI locale to user settings

Revision ID: c8d9e0f1a2b3
Revises: b7c8d9e0f1a2
"""
from alembic import op
import sqlalchemy as sa


revision = "c8d9e0f1a2b3"
down_revision = "b7c8d9e0f1a2"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column(
        "user_settings",
        sa.Column("ui_locale", sa.String(length=10), nullable=True),
    )


def downgrade():
    op.drop_column("user_settings", "ui_locale")
