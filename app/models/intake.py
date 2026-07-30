"""输入管道：来源、分段、候选词。"""
from app.extensions import db
from app.services.timeutil import utc_now


class IntakeSource(db.Model):
    __tablename__ = "intake_sources"
    __table_args__ = (
        db.UniqueConstraint("id", "user_id", name="uq_intake_sources_id_user_id"),
    )

    id               = db.Column(db.Integer, primary_key=True)
    user_id          = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    source_type      = db.Column(db.String(20), nullable=False)  # csv / text_extract / quick_add / reading_pdf
    language_code    = db.Column(db.String(10), nullable=False)
    word_list_id     = db.Column(db.Integer, db.ForeignKey("word_lists.id", ondelete="CASCADE"), nullable=False)
    original_name    = db.Column(db.String(200))
    status           = db.Column(db.String(20), default="processing")  # processing / done / error
    total_segments   = db.Column(db.Integer, default=0)
    total_candidates = db.Column(db.Integer, default=0)
    accepted_count   = db.Column(db.Integer, default=0)
    created_at       = db.Column(db.DateTime, default=utc_now, nullable=False)
    completed_at     = db.Column(db.DateTime, nullable=True)


class SourceSegment(db.Model):
    __tablename__ = "source_segments"

    id            = db.Column(db.Integer, primary_key=True)
    source_id     = db.Column(db.Integer, db.ForeignKey("intake_sources.id", ondelete="CASCADE"), nullable=False)
    user_id       = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    segment_index = db.Column(db.Integer, nullable=False)
    raw_text      = db.Column(db.Text)


class WordCandidate(db.Model):
    __tablename__ = "word_candidates"
    __table_args__ = (
        db.UniqueConstraint("id", "user_id", name="uq_word_candidates_id_user_id"),
        db.CheckConstraint(
            "("
            "context_excerpt IS NULL AND context_provenance IS NULL"
            ") OR ("
            "context_excerpt IS NOT NULL "
            "AND context_provenance IS NOT NULL "
            "AND length(btrim(context_excerpt)) BETWEEN 1 AND 300 "
            "AND context_provenance IN ('source_quote', 'user_edited')"
            ")",
            name="ck_word_candidates_context_pair",
        ),
    )

    id             = db.Column(db.Integer, primary_key=True)
    source_id      = db.Column(db.Integer, db.ForeignKey("intake_sources.id", ondelete="CASCADE"), nullable=False)
    user_id        = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    word           = db.Column(db.String(200), nullable=False)
    part_of_speech = db.Column(db.String(50))
    meaning        = db.Column(db.Text)
    example        = db.Column(db.Text)
    source_example = db.Column(db.Text, nullable=True)
    context_excerpt = db.Column(db.Text, nullable=True)
    context_provenance = db.Column(db.String(20), nullable=True)
    note           = db.Column(db.Text)
    context_start  = db.Column(db.Integer, nullable=True)  # /extract 原文偏移，用于高亮
    context_end    = db.Column(db.Integer, nullable=True)
    status         = db.Column(db.String(20), default="pending")  # pending / accepted / ignored
    word_id        = db.Column(db.Integer, db.ForeignKey("words.id", ondelete="SET NULL"), nullable=True)  # commit 后填入；词删则断链
    created_at     = db.Column(db.DateTime, default=utc_now, nullable=False)


db.Index(
    "uq_word_candidates_active_source_word",
    WordCandidate.source_id,
    db.func.lower(db.func.btrim(WordCandidate.word)),
    unique=True,
    postgresql_where=WordCandidate.status.in_(("pending", "accepted")),
)
