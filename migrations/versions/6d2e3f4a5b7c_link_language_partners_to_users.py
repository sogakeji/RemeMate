"""link language partner profiles to accepted user accounts

Revision ID: 6d2e3f4a5b7c
Revises: 5c1d2e3f4a6b
Create Date: 2026-07-10
"""
from alembic import op
import sqlalchemy as sa


revision = "6d2e3f4a5b7c"
down_revision = "5c1d2e3f4a6b"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column(
        "language_partners",
        sa.Column("linked_user_id", sa.Integer(), nullable=True),
    )
    op.add_column(
        "language_partners",
        sa.Column("invite_token_hash", sa.String(length=64), nullable=True),
    )
    op.create_foreign_key(
        "fk_language_partners_linked_user",
        "language_partners",
        "users",
        ["linked_user_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_check_constraint(
        "ck_language_partners_not_self_linked",
        "language_partners",
        "linked_user_id IS NULL OR linked_user_id <> user_id",
    )
    op.create_unique_constraint(
        "uq_language_partners_user_linked_user",
        "language_partners",
        ["user_id", "linked_user_id"],
    )
    op.create_index(
        "ix_language_partners_linked_user_id",
        "language_partners",
        ["linked_user_id"],
    )


def downgrade():
    op.drop_index(
        "ix_language_partners_linked_user_id",
        table_name="language_partners",
    )
    op.drop_constraint(
        "uq_language_partners_user_linked_user",
        "language_partners",
        type_="unique",
    )
    op.drop_constraint(
        "ck_language_partners_not_self_linked",
        "language_partners",
        type_="check",
    )
    op.drop_constraint(
        "fk_language_partners_linked_user",
        "language_partners",
        type_="foreignkey",
    )
    op.drop_column("language_partners", "invite_token_hash")
    op.drop_column("language_partners", "linked_user_id")
