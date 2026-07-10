"""SessionPad recap papers."""
from app.extensions import db
from app.services.timeutil import utc_now


class PartnerRecap(db.Model):
    __tablename__ = "partner_recaps"
    __table_args__ = (
        db.UniqueConstraint("id", "user_id",
                            name="uq_partner_recaps_id_user_id"),
        db.Index(
            "ix_partner_recaps_user_partner_date",
            "user_id", "partner_id", "session_date",
        ),
        db.ForeignKeyConstraint(
            ["partner_id", "user_id"],
            ["language_partners.id", "language_partners.user_id"],
            ondelete="CASCADE",
        ),
    )

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(
        db.Integer, db.ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
    )
    partner_id = db.Column(db.Integer, nullable=False)
    session_date = db.Column(db.Date, nullable=False)
    title = db.Column(db.String(120), nullable=True)
    created_at = db.Column(db.DateTime, default=utc_now, nullable=False)
    updated_at = db.Column(
        db.DateTime, default=utc_now, onupdate=utc_now, nullable=False,
    )


class PartnerRecapItem(db.Model):
    __tablename__ = "partner_recap_items"
    __table_args__ = (
        db.UniqueConstraint("id", "user_id",
                            name="uq_partner_recap_items_id_user_id"),
        db.Index(
            "ix_partner_recap_items_user_recap",
            "user_id", "recap_id", "created_at",
        ),
        db.CheckConstraint(
            "side IN ('for_me','for_partner')",
            name="ck_partner_recap_items_side",
        ),
        db.CheckConstraint(
            "kind IN ('expression','natural_phrase','correction','next_time',"
            "'private_note')",
            name="ck_partner_recap_items_kind",
        ),
        db.CheckConstraint(
            "side = 'for_partner' OR kind <> 'correction'",
            name="ck_partner_recap_items_correction_side",
        ),
        db.CheckConstraint(
            "side = 'for_me' OR kind <> 'private_note'",
            name="ck_partner_recap_items_private_note_side",
        ),
        db.ForeignKeyConstraint(
            ["recap_id", "user_id"],
            ["partner_recaps.id", "partner_recaps.user_id"],
            ondelete="CASCADE",
        ),
    )

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(
        db.Integer, db.ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
    )
    recap_id = db.Column(db.Integer, nullable=False)
    side = db.Column(db.String(20), nullable=False)
    kind = db.Column(db.String(30), nullable=False)
    content = db.Column(db.Text, nullable=False)
    created_at = db.Column(db.DateTime, default=utc_now, nullable=False)
    updated_at = db.Column(
        db.DateTime, default=utc_now, onupdate=utc_now, nullable=False,
    )
