"""用户、设置、额度、token 用量。"""
from datetime import datetime

from flask_login import UserMixin

from app.extensions import db


class User(db.Model, UserMixin):
    __tablename__ = "users"

    id             = db.Column(db.Integer, primary_key=True)
    email          = db.Column(db.String(255), unique=True, nullable=False)
    password_hash  = db.Column(db.String(255), nullable=False)
    display_name   = db.Column(db.String(100), nullable=False)
    role           = db.Column(db.String(20), default="user", nullable=False)  # user / admin
    is_active      = db.Column(db.Boolean, default=True, nullable=False)
    locked_until   = db.Column(db.DateTime, nullable=True)
    login_attempts = db.Column(db.Integer, default=0, nullable=False)
    timezone       = db.Column(db.String(50), default="Asia/Shanghai", nullable=False)
    # 当前正在学的语言（ui-rescope：首页切换器/设置页/词列表页共用，隐式词表闭环）
    current_language = db.Column(db.String(10), nullable=True)
    # 在学语言集合（修1）：设置页多选存储，逗号拼接（如 "fr,en,ja"），nullable 兼容老用户。
    # current_language 必须是集合子集（不变量由 service 收敛）。
    learning_languages = db.Column(db.String(200), nullable=True)
    created_at     = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)

    settings = db.relationship("UserSettings", backref="user", uselist=False)
    quota    = db.relationship("UserQuota", backref="user", uselist=False)


class UserSettings(db.Model):
    __tablename__ = "user_settings"

    user_id             = db.Column(db.Integer, db.ForeignKey("users.id"), primary_key=True)
    deepseek_key_enc    = db.Column(db.Text, nullable=True)      # DATA_ENCRYPTION_KEY 加密
    bark_url            = db.Column(db.String(500), nullable=True)
    webhook_url         = db.Column(db.String(500), nullable=True)
    podcast_token       = db.Column(db.String(100), nullable=True)
    podcast_public_base = db.Column(db.String(500), nullable=True)
    eudic_token_enc     = db.Column(db.Text, nullable=True)      # P2 预留
    # 通知开关（默认值见 dispatch-multiuser.md）
    notify_review_reminder  = db.Column(db.Boolean, default=True,  nullable=False)
    notify_daily_summary    = db.Column(db.Boolean, default=True,  nullable=False)
    notify_intake_done      = db.Column(db.Boolean, default=True,  nullable=False)
    notify_partner_activity = db.Column(db.Boolean, default=False, nullable=False)  # P2


class UserQuota(db.Model):
    __tablename__ = "user_quota"

    user_id            = db.Column(db.Integer, db.ForeignKey("users.id"), primary_key=True)
    daily_base_limit   = db.Column(db.Integer, default=50_000, nullable=False)
    tokens_used_today  = db.Column(db.Integer, default=0, nullable=False)
    bonus_tokens_today = db.Column(db.Integer, default=0, nullable=False)
    corrections_today  = db.Column(db.Integer, default=0, nullable=False)  # 今日造句批改次数（按提交计）
    imports_today      = db.Column(db.Integer, default=0, nullable=False)  # 今日导入候选词数（抽词/归一化时计）
    quota_reset_at     = db.Column(db.DateTime, nullable=True)  # create_user 时初始化，禁留 None
    updated_at         = db.Column(db.DateTime, default=datetime.utcnow)


class TokenUsageLog(db.Model):
    __tablename__ = "token_usage_log"

    id                = db.Column(db.Integer, primary_key=True)
    user_id           = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    provider          = db.Column(db.String(50))   # deepseek / openai / groq
    model             = db.Column(db.String(100))
    feature           = db.Column(db.String(50))    # extract / clean / write / tutor / nsfw
    prompt_tokens     = db.Column(db.Integer)
    completion_tokens = db.Column(db.Integer)
    used_user_key     = db.Column(db.Boolean, default=False)
    created_at        = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
