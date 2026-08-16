"""expand review-story feedback languages for the AI language set

Revision ID: e7f8a9b0c1d2
Revises: e6f7a8b9c0d1
"""
from alembic import op


revision = "e7f8a9b0c1d2"
down_revision = "e6f7a8b9c0d1"
branch_labels = None
depends_on = None


def upgrade():
    op.drop_constraint(
        "ck_review_story_runs_feedback_language",
        "review_story_runs",
        type_="check",
    )
    op.create_check_constraint(
        "ck_review_story_runs_feedback_language",
        "review_story_runs",
        "feedback_language IN ('zh','fr','en','ja','ko','es')",
    )


def downgrade():
    op.drop_constraint(
        "ck_review_story_runs_feedback_language",
        "review_story_runs",
        type_="check",
    )
    op.create_check_constraint(
        "ck_review_story_runs_feedback_language",
        "review_story_runs",
        "feedback_language IN ('zh','fr','en')",
    )
