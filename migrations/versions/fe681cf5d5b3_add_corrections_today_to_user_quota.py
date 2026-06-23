"""add corrections_today to user_quota

Revision ID: fe681cf5d5b3
Revises: 0be5bc171913
Create Date: 2026-06-23 22:47:27.123017

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'fe681cf5d5b3'
down_revision = '0be5bc171913'
branch_labels = None
depends_on = None


def upgrade():
    # 只加 corrections_today。
    # ⚠ 移除了 autogenerate 误生成的 drop_index('uq_users_email_lower')：那是 M5 手写的
    # 函数唯一索引（lower(email)），autogenerate 不认识手写对象会误删（同 B3 决策的陷阱）。
    op.add_column(
        "user_quota",
        sa.Column("corrections_today", sa.Integer(), nullable=False, server_default="0"),
    )


def downgrade():
    op.drop_column("user_quota", "corrections_today")
