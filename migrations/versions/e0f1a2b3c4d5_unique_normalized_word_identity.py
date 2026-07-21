"""unique normalized word identity inside one language list

Revision ID: e0f1a2b3c4d5
Revises: d9e0f1a2b3c4
"""
from alembic import op


revision = "e0f1a2b3c4d5"
down_revision = "d9e0f1a2b3c4"
branch_labels = None
depends_on = None


INDEX_NAME = "uq_words_list_normalized_word"


def upgrade():
    # Do not guess how to merge user-authored entries. Abort with only an
    # aggregate count so an operator can audit and resolve them deliberately.
    op.execute("""
        DO $$
        DECLARE
            duplicate_groups bigint;
        BEGIN
            SELECT count(*) INTO duplicate_groups
            FROM (
                SELECT 1
                FROM words
                GROUP BY list_id, lower(btrim(word))
                HAVING count(*) > 1
            ) AS duplicates;

            IF duplicate_groups > 0 THEN
                RAISE EXCEPTION
                    'Cannot add normalized word uniqueness: % duplicate groups',
                    duplicate_groups;
            END IF;
        END $$;
    """)
    op.execute(f"""
        CREATE UNIQUE INDEX IF NOT EXISTS {INDEX_NAME}
        ON words (list_id, lower(btrim(word)));
    """)


def downgrade():
    op.execute(f"DROP INDEX IF EXISTS {INDEX_NAME};")
