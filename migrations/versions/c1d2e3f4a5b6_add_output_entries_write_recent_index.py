"""add output_entries write-recent index

Revision ID: c1d2e3f4a5b6
Revises: e8f9a0b1c2d3
Create Date: 2026-08-20 12:00:00.000000

/write 目标词查询的 NOT EXISTS 子查询按 (user_id, word_id, created_at)
过滤 output_entries；该表原本只有主键，词频高后热路径会全表扫描。
索引名带 _writerecent 前缀避免与后续 autogenerate 冲突（同项目手写索引约定）。
"""
from alembic import op

# revision identifiers, used by Alembic.
revision = "c1d2e3f4a5b6"
down_revision = "e8f9a0b1c2d3"
branch_labels = None
depends_on = None


def upgrade():
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_output_entries_writerecent "
        "ON output_entries (user_id, word_id, created_at);"
    )


def downgrade():
    op.execute("DROP INDEX IF EXISTS ix_output_entries_writerecent;")
