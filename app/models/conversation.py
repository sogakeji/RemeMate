"""AI 助教对话与消息。"""
from datetime import datetime

from app.extensions import db


class Conversation(db.Model):
    __tablename__ = "conversations"

    id         = db.Column(db.Integer, primary_key=True)
    user_id    = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    title      = db.Column(db.String(200))
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)

    messages = db.relationship("Message", backref="conversation",
                               cascade="all, delete-orphan")


class Message(db.Model):
    __tablename__ = "messages"

    id      = db.Column(db.Integer, primary_key=True)
    conv_id = db.Column(db.Integer, db.ForeignKey("conversations.id"), nullable=False)
    role    = db.Column(db.String(20), nullable=False)  # user / assistant / system
    content = db.Column(db.Text)
    ts      = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
