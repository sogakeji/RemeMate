"""add feedback language preference

Revision ID: a7b8c9d0e1f2
Revises: f6a7b8c9d0e1
Create Date: 2026-07-01
"""
from alembic import op
import sqlalchemy as sa


revision = 'a7b8c9d0e1f2'
down_revision = 'f6a7b8c9d0e1'
branch_labels = None
depends_on = None


def upgrade():
    op.add_column(
        'user_settings',
        sa.Column('feedback_language', sa.String(length=10),
                  nullable=False, server_default='zh'),
    )
    op.alter_column('user_settings', 'feedback_language', server_default=None)


def downgrade():
    op.drop_column('user_settings', 'feedback_language')
