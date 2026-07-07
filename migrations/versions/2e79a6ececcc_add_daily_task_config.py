"""add daily_task_config

Revision ID: 2e79a6ececcc
Revises: e76e0424
Create Date: 2026-07-07 12:56:41.277149

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = '2e79a6ececcc'
down_revision = 'e76e0424'
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table('user_settings', schema=None) as batch_op:
        batch_op.add_column(
            sa.Column('daily_task_config',
                      postgresql.JSONB(astext_type=sa.Text()),
                      nullable=True))


def downgrade():
    with op.batch_alter_table('user_settings', schema=None) as batch_op:
        batch_op.drop_column('daily_task_config')