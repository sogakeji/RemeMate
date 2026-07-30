"""enforce one active normalized candidate per source

Revision ID: b3c4d5e6f7a8
Revises: a2b3c4d5e6f7
"""
from alembic import op
import sqlalchemy as sa


revision = "b3c4d5e6f7a8"
down_revision = "a2b3c4d5e6f7"
branch_labels = None
depends_on = None

INDEX_NAME = "uq_word_candidates_active_source_word"


def upgrade():
    duplicate = op.get_bind().execute(sa.text("""
        SELECT
            source_id,
            lower(btrim(word)) AS normalized_word,
            count(*) AS duplicate_count
        FROM word_candidates
        WHERE status IN ('pending', 'accepted')
        GROUP BY source_id, lower(btrim(word))
        HAVING count(*) > 1
        LIMIT 1
    """)).mappings().first()
    if duplicate is not None:
        raise RuntimeError(
            "cannot create active candidate uniqueness index: "
            f"source_id={duplicate['source_id']} "
            f"normalized_word={duplicate['normalized_word']!r} "
            f"count={duplicate['duplicate_count']}"
        )

    op.execute(sa.text(f"""
        CREATE UNIQUE INDEX {INDEX_NAME}
        ON word_candidates (source_id, lower(btrim(word)))
        WHERE status IN ('pending', 'accepted')
    """))


def downgrade():
    op.execute(sa.text(f"DROP INDEX IF EXISTS {INDEX_NAME}"))
