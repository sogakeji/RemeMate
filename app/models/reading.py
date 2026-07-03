"""Reading documents and lookup history."""
from app.extensions import db
from app.services.timeutil import utc_now
from sqlalchemy import ForeignKeyConstraint


class ReadingDocument(db.Model):
    __tablename__ = "reading_documents"
    __table_args__ = (
        db.UniqueConstraint("id", "user_id", name="uq_reading_documents_id_user_id"),
        db.UniqueConstraint("user_id", "content_hash", name="uq_reading_documents_user_content_hash"),
        db.CheckConstraint("language_code IN ('zh', 'en', 'ja', 'fr')", name="ck_reading_documents_language_code"),
        db.CheckConstraint("page_count >= 0", name="ck_reading_documents_page_count_nonnegative"),
        ForeignKeyConstraint(["intake_source_id", "user_id"], ["intake_sources.id", "intake_sources.user_id"]),
    )

    id               = db.Column(db.Integer, primary_key=True)
    user_id          = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    language_code    = db.Column(db.String(10), nullable=False)
    title            = db.Column(db.String(200), nullable=False)
    source_filename  = db.Column(db.String(255), nullable=False)
    content_text     = db.Column(db.Text, nullable=False)
    content_hash     = db.Column(db.String(128), nullable=False)
    page_count       = db.Column(db.Integer, nullable=False)
    last_position    = db.Column(db.JSON, nullable=True)
    created_at       = db.Column(db.DateTime, default=utc_now, nullable=False)
    updated_at       = db.Column(db.DateTime, default=utc_now, onupdate=utc_now, nullable=False)
    intake_source_id = db.Column(db.Integer, db.ForeignKey("intake_sources.id", ondelete="SET NULL"), nullable=True)

    lookups = db.relationship("ReadingLookup", backref="document", cascade="all, delete-orphan", passive_deletes=True)


class ReadingLookup(db.Model):
    __tablename__ = "reading_lookups"
    __table_args__ = (
        db.CheckConstraint("language_code IN ('zh', 'en', 'ja', 'fr')", name="ck_reading_lookups_language_code"),
        db.CheckConstraint("context_start IS NULL OR context_start >= 0", name="ck_reading_lookups_context_start_nonnegative"),
        db.CheckConstraint("context_end IS NULL OR context_end >= 0", name="ck_reading_lookups_context_end_nonnegative"),
        db.CheckConstraint(
            "context_start IS NULL OR context_end IS NULL OR context_start < context_end",
            name="ck_reading_lookups_context_order",
        ),
        ForeignKeyConstraint(["document_id", "user_id"], ["reading_documents.id", "reading_documents.user_id"]),
        ForeignKeyConstraint(["candidate_id", "user_id"], ["word_candidates.id", "word_candidates.user_id"]),
    )

    id                     = db.Column(db.Integer, primary_key=True)
    document_id            = db.Column(db.Integer, db.ForeignKey("reading_documents.id", ondelete="CASCADE"), nullable=False)
    user_id                = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    term                   = db.Column(db.String(200), nullable=False)
    normalized_term        = db.Column(db.String(200), nullable=True)
    language_code          = db.Column(db.String(10), nullable=False)
    dictionary_result_json = db.Column(db.JSON, nullable=True)
    context_sentence       = db.Column(db.Text, nullable=True)
    context_start          = db.Column(db.Integer, nullable=True)
    context_end            = db.Column(db.Integer, nullable=True)
    candidate_id           = db.Column(db.Integer, db.ForeignKey("word_candidates.id", ondelete="SET NULL"), nullable=True)
    created_at             = db.Column(db.DateTime, default=utc_now, nullable=False)
