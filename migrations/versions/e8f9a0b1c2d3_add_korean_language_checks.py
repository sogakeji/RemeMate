"""allow Korean in language-partner packet constraints

Revision ID: e8f9a0b1c2d3
Revises: e7f8a9b0c1d2
"""
from alembic import op


revision = "e8f9a0b1c2d3"
down_revision = "e7f8a9b0c1d2"
branch_labels = None
depends_on = None


def upgrade():
    op.drop_constraint(
        "ck_language_partners_native_language",
        "language_partners",
        type_="check",
    )
    op.create_check_constraint(
        "ck_language_partners_native_language",
        "language_partners",
        "native_language_code IS NULL OR "
        "native_language_code IN ('fr','en','ja','ko','de','es','ru','zh')",
    )
    op.drop_constraint(
        "ck_language_partners_learning_language",
        "language_partners",
        type_="check",
    )
    op.create_check_constraint(
        "ck_language_partners_learning_language",
        "language_partners",
        "learning_language_code IS NULL OR "
        "learning_language_code IN ('fr','en','ja','ko','de','es','ru','zh')",
    )
    op.drop_constraint(
        "ck_partner_packets_language",
        "partner_packets",
        type_="check",
    )
    op.create_check_constraint(
        "ck_partner_packets_language",
        "partner_packets",
        "language_code IS NULL OR "
        "language_code IN ('fr','en','ja','ko','de','es','ru','zh')",
    )


def downgrade():
    op.drop_constraint(
        "ck_partner_packets_language", "partner_packets", type_="check",
    )
    op.create_check_constraint(
        "ck_partner_packets_language",
        "partner_packets",
        "language_code IS NULL OR "
        "language_code IN ('fr','en','ja','de','es','ru','zh')",
    )
    op.drop_constraint(
        "ck_language_partners_learning_language",
        "language_partners",
        type_="check",
    )
    op.create_check_constraint(
        "ck_language_partners_learning_language",
        "language_partners",
        "learning_language_code IS NULL OR "
        "learning_language_code IN ('fr','en','ja','de','es','ru','zh')",
    )
    op.drop_constraint(
        "ck_language_partners_native_language",
        "language_partners",
        type_="check",
    )
    op.create_check_constraint(
        "ck_language_partners_native_language",
        "language_partners",
        "native_language_code IS NULL OR "
        "native_language_code IN ('fr','en','ja','de','es','ru','zh')",
    )
