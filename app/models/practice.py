from app.extensions import db
from app.services.timeutil import utc_now


class PracticeSession(db.Model):
    __tablename__ = "practice_sessions"
    __table_args__ = (
        db.CheckConstraint(
            "status IN ('active', 'completed', 'abandoned', 'blocked')",
            name="ck_practice_sessions_status",
        ),
        db.CheckConstraint(
            "current_position >= 0",
            name="ck_practice_sessions_current_position_nonnegative",
        ),
        db.Index(
            "ix_practice_sessions_user_created",
            "user_id", "created_at", "id",
        ),
    )

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(
        db.Integer, db.ForeignKey("users.id", ondelete="CASCADE"), nullable=False,
    )
    language_code = db.Column(db.String(10), nullable=False)
    status = db.Column(db.String(20), nullable=False, default="active")
    current_position = db.Column(db.Integer, nullable=False, default=0)
    voice_available = db.Column(db.Boolean, nullable=True)
    started_at = db.Column(db.DateTime, nullable=False, default=utc_now)
    completed_at = db.Column(db.DateTime, nullable=True)
    abandoned_at = db.Column(db.DateTime, nullable=True)
    blocked_at = db.Column(db.DateTime, nullable=True)
    created_at = db.Column(db.DateTime, nullable=False, default=utc_now)
    updated_at = db.Column(db.DateTime, nullable=False, default=utc_now)

    items = db.relationship(
        "PracticeItem",
        backref="practice_session",
        order_by="PracticeItem.position",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )


class PracticeItem(db.Model):
    __tablename__ = "practice_items"
    __table_args__ = (
        db.UniqueConstraint(
            "session_id", "position", name="uq_practice_items_session_position",
        ),
        db.UniqueConstraint(
            "session_id", "word_id", name="uq_practice_items_session_word",
        ),
        db.CheckConstraint(
            "position >= 0",
            name="ck_practice_items_position_nonnegative",
        ),
        db.CheckConstraint(
            "replay_count >= 0",
            name="ck_practice_items_replay_count_nonnegative",
        ),
        db.CheckConstraint(
            "answer_duration_ms IS NULL OR answer_duration_ms >= 0",
            name="ck_practice_items_answer_duration_nonnegative",
        ),
        db.Index(
            "ix_practice_items_session_position",
            "session_id", "position",
        ),
    )

    id = db.Column(db.Integer, primary_key=True)
    session_id = db.Column(
        db.Integer,
        db.ForeignKey("practice_sessions.id", ondelete="CASCADE"),
        nullable=False,
    )
    user_id = db.Column(
        db.Integer, db.ForeignKey("users.id", ondelete="CASCADE"), nullable=False,
    )
    word_id = db.Column(
        db.Integer, db.ForeignKey("words.id", ondelete="CASCADE"), nullable=False,
    )
    definition_id = db.Column(
        db.Integer, db.ForeignKey("definitions.id", ondelete="CASCADE"),
        nullable=False,
    )
    position = db.Column(db.Integer, nullable=False)
    sentence = db.Column(db.Text, nullable=False)
    target = db.Column(db.Text, nullable=False)
    meaning = db.Column(db.Text, nullable=True)
    submitted_answer = db.Column(db.Text, nullable=True)
    normalized_answer = db.Column(db.Text, nullable=True)
    is_correct = db.Column(db.Boolean, nullable=True)
    submitted_at = db.Column(db.DateTime, nullable=True)
    replay_count = db.Column(db.Integer, nullable=False, default=0)
    answer_duration_ms = db.Column(db.Integer, nullable=True)
    created_at = db.Column(db.DateTime, nullable=False, default=utc_now)
    updated_at = db.Column(db.DateTime, nullable=False, default=utc_now)
