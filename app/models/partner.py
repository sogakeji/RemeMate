"""Private language-partner records for SessionPad."""
from app.extensions import db
from app.services.timeutil import utc_now


class LanguagePartner(db.Model):
    __tablename__ = "language_partners"
    __table_args__ = (
        db.UniqueConstraint("id", "user_id",
                            name="uq_language_partners_id_user_id"),
        db.UniqueConstraint(
            "id", "user_id", "linked_user_id",
            name="uq_language_partners_id_user_linked_user",
        ),
        db.UniqueConstraint(
            "user_id", "linked_user_id",
            name="uq_language_partners_user_linked_user",
        ),
        db.Index("ix_language_partners_user_updated", "user_id", "updated_at"),
        db.CheckConstraint(
            "native_language_code IS NULL OR "
            "native_language_code IN ('fr','en','ja','ko','de','es','ru','zh')",
            name="ck_language_partners_native_language",
        ),
        db.CheckConstraint(
            "learning_language_code IS NULL OR "
            "learning_language_code IN ('fr','en','ja','ko','de','es','ru','zh')",
            name="ck_language_partners_learning_language",
        ),
        db.CheckConstraint(
            "linked_user_id IS NULL OR linked_user_id <> user_id",
            name="ck_language_partners_not_self_linked",
        ),
    )

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(
        db.Integer, db.ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
    )
    linked_user_id = db.Column(
        db.Integer, db.ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True, index=True,
    )
    invite_token_hash = db.Column(db.String(64), nullable=True)
    display_name = db.Column(db.String(100), nullable=False)
    native_language_code = db.Column(db.String(10), nullable=True)
    learning_language_code = db.Column(db.String(10), nullable=True)
    private_note = db.Column(db.Text, nullable=True)
    created_at = db.Column(db.DateTime, default=utc_now, nullable=False)
    updated_at = db.Column(
        db.DateTime, default=utc_now, onupdate=utc_now, nullable=False,
    )
