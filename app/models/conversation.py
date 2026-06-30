"""AI 助教对话与消息。"""
from app.extensions import db
from app.services.timeutil import utc_now


class Conversation(db.Model):
    __tablename__ = "conversations"

    id         = db.Column(db.Integer, primary_key=True)
    user_id    = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    title      = db.Column(db.String(200))
    created_at = db.Column(db.DateTime, default=utc_now, nullable=False)

    messages = db.relationship("Message", backref="conversation",
                               cascade="all, delete-orphan")


class Message(db.Model):
    __tablename__ = "messages"

    id      = db.Column(db.Integer, primary_key=True)
    conv_id = db.Column(db.Integer, db.ForeignKey("conversations.id"), nullable=False)
    role    = db.Column(db.String(20), nullable=False)  # user / assistant / system
    content = db.Column(db.Text)
    ts      = db.Column(db.DateTime, default=utc_now, nullable=False)
