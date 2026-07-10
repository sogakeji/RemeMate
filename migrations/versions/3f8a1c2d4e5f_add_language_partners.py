"""add language partners

Revision ID: 3f8a1c2d4e5f
Revises: 2e79a6ececcc
Create Date: 2026-07-10
"""
from alembic import op
import sqlalchemy as sa


revision = "3f8a1c2d4e5f"
down_revision = "2e79a6ececcc"
branch_labels = None
depends_on = None

UID = "NULLIF(current_setting('app.current_user_id', true), '')::int"


def upgrade():
    op.create_table(
        "language_partners",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("display_name", sa.String(length=100), nullable=False),
        sa.Column("native_language_code", sa.String(length=10), nullable=True),
        sa.Column("learning_language_code", sa.String(length=10), nullable=True),
        sa.Column("private_note", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.CheckConstraint(
            "native_language_code IS NULL OR "
            "native_language_code IN ('fr','en','ja','de','es','ru','zh')",
            name="ck_language_partners_native_language",
        ),
        sa.CheckConstraint(
            "learning_language_code IS NULL OR "
            "learning_language_code IN ('fr','en','ja','de','es','ru','zh')",
            name="ck_language_partners_learning_language",
        ),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("id", "user_id",
                            name="uq_language_partners_id_user_id"),
    )
    op.create_index(
        "ix_language_partners_user_updated",
        "language_partners", ["user_id", "updated_at"],
    )
    op.execute("ALTER TABLE language_partners ENABLE ROW LEVEL SECURITY;")
    op.execute("ALTER TABLE language_partners FORCE ROW LEVEL SECURITY;")
    op.execute(f"""
        CREATE POLICY language_partners_sel ON language_partners FOR SELECT
            USING (user_id = {UID});
        CREATE POLICY language_partners_ins ON language_partners FOR INSERT
            WITH CHECK (user_id = {UID});
        CREATE POLICY language_partners_upd ON language_partners FOR UPDATE
            USING (user_id = {UID}) WITH CHECK (user_id = {UID});
        CREATE POLICY language_partners_del ON language_partners FOR DELETE
            USING (user_id = {UID});
    """)


def downgrade():
    op.execute("DROP POLICY IF EXISTS language_partners_del ON language_partners;")
    op.execute("DROP POLICY IF EXISTS language_partners_upd ON language_partners;")
    op.execute("DROP POLICY IF EXISTS language_partners_ins ON language_partners;")
    op.execute("DROP POLICY IF EXISTS language_partners_sel ON language_partners;")
    op.execute("ALTER TABLE language_partners NO FORCE ROW LEVEL SECURITY;")
    op.execute("ALTER TABLE language_partners DISABLE ROW LEVEL SECURITY;")
    op.drop_index("ix_language_partners_user_updated",
                  table_name="language_partners")
    op.drop_table("language_partners")
