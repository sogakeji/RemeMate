"""add partner recap AI summary

Revision ID: a6b7c8d9e0f1
Revises: 9a5b6c7d8e0f
Create Date: 2026-07-11
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "a6b7c8d9e0f1"
down_revision = "9a5b6c7d8e0f"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column(
        "partner_recaps",
        sa.Column("ai_summary", postgresql.JSONB(), nullable=True),
    )
    op.add_column(
        "partner_recaps",
        sa.Column("ai_summary_source_hash", sa.String(64), nullable=True),
    )
    op.add_column(
        "partner_recaps",
        sa.Column("ai_summary_generated_at", sa.DateTime(), nullable=True),
    )


def downgrade():
    op.drop_column("partner_recaps", "ai_summary_generated_at")
    op.drop_column("partner_recaps", "ai_summary_source_hash")
    op.drop_column("partner_recaps", "ai_summary")
