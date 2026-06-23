"""词库、词、释义、复习记录。"""
from datetime import datetime

from app.extensions import db


class WordList(db.Model):
    __tablename__ = "word_lists"

    id            = db.Column(db.Integer, primary_key=True)
    user_id       = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    name          = db.Column(db.String(200), nullable=False)
    language_code = db.Column(db.String(10), nullable=False)
    created_at    = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)

    words = db.relationship("Word", backref="word_list",
                            cascade="all, delete-orphan", passive_deletes=True)


class Word(db.Model):
    __tablename__ = "words"

    id          = db.Column(db.Integer, primary_key=True)
    list_id     = db.Column(db.Integer, db.ForeignKey("word_lists.id", ondelete="CASCADE"), nullable=False)
    word        = db.Column(db.String(200), nullable=False)
    marked      = db.Column(db.Boolean, default=False, nullable=False)
    # SM-2 字段（P1 使用）
    due_date    = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    interval    = db.Column(db.Integer, default=1, nullable=False)
    ease        = db.Column(db.Float, default=2.5, nullable=False)
    reps        = db.Column(db.Integer, default=0, nullable=False)
    lapses      = db.Column(db.Integer, default=0, nullable=False)
    last_review = db.Column(db.DateTime, nullable=True)
    # FSRS 预留（P2 切换时填入）
    stability   = db.Column(db.Float, nullable=True)
    difficulty  = db.Column(db.Float, nullable=True)

    definitions = db.relationship("Definition", backref="word",
                                  cascade="all, delete-orphan", passive_deletes=True)


class Definition(db.Model):
    __tablename__ = "definitions"

    id             = db.Column(db.Integer, primary_key=True)
    word_id        = db.Column(db.Integer, db.ForeignKey("words.id", ondelete="CASCADE"), nullable=False)
    part_of_speech = db.Column(db.String(50))
    meaning        = db.Column(db.Text)
    example        = db.Column(db.Text)
    note           = db.Column(db.Text)


class ReviewLog(db.Model):
    __tablename__ = "review_logs"

    id             = db.Column(db.Integer, primary_key=True)
    word_id        = db.Column(db.Integer, db.ForeignKey("words.id", ondelete="CASCADE"), nullable=False)
    user_id        = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    ts             = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    grade          = db.Column(db.Integer)        # SM-2 质量分 0-5
    source         = db.Column(db.String(20))     # review / write 等
    interval_after = db.Column(db.Integer)
    # FSRS 预留
    stability_after  = db.Column(db.Float, nullable=True)
    difficulty_after = db.Column(db.Float, nullable=True)
