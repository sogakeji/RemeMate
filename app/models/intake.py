"""输入管道：来源、分段、候选词。"""
from datetime import datetime

from app.extensions import db


class IntakeSource(db.Model):
    __tablename__ = "intake_sources"

    id               = db.Column(db.Integer, primary_key=True)
    user_id          = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    source_type      = db.Column(db.String(20), nullable=False)  # csv / text_extract / quick_add
    language_code    = db.Column(db.String(10), nullable=False)
    word_list_id     = db.Column(db.Integer, db.ForeignKey("word_lists.id", ondelete="CASCADE"), nullable=False)
    original_name    = db.Column(db.String(200))
    status           = db.Column(db.String(20), default="processing")  # processing / done / error
    total_segments   = db.Column(db.Integer, default=0)
    total_candidates = db.Column(db.Integer, default=0)
    accepted_count   = db.Column(db.Integer, default=0)
    created_at       = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
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

    id             = db.Column(db.Integer, primary_key=True)
    source_id      = db.Column(db.Integer, db.ForeignKey("intake_sources.id", ondelete="CASCADE"), nullable=False)
    user_id        = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    word           = db.Column(db.String(200), nullable=False)
    part_of_speech = db.Column(db.String(50))
    meaning        = db.Column(db.Text)
    example        = db.Column(db.Text)
    note           = db.Column(db.Text)
    context_start  = db.Column(db.Integer, nullable=True)  # /extract 原文偏移，用于高亮
    context_end    = db.Column(db.Integer, nullable=True)
    status         = db.Column(db.String(20), default="pending")  # pending / accepted / ignored
    word_id        = db.Column(db.Integer, db.ForeignKey("words.id", ondelete="SET NULL"), nullable=True)  # commit 后填入；词删则断链
    created_at     = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
