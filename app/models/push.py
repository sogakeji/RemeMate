"""推送幂等记录（dispatch 写入，BYPASSRLS）。"""
from datetime import datetime

from app.extensions import db


class PushLog(db.Model):
    __tablename__ = "push_log"

    id              = db.Column(db.Integer, primary_key=True)
    idempotency_key = db.Column(db.String(200), unique=True, nullable=False)
    user_id         = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    push_type       = db.Column(db.String(30))  # review_reminder / daily_summary / podcast
    created_at      = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
