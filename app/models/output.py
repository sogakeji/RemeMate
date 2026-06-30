"""造句日记 / 句子广场内容（表 output_entries）。

同时承载私人草稿与广场公开句：RLS policy 按 is_public 做读例外（见 RLS migration）。
"""
from app.extensions import db
from app.services.timeutil import utc_now


class OutputEntry(db.Model):
    __tablename__ = "output_entries"

    id           = db.Column(db.Integer, primary_key=True)
    word_id      = db.Column(db.Integer, db.ForeignKey("words.id", ondelete="CASCADE"), nullable=False)
    user_id      = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    original     = db.Column(db.Text)                 # 用户原句
    corrected    = db.Column(db.Text)                 # AI 修正句
    feedback     = db.Column(db.Text)
    has_error    = db.Column(db.Boolean, default=False)
    translation  = db.Column(db.Text)                 # 母语翻译（批改时生成）
    is_public    = db.Column(db.Boolean, default=False, nullable=False)  # 是否公开到广场
    upvote_count = db.Column(db.Integer, default=0, nullable=False)      # 夯票冗余缓存
    is_nsfw      = db.Column(db.Boolean, default=False, nullable=False)  # 批改时返回
    created_at   = db.Column(db.DateTime, default=utc_now, nullable=False)
