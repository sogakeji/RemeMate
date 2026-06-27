"""add on delete cascade to word/list FKs

删词表/词时子表跟着清理，避免 review_logs 等 FK 阻塞删除（review 2026-06-23 复现）。
- words.list_id, definitions.word_id, review_logs.word_id, output_entries.word_id → CASCADE
- intake_sources.word_list_id, source_segments.source_id, word_candidates.source_id → CASCADE
- word_candidates.word_id → SET NULL（保留候选记录，仅断链）

可重入（review 2026-06-23 M7）：约束名不写死。Autogenerate 默认名通常与下表
一致，但开发库可能带数字后缀（如 words_list_id_fkey1）或不同名。改为查
pg_constraint 动态取该 (table, column) 的实际外键约束名再 DROP/ADD，且
DROP 走 IF EXISTS，避免重跑（迁移回滚后重试、库已部分有约束）时报
"constraint does not exist"。

Revision ID: b27062024cc0
Revises: 1ca04f710530
"""
from alembic import op
from sqlalchemy import text

revision = 'b27062024cc0'
down_revision = '1ca04f710530'
branch_labels = None
depends_on = None

# (table, column, ref_table, ref_col, ondelete)
_CASCADE = [
    ("words", "list_id", "word_lists", "id", "CASCADE"),
    ("definitions", "word_id", "words", "id", "CASCADE"),
    ("review_logs", "word_id", "words", "id", "CASCADE"),
    ("output_entries", "word_id", "words", "id", "CASCADE"),
    ("intake_sources", "word_list_id", "word_lists", "id", "CASCADE"),
    ("source_segments", "source_id", "intake_sources", "id", "CASCADE"),
    ("word_candidates", "source_id", "intake_sources", "id", "CASCADE"),
    ("word_candidates", "word_id", "words", "id", "SET NULL"),
]


def _existing_fk_name(bind, table, column):
    """查 pg_constraint 取该列实际外键约束名，无则返回 None。

    conrelid=表的 OID；pg_attribute.表与本列匹配；contype='f'=外键。
    """
    result = bind.execute(
        text(
            """
        SELECT c.conname
        FROM pg_constraint c
        JOIN pg_attribute a
          ON a.attrelid = c.conrelid AND a.attnum = ANY (c.conkey)
        WHERE c.contype = 'f'
          AND c.conrelid = cast(:table_id as regclass)
          AND a.attname = :column
        LIMIT 1
        """
        ),
        {"table_id": table, "column": column},
    )
    row = result.fetchone()
    return row[0] if row else None


def _recreate(table, column, ref_table, ref_col, ondelete):
    bind = op.get_bind()
    name = _existing_fk_name(bind, table, column)
    if name is None:
        return  # 该列当前无外键约束，无可重建项（已在目标态 / 库被手动改过）
    op.execute(f'ALTER TABLE {table} DROP CONSTRAINT IF EXISTS {name};')
    # 复用原名，保持与 autogenerate 默认命名一致，便于后续审计。
    op.execute(
        f"ALTER TABLE {table} ADD CONSTRAINT {name} "
        f"FOREIGN KEY ({column}) REFERENCES {ref_table}({ref_col}) ON DELETE {ondelete};"
    )


def upgrade():
    for table, column, ref_table, ref_col, ondelete in _CASCADE:
        _recreate(table, column, ref_table, ref_col, ondelete)


def downgrade():
    # 还原为无 ON DELETE（NO ACTION）
    for table, column, ref_table, ref_col, _ in _CASCADE:
        _recreate_no_action(table, column, ref_table, ref_col)


def _recreate_no_action(table, column, ref_table, ref_col):
    bind = op.get_bind()
    name = _existing_fk_name(bind, table, column)
    if name is None:
        return
    op.execute(f'ALTER TABLE {table} DROP CONSTRAINT IF EXISTS {name};')
    op.execute(
        f"ALTER TABLE {table} ADD CONSTRAINT {name} "
        f"FOREIGN KEY ({column}) REFERENCES {ref_table}({ref_col});"
    )
