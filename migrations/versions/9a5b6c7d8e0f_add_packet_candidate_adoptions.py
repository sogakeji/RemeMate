"""add recipient-private packet candidate adoptions

Revision ID: 9a5b6c7d8e0f
Revises: 8f4a5b6c7d9e
Create Date: 2026-07-11
"""
from alembic import op
import sqlalchemy as sa


revision = "9a5b6c7d8e0f"
down_revision = "8f4a5b6c7d9e"
branch_labels = None
depends_on = None

UID = "NULLIF(current_setting('app.current_user_id', true), '')::int"


def upgrade():
    op.add_column(
        "partner_packets",
        sa.Column("language_code", sa.String(length=10), nullable=True),
    )
    op.execute("""
        UPDATE partner_packets p
        SET language_code = lp.learning_language_code
        FROM language_partners lp
        WHERE lp.id = p.partner_id
          AND lp.user_id = p.sender_user_id
          AND lp.linked_user_id = p.recipient_user_id
    """)
    op.create_check_constraint(
        "ck_partner_packets_language",
        "partner_packets",
        "language_code IS NULL OR "
        "language_code IN ('fr','en','ja','de','es','ru','zh')",
    )
    op.create_unique_constraint(
        "uq_partner_packet_items_id_packet",
        "partner_packet_items",
        ["id", "packet_id"],
    )

    op.create_table(
        "partner_packet_intakes",
        sa.Column("packet_id", sa.Integer(), nullable=False),
        sa.Column("recipient_user_id", sa.Integer(), nullable=False),
        sa.Column("source_id", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(
            ["recipient_user_id"], ["users.id"], ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["packet_id", "recipient_user_id"],
            ["partner_packets.id", "partner_packets.recipient_user_id"],
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["source_id", "recipient_user_id"],
            ["intake_sources.id", "intake_sources.user_id"],
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("packet_id"),
        sa.UniqueConstraint(
            "source_id", name="uq_partner_packet_intakes_source",
        ),
    )
    op.create_table(
        "partner_packet_item_adoptions",
        sa.Column("packet_item_id", sa.Integer(), nullable=False),
        sa.Column("packet_id", sa.Integer(), nullable=False),
        sa.Column("recipient_user_id", sa.Integer(), nullable=False),
        sa.Column("candidate_id", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(
            ["recipient_user_id"], ["users.id"], ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["packet_item_id", "packet_id"],
            ["partner_packet_items.id", "partner_packet_items.packet_id"],
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["packet_id", "recipient_user_id"],
            ["partner_packets.id", "partner_packets.recipient_user_id"],
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["candidate_id", "recipient_user_id"],
            ["word_candidates.id", "word_candidates.user_id"],
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("packet_item_id"),
    )

    for table in ("partner_packet_intakes", "partner_packet_item_adoptions"):
        op.execute(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY;")
        op.execute(f"ALTER TABLE {table} FORCE ROW LEVEL SECURITY;")
        op.execute(f"""
            CREATE POLICY {table}_sel ON {table} FOR SELECT
                USING (recipient_user_id = {UID});
            CREATE POLICY {table}_ins ON {table} FOR INSERT
                WITH CHECK (recipient_user_id = {UID});
        """)


def downgrade():
    for table in ("partner_packet_item_adoptions", "partner_packet_intakes"):
        op.execute(f"DROP POLICY IF EXISTS {table}_ins ON {table};")
        op.execute(f"DROP POLICY IF EXISTS {table}_sel ON {table};")
        op.execute(f"ALTER TABLE {table} NO FORCE ROW LEVEL SECURITY;")
        op.execute(f"ALTER TABLE {table} DISABLE ROW LEVEL SECURITY;")
        op.drop_table(table)
    op.drop_constraint(
        "uq_partner_packet_items_id_packet",
        "partner_packet_items",
        type_="unique",
    )
    op.drop_constraint(
        "ck_partner_packets_language",
        "partner_packets",
        type_="check",
    )
    op.drop_column("partner_packets", "language_code")
