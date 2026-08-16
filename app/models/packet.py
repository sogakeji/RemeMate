"""Immutable feedback packets sent between linked language partners."""
from app.extensions import db
from app.services.timeutil import utc_now


class PartnerPacket(db.Model):
    __tablename__ = "partner_packets"
    __table_args__ = (
        db.CheckConstraint(
            "sender_user_id <> recipient_user_id",
            name="ck_partner_packets_distinct_users",
        ),
        db.CheckConstraint(
            "item_count BETWEEN 1 AND 20",
            name="ck_partner_packets_item_count",
        ),
        db.CheckConstraint(
            "language_code IS NULL OR "
            "language_code IN ('fr','en','ja','ko','de','es','ru','zh')",
            name="ck_partner_packets_language",
        ),
        db.UniqueConstraint(
            "sender_user_id", "recipient_user_id", "recap_id",
            "content_fingerprint",
            name="uq_partner_packets_exact_snapshot",
        ),
        db.UniqueConstraint(
            "id", "recipient_user_id",
            name="uq_partner_packets_id_recipient",
        ),
        db.ForeignKeyConstraint(
            ["partner_id", "sender_user_id", "recipient_user_id"],
            [
                "language_partners.id",
                "language_partners.user_id",
                "language_partners.linked_user_id",
            ],
            ondelete="RESTRICT",
        ),
        db.ForeignKeyConstraint(
            ["recap_id", "sender_user_id", "partner_id"],
            [
                "partner_recaps.id",
                "partner_recaps.user_id",
                "partner_recaps.partner_id",
            ],
            ondelete="RESTRICT",
        ),
        db.Index(
            "ix_partner_packets_recipient_created",
            "recipient_user_id", "created_at",
        ),
        db.Index(
            "ix_partner_packets_sender_recap",
            "sender_user_id", "recap_id", "created_at",
        ),
    )

    id = db.Column(db.Integer, primary_key=True)
    sender_user_id = db.Column(
        db.Integer, db.ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
    )
    recipient_user_id = db.Column(
        db.Integer, db.ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
    )
    partner_id = db.Column(db.Integer, nullable=False)
    recap_id = db.Column(db.Integer, nullable=False)
    sender_display_name = db.Column(db.String(100), nullable=False)
    recipient_display_name = db.Column(db.String(100), nullable=False)
    recap_title = db.Column(db.String(120), nullable=True)
    session_date = db.Column(db.Date, nullable=False)
    language_code = db.Column(db.String(10), nullable=True)
    content_fingerprint = db.Column(db.String(64), nullable=False)
    item_count = db.Column(db.Integer, nullable=False)
    created_at = db.Column(db.DateTime, default=utc_now, nullable=False)

    items = db.relationship(
        "PartnerPacketItem",
        backref="packet",
        cascade="all, delete-orphan",
        lazy="select",
        order_by="PartnerPacketItem.position",
    )
    thank = db.relationship(
        "PartnerPacketThank",
        backref="packet",
        cascade="all, delete-orphan",
        lazy="select",
        uselist=False,
    )


class PartnerPacketItem(db.Model):
    __tablename__ = "partner_packet_items"
    __table_args__ = (
        db.CheckConstraint(
            "kind IN ('expression','natural_phrase','correction','next_time')",
            name="ck_partner_packet_items_kind",
        ),
        db.CheckConstraint(
            "position >= 0",
            name="ck_partner_packet_items_position",
        ),
        db.UniqueConstraint(
            "packet_id", "position",
            name="uq_partner_packet_items_packet_position",
        ),
        db.UniqueConstraint(
            "id", "packet_id",
            name="uq_partner_packet_items_id_packet",
        ),
        db.Index(
            "ix_partner_packet_items_packet_position",
            "packet_id", "position",
        ),
    )

    id = db.Column(db.Integer, primary_key=True)
    packet_id = db.Column(
        db.Integer,
        db.ForeignKey("partner_packets.id", ondelete="CASCADE"),
        nullable=False,
    )
    kind = db.Column(db.String(30), nullable=False)
    content = db.Column(db.Text, nullable=False)
    position = db.Column(db.Integer, nullable=False)


class PartnerPacketThank(db.Model):
    __tablename__ = "partner_packet_thanks"
    __table_args__ = (
        db.ForeignKeyConstraint(
            ["packet_id", "recipient_user_id"],
            ["partner_packets.id", "partner_packets.recipient_user_id"],
            ondelete="CASCADE",
        ),
    )

    packet_id = db.Column(db.Integer, primary_key=True)
    recipient_user_id = db.Column(
        db.Integer,
        db.ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
    )
    thanked_at = db.Column(db.DateTime, default=utc_now, nullable=False)


class PartnerPacketIntake(db.Model):
    __tablename__ = "partner_packet_intakes"
    __table_args__ = (
        db.ForeignKeyConstraint(
            ["packet_id", "recipient_user_id"],
            ["partner_packets.id", "partner_packets.recipient_user_id"],
            ondelete="CASCADE",
        ),
        db.ForeignKeyConstraint(
            ["source_id", "recipient_user_id"],
            ["intake_sources.id", "intake_sources.user_id"],
            ondelete="CASCADE",
        ),
        db.UniqueConstraint(
            "source_id", name="uq_partner_packet_intakes_source",
        ),
    )

    packet_id = db.Column(db.Integer, primary_key=True)
    recipient_user_id = db.Column(
        db.Integer, db.ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
    )
    source_id = db.Column(db.Integer, nullable=False)
    created_at = db.Column(db.DateTime, default=utc_now, nullable=False)


class PartnerPacketItemAdoption(db.Model):
    __tablename__ = "partner_packet_item_adoptions"
    __table_args__ = (
        db.ForeignKeyConstraint(
            ["packet_item_id", "packet_id"],
            ["partner_packet_items.id", "partner_packet_items.packet_id"],
            ondelete="CASCADE",
        ),
        db.ForeignKeyConstraint(
            ["packet_id", "recipient_user_id"],
            ["partner_packets.id", "partner_packets.recipient_user_id"],
            ondelete="CASCADE",
        ),
        db.ForeignKeyConstraint(
            ["candidate_id", "recipient_user_id"],
            ["word_candidates.id", "word_candidates.user_id"],
            ondelete="CASCADE",
        ),
    )

    packet_item_id = db.Column(db.Integer, primary_key=True)
    packet_id = db.Column(db.Integer, nullable=False)
    recipient_user_id = db.Column(
        db.Integer, db.ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
    )
    candidate_id = db.Column(db.Integer, primary_key=True)
    created_at = db.Column(db.DateTime, default=utc_now, nullable=False)
