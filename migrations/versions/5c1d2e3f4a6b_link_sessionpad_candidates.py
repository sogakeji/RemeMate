"""link SessionPad recaps to intake candidates

Revision ID: 5c1d2e3f4a6b
Revises: 4b0c3d4e5f6a
Create Date: 2026-07-10
"""
from alembic import op
import sqlalchemy as sa


revision = "5c1d2e3f4a6b"
down_revision = "4b0c3d4e5f6a"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column(
        "partner_recaps",
        sa.Column("intake_source_id", sa.Integer(), nullable=True),
    )
    op.create_index(
        "ix_partner_recaps_intake_source_id",
        "partner_recaps",
        ["intake_source_id"],
    )
    op.create_foreign_key(
        "fk_partner_recaps_intake_source",
        "partner_recaps",
        "intake_sources",
        ["intake_source_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.execute("""
        ALTER TABLE partner_recaps
        ADD CONSTRAINT fk_partner_recaps_intake_source_owner
        FOREIGN KEY (intake_source_id, user_id)
        REFERENCES intake_sources (id, user_id)
        ON DELETE SET NULL (intake_source_id)
    """)

    op.add_column(
        "partner_recap_items",
        sa.Column("candidate_id", sa.Integer(), nullable=True),
    )
    op.create_index(
        "ix_partner_recap_items_candidate_id",
        "partner_recap_items",
        ["candidate_id"],
    )
    op.create_foreign_key(
        "fk_partner_recap_items_candidate",
        "partner_recap_items",
        "word_candidates",
        ["candidate_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.execute("""
        ALTER TABLE partner_recap_items
        ADD CONSTRAINT fk_partner_recap_items_candidate_owner
        FOREIGN KEY (candidate_id, user_id)
        REFERENCES word_candidates (id, user_id)
        ON DELETE SET NULL (candidate_id)
    """)


def downgrade():
    op.drop_constraint(
        "fk_partner_recap_items_candidate_owner",
        "partner_recap_items",
        type_="foreignkey",
    )
    op.drop_constraint(
        "fk_partner_recap_items_candidate",
        "partner_recap_items",
        type_="foreignkey",
    )
    op.drop_index(
        "ix_partner_recap_items_candidate_id",
        table_name="partner_recap_items",
    )
    op.drop_column("partner_recap_items", "candidate_id")

    op.drop_constraint(
        "fk_partner_recaps_intake_source_owner",
        "partner_recaps",
        type_="foreignkey",
    )
    op.drop_constraint(
        "fk_partner_recaps_intake_source",
        "partner_recaps",
        type_="foreignkey",
    )
    op.drop_index(
        "ix_partner_recaps_intake_source_id",
        table_name="partner_recaps",
    )
    op.drop_column("partner_recaps", "intake_source_id")
