"""句子广场点夯（公开内容，不开 RLS）。"""
from app.extensions import db
from app.services.timeutil import utc_now


class SentenceUpvote(db.Model):
    __tablename__ = "sentence_upvotes"
    __table_args__ = (
        db.UniqueConstraint("entry_id", "user_id", name="uq_sentence_upvote"),
    )

    id         = db.Column(db.Integer, primary_key=True)
    entry_id   = db.Column(db.Integer, db.ForeignKey("output_entries.id"), nullable=False)
    user_id    = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    created_at = db.Column(db.DateTime, default=utc_now, nullable=False)
