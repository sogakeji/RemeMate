"""add on delete cascade to word/list FKs

删词表/词时子表跟着清理，避免 review_logs 等 FK 阻塞删除（review 2026-06-23 复现）。
- words.list_id, definitions.word_id, review_logs.word_id, output_entries.word_id → CASCADE
- intake_sources.word_list_id, source_segments.source_id, word_candidates.source_id → CASCADE
- word_candidates.word_id → SET NULL（保留候选记录，仅断链）

Revision ID: b27062024cc0
Revises: 1ca04f710530
"""
from alembic import op

revision = 'b27062024cc0'
down_revision = '1ca04f710530'
branch_labels = None
depends_on = None

# (table, constraint_name, column, ref_table, ref_col, ondelete)
_CASCADE = [
    ("words", "words_list_id_fkey", "list_id", "word_lists", "id", "CASCADE"),
    ("definitions", "definitions_word_id_fkey", "word_id", "words", "id", "CASCADE"),
    ("review_logs", "review_logs_word_id_fkey", "word_id", "words", "id", "CASCADE"),
    ("output_entries", "output_entries_word_id_fkey", "word_id", "words", "id", "CASCADE"),
    ("intake_sources", "intake_sources_word_list_id_fkey", "word_list_id", "word_lists", "id", "CASCADE"),
    ("source_segments", "source_segments_source_id_fkey", "source_id", "intake_sources", "id", "CASCADE"),
    ("word_candidates", "word_candidates_source_id_fkey", "source_id", "intake_sources", "id", "CASCADE"),
    ("word_candidates", "word_candidates_word_id_fkey", "word_id", "words", "id", "SET NULL"),
]


def _recreate(table, name, col, ref_table, ref_col, ondelete):
    op.execute(f"ALTER TABLE {table} DROP CONSTRAINT {name};")
    op.execute(
        f"ALTER TABLE {table} ADD CONSTRAINT {name} "
        f"FOREIGN KEY ({col}) REFERENCES {ref_table}({ref_col}) ON DELETE {ondelete};"
    )


def upgrade():
    for row in _CASCADE:
        _recreate(*row)


def downgrade():
    # 还原为无 ON DELETE（NO ACTION）
    for table, name, col, ref_table, ref_col, _ in _CASCADE:
        op.execute(f"ALTER TABLE {table} DROP CONSTRAINT {name};")
        op.execute(
            f"ALTER TABLE {table} ADD CONSTRAINT {name} "
            f"FOREIGN KEY ({col}) REFERENCES {ref_table}({ref_col});"
        )
