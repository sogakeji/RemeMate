"""add contextual dictation practice tables

Revision ID: d7a8b9c0d1e2
Revises: c1d2e3f4a5b6
"""
from alembic import op
import sqlalchemy as sa


revision = "d7a8b9c0d1e2"
down_revision = "c1d2e3f4a5b6"
branch_labels = None
depends_on = None


UID = "NULLIF(current_setting('app.current_user_id', true), '')::int"


def _policy(name, table, statement):
    op.execute(f"DROP POLICY IF EXISTS {name} ON {table};")
    op.execute(statement)


def upgrade():
    op.create_table(
        "practice_sessions",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("language_code", sa.String(length=10), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("current_position", sa.Integer(), nullable=False),
        sa.Column("voice_available", sa.Boolean(), nullable=True),
        sa.Column("started_at", sa.DateTime(), nullable=False),
        sa.Column("completed_at", sa.DateTime(), nullable=True),
        sa.Column("abandoned_at", sa.DateTime(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.CheckConstraint(
            "status IN ('active', 'completed', 'abandoned')",
            name="ck_practice_sessions_status",
        ),
        sa.CheckConstraint(
            "current_position >= 0",
            name="ck_practice_sessions_current_position_nonnegative",
        ),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
    )
    op.create_index(
        "ix_practice_sessions_user_created",
        "practice_sessions", ["user_id", "created_at", "id"],
    )

    op.create_table(
        "practice_items",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("session_id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("word_id", sa.Integer(), nullable=False),
        sa.Column("definition_id", sa.Integer(), nullable=False),
        sa.Column("position", sa.Integer(), nullable=False),
        sa.Column("sentence", sa.Text(), nullable=False),
        sa.Column("target", sa.Text(), nullable=False),
        sa.Column("meaning", sa.Text(), nullable=True),
        sa.Column("submitted_answer", sa.Text(), nullable=True),
        sa.Column("normalized_answer", sa.Text(), nullable=True),
        sa.Column("is_correct", sa.Boolean(), nullable=True),
        sa.Column("submitted_at", sa.DateTime(), nullable=True),
        sa.Column("replay_count", sa.Integer(), nullable=False),
        sa.Column("answer_duration_ms", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.CheckConstraint(
            "position >= 0", name="ck_practice_items_position_nonnegative",
        ),
        sa.CheckConstraint(
            "replay_count >= 0",
            name="ck_practice_items_replay_count_nonnegative",
        ),
        sa.CheckConstraint(
            "answer_duration_ms IS NULL OR answer_duration_ms >= 0",
            name="ck_practice_items_answer_duration_nonnegative",
        ),
        sa.ForeignKeyConstraint(
            ["session_id"], ["practice_sessions.id"], ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["word_id"], ["words.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(
            ["definition_id"], ["definitions.id"], ondelete="CASCADE",
        ),
        sa.UniqueConstraint(
            "session_id", "position", name="uq_practice_items_session_position",
        ),
        sa.UniqueConstraint(
            "session_id", "word_id", name="uq_practice_items_session_word",
        ),
    )
    op.create_index(
        "ix_practice_items_session_position",
        "practice_items", ["session_id", "position"],
    )

    for table in ("practice_sessions", "practice_items"):
        op.execute(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY;")
        op.execute(f"ALTER TABLE {table} FORCE ROW LEVEL SECURITY;")

    _policy(
        "practice_sessions_select",
        "practice_sessions",
        f"CREATE POLICY practice_sessions_select ON practice_sessions "
        f"FOR SELECT USING (user_id = {UID});",
    )
    _policy(
        "practice_sessions_insert",
        "practice_sessions",
        f"CREATE POLICY practice_sessions_insert ON practice_sessions "
        f"FOR INSERT WITH CHECK (user_id = {UID});",
    )
    _policy(
        "practice_sessions_update",
        "practice_sessions",
        f"CREATE POLICY practice_sessions_update ON practice_sessions "
        f"FOR UPDATE USING (user_id = {UID}) WITH CHECK (user_id = {UID});",
    )
    _policy(
        "practice_sessions_delete",
        "practice_sessions",
        f"CREATE POLICY practice_sessions_delete ON practice_sessions "
        f"FOR DELETE USING (user_id = {UID});",
    )

    item_owner = f"user_id = {UID}"
    item_session_owner = (
        f"{item_owner} AND EXISTS ("
        f"SELECT 1 FROM practice_sessions ps "
        f"WHERE ps.id = practice_items.session_id AND ps.user_id = {UID})"
    )
    _policy(
        "practice_items_select",
        "practice_items",
        f"CREATE POLICY practice_items_select ON practice_items "
        f"FOR SELECT USING ({item_owner});",
    )
    _policy(
        "practice_items_insert",
        "practice_items",
        f"CREATE POLICY practice_items_insert ON practice_items "
        f"FOR INSERT WITH CHECK ({item_session_owner});",
    )
    _policy(
        "practice_items_update",
        "practice_items",
        f"CREATE POLICY practice_items_update ON practice_items "
        f"FOR UPDATE USING ({item_owner}) WITH CHECK ({item_session_owner});",
    )
    _policy(
        "practice_items_delete",
        "practice_items",
        f"CREATE POLICY practice_items_delete ON practice_items "
        f"FOR DELETE USING ({item_owner});",
    )


def downgrade():
    for policy, table in (
        ("practice_items_delete", "practice_items"),
        ("practice_items_update", "practice_items"),
        ("practice_items_insert", "practice_items"),
        ("practice_items_select", "practice_items"),
        ("practice_sessions_delete", "practice_sessions"),
        ("practice_sessions_update", "practice_sessions"),
        ("practice_sessions_insert", "practice_sessions"),
        ("practice_sessions_select", "practice_sessions"),
    ):
        op.execute(f"DROP POLICY IF EXISTS {policy} ON {table};")
    for table in ("practice_items", "practice_sessions"):
        op.execute(f"ALTER TABLE {table} NO FORCE ROW LEVEL SECURITY;")
        op.execute(f"ALTER TABLE {table} DISABLE ROW LEVEL SECURITY;")
    op.drop_index("ix_practice_items_session_position", table_name="practice_items")
    op.drop_table("practice_items")
    op.drop_index("ix_practice_sessions_user_created", table_name="practice_sessions")
    op.drop_table("practice_sessions")
