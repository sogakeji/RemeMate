"""add one-way partner packet thanks

Revision ID: 8f4a5b6c7d9e
Revises: 7e3f4a5b6c8d
Create Date: 2026-07-11
"""
from alembic import op
import sqlalchemy as sa


revision = "8f4a5b6c7d9e"
down_revision = "7e3f4a5b6c8d"
branch_labels = None
depends_on = None

UID = "NULLIF(current_setting('app.current_user_id', true), '')::int"


def upgrade():
    op.create_unique_constraint(
        "uq_partner_packets_id_recipient",
        "partner_packets",
        ["id", "recipient_user_id"],
    )
    op.create_table(
        "partner_packet_thanks",
        sa.Column("packet_id", sa.Integer(), nullable=False),
        sa.Column("recipient_user_id", sa.Integer(), nullable=False),
        sa.Column("thanked_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(
            ["recipient_user_id"], ["users.id"], ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["packet_id", "recipient_user_id"],
            ["partner_packets.id", "partner_packets.recipient_user_id"],
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("packet_id"),
    )
    op.execute("ALTER TABLE partner_packet_thanks ENABLE ROW LEVEL SECURITY;")
    op.execute("ALTER TABLE partner_packet_thanks FORCE ROW LEVEL SECURITY;")
    op.execute(f"""
        CREATE POLICY partner_packet_thanks_sel ON partner_packet_thanks
            FOR SELECT USING (EXISTS (
                SELECT 1 FROM partner_packets p
                WHERE p.id = packet_id
                  AND (p.sender_user_id = {UID} OR p.recipient_user_id = {UID})
            ));
        CREATE POLICY partner_packet_thanks_ins ON partner_packet_thanks
            FOR INSERT WITH CHECK (
                recipient_user_id = {UID}
                AND EXISTS (
                    SELECT 1 FROM partner_packets p
                    WHERE p.id = packet_id AND p.recipient_user_id = {UID}
                )
            );
    """)


def downgrade():
    op.execute("DROP POLICY IF EXISTS partner_packet_thanks_ins ON partner_packet_thanks;")
    op.execute("DROP POLICY IF EXISTS partner_packet_thanks_sel ON partner_packet_thanks;")
    op.execute("ALTER TABLE partner_packet_thanks NO FORCE ROW LEVEL SECURITY;")
    op.execute("ALTER TABLE partner_packet_thanks DISABLE ROW LEVEL SECURITY;")
    op.drop_table("partner_packet_thanks")
    op.drop_constraint(
        "uq_partner_packets_id_recipient",
        "partner_packets",
        type_="unique",
    )
