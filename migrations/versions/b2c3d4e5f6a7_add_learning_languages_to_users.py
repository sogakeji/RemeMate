"""add learning_languages to users

用户「在学语言集合」（ui-rescope 修1）：设置页多选勾几个在学的语言，
首页切换器只在集合内切「当前主攻」language。current_language 必须是集合子集
（不变量由 service set_learning_languages 收敛：删除当前主攻后自动收成首个/英语）。

存法：VARCHAR 逗号拼接（如 "fr,en,ja"），nullable（兼容老用户未设）。比 ARRAY
跨 SQLAlchemy/迁移更稳；语言 code 固定 6 个，不会膨胀。

Revision ID: b2c3d4e5f6a7
Revises: a1b2c3d4e5f6
Create Date: 2026-06-30
"""
from alembic import op


# revision identifiers, used by Alembic.
revision = 'b2c3d4e5f6a7'
down_revision = 'a1b2c3d4e5f6'
branch_labels = None
depends_on = None


def upgrade():
    op.execute(
        "ALTER TABLE users "
        "ADD COLUMN IF NOT EXISTS learning_languages VARCHAR(200);"
    )


def downgrade():
    op.execute("ALTER TABLE users DROP COLUMN IF EXISTS learning_languages;")