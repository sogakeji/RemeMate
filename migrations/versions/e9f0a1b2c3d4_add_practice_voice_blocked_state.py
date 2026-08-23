"""persist voice-unavailable practice attempts as blocked sessions

Revision ID: e9f0a1b2c3d4
Revises: d7a8b9c0d1e2
"""
from alembic import op
import sqlalchemy as sa


revision = "e9f0a1b2c3d4"
down_revision = "d7a8b9c0d1e2"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column(
        "practice_sessions",
        sa.Column("blocked_at", sa.DateTime(), nullable=True),
    )
    op.drop_constraint(
        "ck_practice_sessions_status",
        "practice_sessions",
        type_="check",
    )
    op.create_check_constraint(
        "ck_practice_sessions_status",
        "practice_sessions",
        "status IN ('active', 'completed', 'abandoned', 'blocked')",
    )


def downgrade():
    op.drop_constraint(
        "ck_practice_sessions_status",
        "practice_sessions",
        type_="check",
    )
    op.execute(
        "ALTER TABLE practice_sessions NO FORCE ROW LEVEL SECURITY;"
    )
    op.execute(
        "UPDATE practice_sessions "
        "SET status = 'abandoned', "
        "abandoned_at = COALESCE(abandoned_at, blocked_at) "
        "WHERE status = 'blocked';"
    )
    op.create_check_constraint(
        "ck_practice_sessions_status",
        "practice_sessions",
        "status IN ('active', 'completed', 'abandoned')",
    )
    op.execute(
        "ALTER TABLE practice_sessions FORCE ROW LEVEL SECURITY;"
    )
    op.drop_column("practice_sessions", "blocked_at")
