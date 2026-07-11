"""add partner recaps

Revision ID: 4a9b2c3d5e6f
Revises: 3f8a1c2d4e5f
Create Date: 2026-07-10
"""
from alembic import op
import sqlalchemy as sa


revision = "4a9b2c3d5e6f"
down_revision = "3f8a1c2d4e5f"
branch_labels = None
depends_on = None

UID = "NULLIF(current_setting('app.current_user_id', true), '')::int"


def upgrade():
    op.create_table(
        "partner_recaps",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("partner_id", sa.Integer(), nullable=False),
        sa.Column("session_date", sa.Date(), nullable=False),
        sa.Column("title", sa.String(length=120), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(
            ["partner_id", "user_id"],
            ["language_partners.id", "language_partners.user_id"],
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("id", "user_id",
                            name="uq_partner_recaps_id_user_id"),
    )
    op.create_index(
        "ix_partner_recaps_user_partner_date", "partner_recaps",
        ["user_id", "partner_id", "session_date"],
    )
    op.execute("ALTER TABLE partner_recaps ENABLE ROW LEVEL SECURITY;")
    op.execute("ALTER TABLE partner_recaps FORCE ROW LEVEL SECURITY;")
    op.execute(f"""
        CREATE POLICY partner_recaps_sel ON partner_recaps FOR SELECT
            USING (user_id = {UID});
        CREATE POLICY partner_recaps_ins ON partner_recaps FOR INSERT
            WITH CHECK (user_id = {UID});
        CREATE POLICY partner_recaps_upd ON partner_recaps FOR UPDATE
            USING (user_id = {UID}) WITH CHECK (user_id = {UID});
        CREATE POLICY partner_recaps_del ON partner_recaps FOR DELETE
            USING (user_id = {UID});
    """)

def downgrade():
    op.execute("DROP POLICY IF EXISTS partner_recaps_del ON partner_recaps;")
    op.execute("DROP POLICY IF EXISTS partner_recaps_upd ON partner_recaps;")
    op.execute("DROP POLICY IF EXISTS partner_recaps_ins ON partner_recaps;")
    op.execute("DROP POLICY IF EXISTS partner_recaps_sel ON partner_recaps;")
    op.execute("ALTER TABLE partner_recaps NO FORCE ROW LEVEL SECURITY;")
    op.execute("ALTER TABLE partner_recaps DISABLE ROW LEVEL SECURITY;")
    op.drop_index("ix_partner_recaps_user_partner_date",
                  table_name="partner_recaps")
    op.drop_table("partner_recaps")
