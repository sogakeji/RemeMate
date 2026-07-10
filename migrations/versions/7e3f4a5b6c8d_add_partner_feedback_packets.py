"""add immutable partner feedback packets

Revision ID: 7e3f4a5b6c8d
Revises: 6d2e3f4a5b7c
Create Date: 2026-07-10
"""
from alembic import op
import sqlalchemy as sa


revision = "7e3f4a5b6c8d"
down_revision = "6d2e3f4a5b7c"
branch_labels = None
depends_on = None

UID = "NULLIF(current_setting('app.current_user_id', true), '')::int"


def upgrade():
    op.create_unique_constraint(
        "uq_language_partners_id_user_linked_user",
        "language_partners",
        ["id", "user_id", "linked_user_id"],
    )
    op.create_unique_constraint(
        "uq_partner_recaps_id_user_partner",
        "partner_recaps",
        ["id", "user_id", "partner_id"],
    )
    op.create_table(
        "partner_packets",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("sender_user_id", sa.Integer(), nullable=False),
        sa.Column("recipient_user_id", sa.Integer(), nullable=False),
        sa.Column("partner_id", sa.Integer(), nullable=False),
        sa.Column("recap_id", sa.Integer(), nullable=False),
        sa.Column("sender_display_name", sa.String(length=100), nullable=False),
        sa.Column("recipient_display_name", sa.String(length=100), nullable=False),
        sa.Column("recap_title", sa.String(length=120), nullable=True),
        sa.Column("session_date", sa.Date(), nullable=False),
        sa.Column("content_fingerprint", sa.String(length=64), nullable=False),
        sa.Column("item_count", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.CheckConstraint(
            "sender_user_id <> recipient_user_id",
            name="ck_partner_packets_distinct_users",
        ),
        sa.CheckConstraint(
            "item_count BETWEEN 1 AND 20",
            name="ck_partner_packets_item_count",
        ),
        sa.ForeignKeyConstraint(
            ["sender_user_id"], ["users.id"], ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["recipient_user_id"], ["users.id"], ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["partner_id", "sender_user_id", "recipient_user_id"],
            [
                "language_partners.id",
                "language_partners.user_id",
                "language_partners.linked_user_id",
            ],
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["recap_id", "sender_user_id", "partner_id"],
            [
                "partner_recaps.id",
                "partner_recaps.user_id",
                "partner_recaps.partner_id",
            ],
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "sender_user_id", "recipient_user_id", "recap_id",
            "content_fingerprint",
            name="uq_partner_packets_exact_snapshot",
        ),
    )
    op.create_index(
        "ix_partner_packets_recipient_created",
        "partner_packets",
        ["recipient_user_id", "created_at"],
    )
    op.create_index(
        "ix_partner_packets_sender_recap",
        "partner_packets",
        ["sender_user_id", "recap_id", "created_at"],
    )

    op.create_table(
        "partner_packet_items",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("packet_id", sa.Integer(), nullable=False),
        sa.Column("kind", sa.String(length=30), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("position", sa.Integer(), nullable=False),
        sa.CheckConstraint(
            "kind IN ('expression','natural_phrase','correction','next_time')",
            name="ck_partner_packet_items_kind",
        ),
        sa.CheckConstraint(
            "position >= 0",
            name="ck_partner_packet_items_position",
        ),
        sa.ForeignKeyConstraint(
            ["packet_id"], ["partner_packets.id"], ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "packet_id", "position",
            name="uq_partner_packet_items_packet_position",
        ),
    )
    op.create_index(
        "ix_partner_packet_items_packet_position",
        "partner_packet_items",
        ["packet_id", "position"],
    )

    op.execute("ALTER TABLE partner_packets ENABLE ROW LEVEL SECURITY;")
    op.execute("ALTER TABLE partner_packets FORCE ROW LEVEL SECURITY;")
    op.execute("ALTER TABLE partner_packet_items ENABLE ROW LEVEL SECURITY;")
    op.execute("ALTER TABLE partner_packet_items FORCE ROW LEVEL SECURITY;")
    op.execute(f"""
        CREATE POLICY partner_packets_sel ON partner_packets FOR SELECT
            USING (sender_user_id = {UID} OR recipient_user_id = {UID});
        CREATE POLICY partner_packets_ins ON partner_packets FOR INSERT
            WITH CHECK (sender_user_id = {UID});
        CREATE POLICY partner_packet_items_sel ON partner_packet_items FOR SELECT
            USING (EXISTS (
                SELECT 1 FROM partner_packets p
                WHERE p.id = packet_id
                  AND (p.sender_user_id = {UID} OR p.recipient_user_id = {UID})
            ));
        CREATE POLICY partner_packet_items_ins ON partner_packet_items FOR INSERT
            WITH CHECK (EXISTS (
                SELECT 1 FROM partner_packets p
                WHERE p.id = packet_id AND p.sender_user_id = {UID}
            ));
    """)


def downgrade():
    op.execute("DROP POLICY IF EXISTS partner_packet_items_ins ON partner_packet_items;")
    op.execute("DROP POLICY IF EXISTS partner_packet_items_sel ON partner_packet_items;")
    op.execute("DROP POLICY IF EXISTS partner_packets_ins ON partner_packets;")
    op.execute("DROP POLICY IF EXISTS partner_packets_sel ON partner_packets;")
    op.execute("ALTER TABLE partner_packet_items NO FORCE ROW LEVEL SECURITY;")
    op.execute("ALTER TABLE partner_packet_items DISABLE ROW LEVEL SECURITY;")
    op.execute("ALTER TABLE partner_packets NO FORCE ROW LEVEL SECURITY;")
    op.execute("ALTER TABLE partner_packets DISABLE ROW LEVEL SECURITY;")
    op.drop_index(
        "ix_partner_packet_items_packet_position",
        table_name="partner_packet_items",
    )
    op.drop_table("partner_packet_items")
    op.drop_index(
        "ix_partner_packets_sender_recap",
        table_name="partner_packets",
    )
    op.drop_index(
        "ix_partner_packets_recipient_created",
        table_name="partner_packets",
    )
    op.drop_table("partner_packets")
    op.drop_constraint(
        "uq_partner_recaps_id_user_partner",
        "partner_recaps",
        type_="unique",
    )
    op.drop_constraint(
        "uq_language_partners_id_user_linked_user",
        "language_partners",
        type_="unique",
    )
