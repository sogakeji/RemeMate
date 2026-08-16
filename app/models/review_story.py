"""Private review-story cache and privacy-safe funnel events."""
from sqlalchemy.dialects.postgresql import JSONB

from app.extensions import db
from app.services.timeutil import utc_now


REVIEW_STORY_STATUSES = ("pending", "ready", "failed")
LEARNING_FUNNEL_EVENT_TYPES = (
    "story_eligible_normal",
    "story_eligible_strong",
    "story_generation_started",
    "story_generation_ready",
    "story_generation_failed",
    "story_cache_hit",
    "story_writing_handoff",
    "story_output_saved",
)


class ReviewStoryRun(db.Model):
    """One private cached generation identity.

    RS1 only establishes the storage boundary. The state machine and provider
    calls are implemented in RS2.
    """

    __tablename__ = "review_story_runs"
    __table_args__ = (
        db.UniqueConstraint(
            "user_id",
            "local_date",
            "target_language",
            "feedback_language",
            "contract_version",
            "input_hash",
            name="uq_review_story_runs_input_identity",
        ),
        db.CheckConstraint(
            "status IN ('pending','ready','failed')",
            name="ck_review_story_runs_status",
        ),
        db.CheckConstraint(
            "attempt_count BETWEEN 0 AND 2",
            name="ck_review_story_runs_attempt_count",
        ),
        db.CheckConstraint(
            "attempt_version >= 0",
            name="ck_review_story_runs_attempt_version",
        ),
        db.CheckConstraint(
            "target_language IN ('fr','en','ja','ko','de','es','ru','zh')",
            name="ck_review_story_runs_target_language",
        ),
        db.CheckConstraint(
            "feedback_language IN ('zh','fr','en','ja','ko','es')",
            name="ck_review_story_runs_feedback_language",
        ),
        db.CheckConstraint(
            "char_length(input_hash) = 64",
            name="ck_review_story_runs_input_hash",
        ),
        db.Index(
            "ix_review_story_runs_user_created",
            "user_id",
            "created_at",
        ),
        db.Index(
            "ix_review_story_runs_content_expiry",
            "content_expires_at",
        ),
    )

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(
        db.Integer,
        db.ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
    )
    local_date = db.Column(db.Date, nullable=False)
    target_language = db.Column(db.String(10), nullable=False)
    feedback_language = db.Column(db.String(10), nullable=False)
    contract_version = db.Column(db.String(50), nullable=False)
    input_hash = db.Column(db.String(64), nullable=False)
    # Both snapshots are private and short-lived. Internal ids are never sent
    # to a provider; RS2 uses term_word_ids only for validated writing handoff.
    term_snapshot = db.Column(JSONB, nullable=True)
    term_word_ids = db.Column(JSONB, nullable=True)
    result_json = db.Column(JSONB, nullable=True)
    status = db.Column(db.String(20), default="pending", nullable=False)
    attempt_count = db.Column(db.Integer, default=0, nullable=False)
    attempt_version = db.Column(db.Integer, default=0, nullable=False)
    lease_expires_at = db.Column(db.DateTime, nullable=True)
    error_code = db.Column(db.String(50), nullable=True)
    content_expires_at = db.Column(db.DateTime, nullable=True)
    created_at = db.Column(db.DateTime, default=utc_now, nullable=False)
    updated_at = db.Column(
        db.DateTime,
        default=utc_now,
        onupdate=utc_now,
        nullable=False,
    )


class LearningFunnelEvent(db.Model):
    """Content-free event used only for aggregate closed-beta observation."""

    __tablename__ = "learning_funnel_events"
    __table_args__ = (
        db.UniqueConstraint(
            "user_id",
            "event_type",
            "dedupe_key",
            name="uq_learning_funnel_events_semantic_identity",
        ),
        db.CheckConstraint(
            "event_type IN ("
            "'story_eligible_normal','story_eligible_strong',"
            "'story_generation_started','story_generation_ready',"
            "'story_generation_failed','story_cache_hit',"
            "'story_writing_handoff','story_output_saved')",
            name="ck_learning_funnel_events_type",
        ),
        db.CheckConstraint(
            "char_length(dedupe_key) = 64",
            name="ck_learning_funnel_events_dedupe_key",
        ),
        db.Index(
            "ix_learning_funnel_events_user_occurred",
            "user_id",
            "occurred_at",
        ),
        db.Index(
            "ix_learning_funnel_events_type_occurred",
            "event_type",
            "occurred_at",
        ),
    )

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(
        db.Integer,
        db.ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
    )
    event_type = db.Column(db.String(50), nullable=False)
    occurred_at = db.Column(db.DateTime, default=utc_now, nullable=False)
    dedupe_key = db.Column(db.String(64), nullable=False)
