"""add anonymous authentication control tables

Revision ID: d5e6f7a8b9c0
Revises: c4d5e6f7a8b9
"""
from alembic import op
import sqlalchemy as sa


revision = "d5e6f7a8b9c0"
down_revision = "c4d5e6f7a8b9"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "auth_challenges",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("token_digest", sa.String(length=64), nullable=False),
        sa.Column("purpose", sa.String(length=20), nullable=False),
        sa.Column("email", sa.String(length=255), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=True),
        sa.Column("expires_at", sa.DateTime(), nullable=False),
        sa.Column("consumed_at", sa.DateTime(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.CheckConstraint(
            "purpose IN ('registration', 'password_reset')",
            name="ck_auth_challenges_purpose",
        ),
        sa.CheckConstraint(
            "(purpose = 'registration' AND user_id IS NULL) OR "
            "(purpose = 'password_reset' AND user_id IS NOT NULL)",
            name="ck_auth_challenges_purpose_user",
        ),
        sa.ForeignKeyConstraint(
            ["user_id"], ["users.id"], ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "token_digest", name="uq_auth_challenges_token_digest",
        ),
    )
    op.create_index(
        "ix_auth_challenges_email_purpose_created",
        "auth_challenges",
        ["email", "purpose", "created_at"],
    )
    op.create_index(
        "ix_auth_challenges_expires_at",
        "auth_challenges",
        ["expires_at"],
    )

    op.create_table(
        "auth_mail_events",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("challenge_id", sa.Integer(), nullable=True),
        sa.Column("purpose", sa.String(length=30), nullable=False),
        sa.Column("email", sa.String(length=255), nullable=False),
        sa.Column("client_key_digest", sa.String(length=64), nullable=False),
        sa.Column("delivery_status", sa.String(length=20), nullable=False),
        sa.Column("provider_message_id", sa.String(length=255), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.CheckConstraint(
            "purpose IN ('registration', 'password_reset', 'account_guidance')",
            name="ck_auth_mail_events_purpose",
        ),
        sa.CheckConstraint(
            "delivery_status IN ('reserved', 'sent', 'failed')",
            name="ck_auth_mail_events_delivery_status",
        ),
        sa.ForeignKeyConstraint(
            ["challenge_id"], ["auth_challenges.id"], ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_auth_mail_events_email_created",
        "auth_mail_events",
        ["email", "created_at"],
    )
    op.create_index(
        "ix_auth_mail_events_client_key_created",
        "auth_mail_events",
        ["client_key_digest", "created_at"],
    )
    op.create_index(
        "ix_auth_mail_events_created_at",
        "auth_mail_events",
        ["created_at"],
    )


def downgrade():
    op.drop_index(
        "ix_auth_mail_events_created_at", table_name="auth_mail_events",
    )
    op.drop_index(
        "ix_auth_mail_events_client_key_created", table_name="auth_mail_events",
    )
    op.drop_index(
        "ix_auth_mail_events_email_created", table_name="auth_mail_events",
    )
    op.drop_table("auth_mail_events")

    op.drop_index(
        "ix_auth_challenges_expires_at", table_name="auth_challenges",
    )
    op.drop_index(
        "ix_auth_challenges_email_purpose_created",
        table_name="auth_challenges",
    )
    op.drop_table("auth_challenges")
