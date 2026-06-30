"""add current_language to users

用户「正在学哪种语言」的当前状态（ui-rescope 隐式词表闭环）：
- 首页语言切换器、设置页选语言、词列表页「按当前语言展示」共用此列。
- nullable：新用户未设过为 NULL，首页/词列表空态提示「先去设置选语言」。
- 不动 word_lists schema（隐式词表口径：词表对用户不可见，不变量靠 service upsert）。

Revision ID: a1b2c3d4e5f6
Revises: f7429a9f28db
Create Date: 2026-06-30
"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'a1b2c3d4e5f6'
down_revision = 'f7429a9f28db'
branch_labels = None
depends_on = None


def upgrade():
    # IF NOT EXISTS 保证可重入（review 2026-06-23 M7）。
    op.execute(
        "ALTER TABLE users "
        "ADD COLUMN IF NOT EXISTS current_language VARCHAR(10);"
    )


def downgrade():
    op.execute("ALTER TABLE users DROP COLUMN IF EXISTS current_language;")