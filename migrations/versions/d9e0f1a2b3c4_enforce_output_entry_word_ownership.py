"""enforce output entry word ownership in RLS

Revision ID: d9e0f1a2b3c4
Revises: c8d9e0f1a2b3
"""
from alembic import op


revision = "d9e0f1a2b3c4"
down_revision = "c8d9e0f1a2b3"
branch_labels = None
depends_on = None


UID = "NULLIF(current_setting('app.current_user_id', true), '')::int"
OWNED_WORD = f"""(
    word_id IS NULL OR word_id IN (
        SELECT w.id
        FROM words AS w
        JOIN word_lists AS wl ON wl.id = w.list_id
        WHERE wl.user_id = {UID}
    )
)"""


def _replace_write_policies(insert_check, update_check):
    op.execute("DROP POLICY IF EXISTS oe_ins ON output_entries;")
    op.execute("DROP POLICY IF EXISTS oe_upd ON output_entries;")
    op.execute(f"""
        CREATE POLICY oe_ins ON output_entries FOR INSERT
            WITH CHECK ({insert_check});
    """)
    op.execute(f"""
        CREATE POLICY oe_upd ON output_entries FOR UPDATE
            USING (user_id = {UID})
            WITH CHECK ({update_check});
    """)


def upgrade():
    owned_entry = f"user_id = {UID} AND {OWNED_WORD}"
    _replace_write_policies(owned_entry, owned_entry)


def downgrade():
    own_user = f"user_id = {UID}"
    _replace_write_policies(own_user, own_user)
