"""unique word list per user/language

Revision ID: c3d4e5f6a7b8
Revises: b2c3d4e5f6a7
Create Date: 2026-06-30
"""
from alembic import op


# revision identifiers, used by Alembic.
revision = 'c3d4e5f6a7b8'
down_revision = 'b2c3d4e5f6a7'
branch_labels = None
depends_on = None


def upgrade():
    # Collapse any pre-existing duplicates before adding the invariant. Keep the
    # earliest list and move dependent rows to it; word-level dedupe remains the
    # service layer's concern.
    op.execute("""
        WITH ranked AS (
            SELECT id,
                   min(id) OVER (PARTITION BY user_id, language_code) AS keep_id,
                   row_number() OVER (PARTITION BY user_id, language_code ORDER BY id) AS rn
            FROM word_lists
        )
        UPDATE words AS w
        SET list_id = ranked.keep_id
        FROM ranked
        WHERE w.list_id = ranked.id AND ranked.rn > 1;
    """)
    op.execute("""
        WITH ranked AS (
            SELECT id,
                   min(id) OVER (PARTITION BY user_id, language_code) AS keep_id,
                   row_number() OVER (PARTITION BY user_id, language_code ORDER BY id) AS rn
            FROM word_lists
        )
        UPDATE intake_sources AS s
        SET word_list_id = ranked.keep_id
        FROM ranked
        WHERE s.word_list_id = ranked.id AND ranked.rn > 1;
    """)
    op.execute("""
        WITH ranked AS (
            SELECT id,
                   row_number() OVER (PARTITION BY user_id, language_code ORDER BY id) AS rn
            FROM word_lists
        )
        DELETE FROM word_lists AS wl
        USING ranked
        WHERE wl.id = ranked.id AND ranked.rn > 1;
    """)
    op.execute("""
        DO $$
        BEGIN
            IF NOT EXISTS (
                SELECT 1 FROM pg_constraint
                WHERE conname = 'uq_word_lists_user_language'
                  AND conrelid = 'word_lists'::regclass
            ) THEN
                ALTER TABLE word_lists
                ADD CONSTRAINT uq_word_lists_user_language
                UNIQUE (user_id, language_code);
            END IF;
        END $$;
    """)


def downgrade():
    op.execute("""
        ALTER TABLE word_lists
        DROP CONSTRAINT IF EXISTS uq_word_lists_user_language;
    """)
