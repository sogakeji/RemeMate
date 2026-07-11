"""add partner recap items

Revision ID: 4b0c3d4e5f6a
Revises: 4a9b2c3d5e6f
Create Date: 2026-07-10
"""
from alembic import op
import sqlalchemy as sa


revision = "4b0c3d4e5f6a"
down_revision = "4a9b2c3d5e6f"
branch_labels = None
depends_on = None

UID = "NULLIF(current_setting('app.current_user_id', true), '')::int"


def upgrade():
    op.create_table(
        "partner_recap_items",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("recap_id", sa.Integer(), nullable=False),
        sa.Column("side", sa.String(length=20), nullable=False),
        sa.Column("kind", sa.String(length=30), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.CheckConstraint(
            "side IN ('for_me','for_partner')",
            name="ck_partner_recap_items_side",
        ),
        sa.CheckConstraint(
            "kind IN ('expression','natural_phrase','correction','next_time',"
            "'private_note')",
            name="ck_partner_recap_items_kind",
        ),
        sa.CheckConstraint(
            "side = 'for_partner' OR kind <> 'correction'",
            name="ck_partner_recap_items_correction_side",
        ),
        sa.CheckConstraint(
            "side = 'for_me' OR kind <> 'private_note'",
            name="ck_partner_recap_items_private_note_side",
        ),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(
            ["recap_id", "user_id"],
            ["partner_recaps.id", "partner_recaps.user_id"],
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("id", "user_id",
                            name="uq_partner_recap_items_id_user_id"),
    )
    op.create_index(
        "ix_partner_recap_items_user_recap", "partner_recap_items",
        ["user_id", "recap_id", "created_at"],
    )
    op.execute("ALTER TABLE partner_recap_items ENABLE ROW LEVEL SECURITY;")
    op.execute("ALTER TABLE partner_recap_items FORCE ROW LEVEL SECURITY;")
    op.execute(f"""
        CREATE POLICY partner_recap_items_sel ON partner_recap_items FOR SELECT
            USING (user_id = {UID});
        CREATE POLICY partner_recap_items_ins ON partner_recap_items FOR INSERT
            WITH CHECK (user_id = {UID});
        CREATE POLICY partner_recap_items_upd ON partner_recap_items FOR UPDATE
            USING (user_id = {UID}) WITH CHECK (user_id = {UID});
        CREATE POLICY partner_recap_items_del ON partner_recap_items FOR DELETE
            USING (user_id = {UID});
    """)


def downgrade():
    op.execute("DROP POLICY IF EXISTS partner_recap_items_del ON partner_recap_items;")
    op.execute("DROP POLICY IF EXISTS partner_recap_items_upd ON partner_recap_items;")
    op.execute("DROP POLICY IF EXISTS partner_recap_items_ins ON partner_recap_items;")
    op.execute("DROP POLICY IF EXISTS partner_recap_items_sel ON partner_recap_items;")
    op.execute("ALTER TABLE partner_recap_items NO FORCE ROW LEVEL SECURITY;")
    op.execute("ALTER TABLE partner_recap_items DISABLE ROW LEVEL SECURITY;")
    op.drop_index("ix_partner_recap_items_user_recap",
                  table_name="partner_recap_items")
    op.drop_table("partner_recap_items")
