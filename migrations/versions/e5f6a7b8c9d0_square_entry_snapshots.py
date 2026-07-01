"""square entry display snapshots

Revision ID: e5f6a7b8c9d0
Revises: c3d4e5f6a7b8
Create Date: 2026-07-01
"""
from alembic import op


revision = 'e5f6a7b8c9d0'
down_revision = 'c3d4e5f6a7b8'
branch_labels = None
depends_on = None


def upgrade():
    # The initial public read policies for words/word_lists caused recursive RLS
    # through the existing private word policies. Square reads denormalized
    # snapshots from output_entries instead, so private word tables stay private.
    op.execute("DROP POLICY IF EXISTS word_lists_square_public_sel ON word_lists;")
    op.execute("DROP POLICY IF EXISTS words_square_public_sel ON words;")
    op.execute(
        "ALTER TABLE output_entries "
        "ADD COLUMN IF NOT EXISTS word_text varchar(200);"
    )
    op.execute(
        "ALTER TABLE output_entries "
        "ADD COLUMN IF NOT EXISTS language_code varchar(10);"
    )
    op.execute("ALTER TABLE output_entries DISABLE ROW LEVEL SECURITY;")
    op.execute("ALTER TABLE words DISABLE ROW LEVEL SECURITY;")
    op.execute("ALTER TABLE word_lists DISABLE ROW LEVEL SECURITY;")
    op.execute("""
        UPDATE output_entries AS e
        SET word_text = w.word,
            language_code = wl.language_code
        FROM words AS w
        JOIN word_lists AS wl ON wl.id = w.list_id
        WHERE e.word_id = w.id
          AND (e.word_text IS NULL OR e.language_code IS NULL);
    """)
    op.execute("ALTER TABLE output_entries ALTER COLUMN word_text SET NOT NULL;")
    op.execute("ALTER TABLE output_entries ALTER COLUMN language_code SET NOT NULL;")
    op.execute("ALTER TABLE word_lists ENABLE ROW LEVEL SECURITY;")
    op.execute("ALTER TABLE word_lists FORCE ROW LEVEL SECURITY;")
    op.execute("ALTER TABLE words ENABLE ROW LEVEL SECURITY;")
    op.execute("ALTER TABLE words FORCE ROW LEVEL SECURITY;")
    op.execute("ALTER TABLE output_entries ENABLE ROW LEVEL SECURITY;")
    op.execute("ALTER TABLE output_entries FORCE ROW LEVEL SECURITY;")


def downgrade():
    op.execute("ALTER TABLE output_entries DROP COLUMN IF EXISTS language_code;")
    op.execute("ALTER TABLE output_entries DROP COLUMN IF EXISTS word_text;")
    op.execute("DROP POLICY IF EXISTS words_square_public_sel ON words;")
    op.execute("DROP POLICY IF EXISTS word_lists_square_public_sel ON word_lists;")
