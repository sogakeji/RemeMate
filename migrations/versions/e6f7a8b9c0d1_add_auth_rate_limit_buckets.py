"""add anonymous authentication rate limit buckets

Revision ID: e6f7a8b9c0d1
Revises: d5e6f7a8b9c0
"""
from alembic import op
import sqlalchemy as sa


revision = "e6f7a8b9c0d1"
down_revision = "d5e6f7a8b9c0"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "auth_rate_limit_buckets",
        sa.Column("scope", sa.String(length=20), nullable=False),
        sa.Column("key_digest", sa.CHAR(length=64), nullable=False),
        sa.Column(
            "window_start",
            sa.DateTime(timezone=True),
            nullable=False,
        ),
        sa.Column(
            "used_count",
            sa.Integer(),
            nullable=False,
            server_default=sa.text("0"),
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.CheckConstraint(
            "scope IN ('global_day', 'email_hour', "
            "'email_minute', 'client_hour')",
            name="ck_auth_rate_limit_buckets_scope",
        ),
        sa.CheckConstraint(
            "used_count >= 0",
            name="ck_auth_rate_limit_buckets_used_count",
        ),
        sa.PrimaryKeyConstraint(
            "scope",
            "key_digest",
            "window_start",
            name="pk_auth_rate_limit_buckets",
        ),
    )


def downgrade():
    op.drop_table("auth_rate_limit_buckets")
