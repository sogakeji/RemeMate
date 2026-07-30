"""add SessionPad candidate context fields

Revision ID: a2b3c4d5e6f7
Revises: f1a2b3c4d5e6
"""
from alembic import op
import sqlalchemy as sa


revision = "a2b3c4d5e6f7"
down_revision = "f1a2b3c4d5e6"
branch_labels = None
depends_on = None

CONSTRAINT_NAME = "ck_word_candidates_context_pair"


def upgrade():
    op.add_column(
        "word_candidates",
        sa.Column("context_excerpt", sa.Text(), nullable=True),
    )
    op.add_column(
        "word_candidates",
        sa.Column("context_provenance", sa.String(length=20), nullable=True),
    )
    op.create_check_constraint(
        CONSTRAINT_NAME,
        "word_candidates",
        """
        (
            context_excerpt IS NULL
            AND context_provenance IS NULL
        ) OR (
            context_excerpt IS NOT NULL
            AND context_provenance IS NOT NULL
            AND length(btrim(context_excerpt)) BETWEEN 1 AND 300
            AND context_provenance IN ('source_quote', 'user_edited')
        )
        """,
    )


def downgrade():
    op.drop_constraint(CONSTRAINT_NAME, "word_candidates", type_="check")
    op.drop_column("word_candidates", "context_provenance")
    op.drop_column("word_candidates", "context_excerpt")
