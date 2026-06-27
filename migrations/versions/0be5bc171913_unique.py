"""unique

Revision ID: 0be5bc171913
Revises: b27062024cc0
Create Date: 2026-06-23 22:15:44.890027

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '0be5bc171913'
down_revision = 'b27062024cc0'
branch_labels = None
depends_on = None


def upgrade():
    # 邮箱大小写无关唯一（M5）。写入侧已 normalize_email() 小写化，这里加函数索引
    # 兜底任何漏归一化的写路径。原 users_email_key 保留无害。
    # IF NOT EXISTS 保证可重入（review 2026-06-23 M7）。
    op.execute("CREATE UNIQUE INDEX IF NOT EXISTS uq_users_email_lower ON users (lower(email));")


def downgrade():
    op.execute("DROP INDEX IF EXISTS uq_users_email_lower;")
