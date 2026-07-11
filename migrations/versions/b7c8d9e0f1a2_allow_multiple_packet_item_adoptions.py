"""allow multiple candidate adoptions per packet item

Revision ID: b7c8d9e0f1a2
Revises: a6b7c8d9e0f1
Create Date: 2026-07-11
"""
from alembic import op
import sqlalchemy as sa


revision = "b7c8d9e0f1a2"
down_revision = "a6b7c8d9e0f1"
branch_labels = None
depends_on = None


def _drop_primary_key():
    bind = op.get_bind()
    name = sa.inspect(bind).get_pk_constraint(
        "partner_packet_item_adoptions",
    ).get("name")
    if name:
        op.drop_constraint(
            name, "partner_packet_item_adoptions", type_="primary",
        )


def upgrade():
    _drop_primary_key()
    op.create_primary_key(
        "pk_partner_packet_item_adoptions",
        "partner_packet_item_adoptions",
        ["packet_item_id", "candidate_id"],
    )


def downgrade():
    op.execute("""
        DELETE FROM partner_packet_item_adoptions newer
        USING partner_packet_item_adoptions older
        WHERE newer.packet_item_id = older.packet_item_id
          AND newer.candidate_id > older.candidate_id
    """)
    _drop_primary_key()
    op.create_primary_key(
        "partner_packet_item_adoptions_pkey",
        "partner_packet_item_adoptions",
        ["packet_item_id"],
    )
