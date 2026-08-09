"""add open-registration identity fields

Revision ID: c4d5e6f7a8b9
Revises: b3c4d5e6f7a8
"""
from uuid import uuid4

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "c4d5e6f7a8b9"
down_revision = "b3c4d5e6f7a8"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column(
        "users",
        sa.Column("public_id", postgresql.UUID(as_uuid=True), nullable=True),
    )
    op.add_column(
        "users",
        sa.Column(
            "password_setup_required",
            sa.Boolean(),
            nullable=True,
            server_default=sa.text("false"),
        ),
    )

    bind = op.get_bind()
    user_ids = bind.execute(
        sa.text("SELECT id FROM users WHERE public_id IS NULL ORDER BY id")
    ).scalars().all()
    for user_id in user_ids:
        bind.execute(
            sa.text("UPDATE users SET public_id=:public_id WHERE id=:user_id"),
            {"public_id": uuid4(), "user_id": user_id},
        )

    bind.execute(
        sa.text(
            "UPDATE users SET password_setup_required=false "
            "WHERE password_setup_required IS NULL"
        )
    )
    op.alter_column(
        "users",
        "public_id",
        existing_type=postgresql.UUID(as_uuid=True),
        nullable=False,
    )
    op.alter_column(
        "users",
        "password_setup_required",
        existing_type=sa.Boolean(),
        nullable=False,
        server_default=sa.text("false"),
    )
    op.create_unique_constraint(
        "uq_users_public_id",
        "users",
        ["public_id"],
    )


def downgrade():
    op.drop_constraint("uq_users_public_id", "users", type_="unique")
    op.drop_column("users", "password_setup_required")
    op.drop_column("users", "public_id")
