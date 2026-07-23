"""add review story foundation

Revision ID: f1a2b3c4d5e6
Revises: e0f1a2b3c4d5
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "f1a2b3c4d5e6"
down_revision = "e0f1a2b3c4d5"
branch_labels = None
depends_on = None

UID = "NULLIF(current_setting('app.current_user_id', true), '')::int"


def _create_user_policies(table):
    op.execute(f"""
        CREATE POLICY {table}_sel ON {table} FOR SELECT
            USING (user_id = {UID});
        CREATE POLICY {table}_ins ON {table} FOR INSERT
            WITH CHECK (user_id = {UID});
        CREATE POLICY {table}_upd ON {table} FOR UPDATE
            USING (user_id = {UID}) WITH CHECK (user_id = {UID});
        CREATE POLICY {table}_del ON {table} FOR DELETE
            USING (user_id = {UID});
    """)


def upgrade():
    op.create_index(
        "ix_review_logs_user_ts_word_grade",
        "review_logs",
        ["user_id", "ts", "word_id", "grade"],
    )

    op.create_table(
        "review_story_runs",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("local_date", sa.Date(), nullable=False),
        sa.Column("target_language", sa.String(length=10), nullable=False),
        sa.Column("feedback_language", sa.String(length=10), nullable=False),
        sa.Column("contract_version", sa.String(length=50), nullable=False),
        sa.Column("input_hash", sa.String(length=64), nullable=False),
        sa.Column("term_snapshot", postgresql.JSONB(), nullable=True),
        sa.Column("term_word_ids", postgresql.JSONB(), nullable=True),
        sa.Column("result_json", postgresql.JSONB(), nullable=True),
        sa.Column(
            "status",
            sa.String(length=20),
            nullable=False,
            server_default="pending",
        ),
        sa.Column(
            "attempt_count",
            sa.Integer(),
            nullable=False,
            server_default="0",
        ),
        sa.Column(
            "attempt_version",
            sa.Integer(),
            nullable=False,
            server_default="0",
        ),
        sa.Column("lease_expires_at", sa.DateTime(), nullable=True),
        sa.Column("error_code", sa.String(length=50), nullable=True),
        sa.Column("content_expires_at", sa.DateTime(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.CheckConstraint(
            "target_language IN ('fr','en','ja','de','es','ru','zh')",
            name="ck_review_story_runs_target_language",
        ),
        sa.CheckConstraint(
            "feedback_language IN ('zh','fr','en')",
            name="ck_review_story_runs_feedback_language",
        ),
        sa.CheckConstraint(
            "status IN ('pending','ready','failed')",
            name="ck_review_story_runs_status",
        ),
        sa.CheckConstraint(
            "attempt_count BETWEEN 0 AND 2",
            name="ck_review_story_runs_attempt_count",
        ),
        sa.CheckConstraint(
            "attempt_version >= 0",
            name="ck_review_story_runs_attempt_version",
        ),
        sa.CheckConstraint(
            "char_length(input_hash) = 64",
            name="ck_review_story_runs_input_hash",
        ),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "user_id",
            "local_date",
            "target_language",
            "feedback_language",
            "contract_version",
            "input_hash",
            name="uq_review_story_runs_input_identity",
        ),
    )
    op.create_index(
        "ix_review_story_runs_user_created",
        "review_story_runs",
        ["user_id", "created_at"],
    )
    op.create_index(
        "ix_review_story_runs_content_expiry",
        "review_story_runs",
        ["content_expires_at"],
    )

    op.create_table(
        "learning_funnel_events",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("event_type", sa.String(length=50), nullable=False),
        sa.Column("occurred_at", sa.DateTime(), nullable=False),
        sa.Column("dedupe_key", sa.String(length=64), nullable=False),
        sa.CheckConstraint(
            "event_type IN ("
            "'story_eligible_normal','story_eligible_strong',"
            "'story_generation_started','story_generation_ready',"
            "'story_generation_failed','story_cache_hit',"
            "'story_writing_handoff','story_output_saved')",
            name="ck_learning_funnel_events_type",
        ),
        sa.CheckConstraint(
            "char_length(dedupe_key) = 64",
            name="ck_learning_funnel_events_dedupe_key",
        ),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "user_id",
            "event_type",
            "dedupe_key",
            name="uq_learning_funnel_events_semantic_identity",
        ),
    )
    op.create_index(
        "ix_learning_funnel_events_user_occurred",
        "learning_funnel_events",
        ["user_id", "occurred_at"],
    )
    op.create_index(
        "ix_learning_funnel_events_type_occurred",
        "learning_funnel_events",
        ["event_type", "occurred_at"],
    )

    for table in ("review_story_runs", "learning_funnel_events"):
        op.execute(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY;")
        op.execute(f"ALTER TABLE {table} FORCE ROW LEVEL SECURITY;")
        _create_user_policies(table)


def downgrade():
    for table in ("learning_funnel_events", "review_story_runs"):
        for suffix in ("sel", "ins", "upd", "del"):
            op.execute(f"DROP POLICY IF EXISTS {table}_{suffix} ON {table};")
        op.execute(f"ALTER TABLE {table} NO FORCE ROW LEVEL SECURITY;")
        op.execute(f"ALTER TABLE {table} DISABLE ROW LEVEL SECURITY;")

    op.drop_index(
        "ix_learning_funnel_events_type_occurred",
        table_name="learning_funnel_events",
    )
    op.drop_index(
        "ix_learning_funnel_events_user_occurred",
        table_name="learning_funnel_events",
    )
    op.drop_table("learning_funnel_events")

    op.drop_index(
        "ix_review_story_runs_content_expiry",
        table_name="review_story_runs",
    )
    op.drop_index(
        "ix_review_story_runs_user_created",
        table_name="review_story_runs",
    )
    op.drop_table("review_story_runs")
    op.drop_index(
        "ix_review_logs_user_ts_word_grade",
        table_name="review_logs",
    )
