"""匿名账号访问控制面模型。"""
from sqlalchemy import CheckConstraint, Index, text

from app.extensions import db
from app.services.timeutil import utc_now


class AuthChallenge(db.Model):
    __tablename__ = "auth_challenges"

    id = db.Column(db.Integer, primary_key=True)
    token_digest = db.Column(db.String(64), unique=True, nullable=False)
    purpose = db.Column(db.String(20), nullable=False)
    email = db.Column(db.String(255), nullable=False)
    user_id = db.Column(
        db.Integer,
        db.ForeignKey("users.id", ondelete="CASCADE"),
        nullable=True,
    )
    expires_at = db.Column(db.DateTime, nullable=False)
    consumed_at = db.Column(db.DateTime, nullable=True)
    created_at = db.Column(
        db.DateTime,
        default=utc_now,
        server_default=text("now()"),
        nullable=False,
    )

    __table_args__ = (
        CheckConstraint(
            "purpose IN ('registration', 'password_reset')",
            name="ck_auth_challenges_purpose",
        ),
        CheckConstraint(
            "(purpose = 'registration' AND user_id IS NULL) OR "
            "(purpose = 'password_reset' AND user_id IS NOT NULL)",
            name="ck_auth_challenges_purpose_user",
        ),
        Index(
            "ix_auth_challenges_email_purpose_created",
            "email", "purpose", "created_at",
        ),
        Index("ix_auth_challenges_expires_at", "expires_at"),
    )


class AuthMailEvent(db.Model):
    __tablename__ = "auth_mail_events"

    id = db.Column(db.Integer, primary_key=True)
    challenge_id = db.Column(
        db.Integer,
        db.ForeignKey("auth_challenges.id", ondelete="SET NULL"),
        nullable=True,
    )
    purpose = db.Column(db.String(30), nullable=False)
    email = db.Column(db.String(255), nullable=False)
    client_key_digest = db.Column(db.String(64), nullable=False)
    delivery_status = db.Column(db.String(20), nullable=False)
    provider_message_id = db.Column(db.String(255), nullable=True)
    created_at = db.Column(
        db.DateTime,
        default=utc_now,
        server_default=text("now()"),
        nullable=False,
    )

    __table_args__ = (
        CheckConstraint(
            "purpose IN ('registration', 'password_reset', 'account_guidance')",
            name="ck_auth_mail_events_purpose",
        ),
        CheckConstraint(
            "delivery_status IN ('reserved', 'sent', 'failed')",
            name="ck_auth_mail_events_delivery_status",
        ),
        Index(
            "ix_auth_mail_events_email_created",
            "email", "created_at",
        ),
        Index(
            "ix_auth_mail_events_client_key_created",
            "client_key_digest", "created_at",
        ),
        Index("ix_auth_mail_events_created_at", "created_at"),
    )
