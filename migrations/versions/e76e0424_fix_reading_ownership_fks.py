"""fix reading ownership foreign keys

Revision ID: e76e0424
Revises: d4e5f6a7b8c9
Create Date: 2026-07-04
"""
from alembic import op


revision = 'e76e0424'
down_revision = 'd4e5f6a7b8c9'
branch_labels = None
depends_on = None


def upgrade():
    op.create_unique_constraint(
        'uq_intake_sources_id_user_id',
        'intake_sources',
        ['id', 'user_id'],
    )
    op.create_unique_constraint(
        'uq_word_candidates_id_user_id',
        'word_candidates',
        ['id', 'user_id'],
    )
    op.create_unique_constraint(
        'uq_reading_documents_id_user_id',
        'reading_documents',
        ['id', 'user_id'],
    )
    op.execute("""
        ALTER TABLE reading_documents
        ADD CONSTRAINT fk_reading_documents_intake_source_owner
        FOREIGN KEY (intake_source_id, user_id)
        REFERENCES intake_sources (id, user_id)
        ON DELETE SET NULL (intake_source_id)
    """)
    op.create_foreign_key(
        'fk_reading_lookups_document_owner',
        'reading_lookups',
        'reading_documents',
        ['document_id', 'user_id'],
        ['id', 'user_id'],
    )
    op.execute("""
        ALTER TABLE reading_lookups
        ADD CONSTRAINT fk_reading_lookups_candidate_owner
        FOREIGN KEY (candidate_id, user_id)
        REFERENCES word_candidates (id, user_id)
        ON DELETE SET NULL (candidate_id)
    """)


def downgrade():
    op.drop_constraint('fk_reading_lookups_candidate_owner', 'reading_lookups', type_='foreignkey')
    op.drop_constraint('fk_reading_lookups_document_owner', 'reading_lookups', type_='foreignkey')
    op.drop_constraint('fk_reading_documents_intake_source_owner', 'reading_documents', type_='foreignkey')
    op.drop_constraint('uq_reading_documents_id_user_id', 'reading_documents', type_='unique')
    op.drop_constraint('uq_word_candidates_id_user_id', 'word_candidates', type_='unique')
    op.drop_constraint('uq_intake_sources_id_user_id', 'intake_sources', type_='unique')
