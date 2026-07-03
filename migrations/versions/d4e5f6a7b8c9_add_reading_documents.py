"""add reading documents

Revision ID: d4e5f6a7b8c9
Revises: a7b8c9d0e1f2
Create Date: 2026-07-04
"""
from alembic import op
import sqlalchemy as sa


revision = 'd4e5f6a7b8c9'
down_revision = 'a7b8c9d0e1f2'
branch_labels = None
depends_on = None

UID = "NULLIF(current_setting('app.current_user_id', true), '')::int"


def _recreate_policy(name, table, stmt):
    op.execute(f"DROP POLICY IF EXISTS {name} ON {table};")
    op.execute(stmt)


def _create_user_policies(table):
    _recreate_policy(f"{table}_sel", table, f"""
        CREATE POLICY {table}_sel ON {table} FOR SELECT
            USING (user_id = {UID});
    """)
    _recreate_policy(f"{table}_ins", table, f"""
        CREATE POLICY {table}_ins ON {table} FOR INSERT
            WITH CHECK (user_id = {UID});
    """)
    _recreate_policy(f"{table}_upd", table, f"""
        CREATE POLICY {table}_upd ON {table} FOR UPDATE
            USING (user_id = {UID}) WITH CHECK (user_id = {UID});
    """)
    _recreate_policy(f"{table}_del", table, f"""
        CREATE POLICY {table}_del ON {table} FOR DELETE
            USING (user_id = {UID});
    """)


def upgrade():
    op.add_column('word_candidates', sa.Column('source_example', sa.Text(), nullable=True))

    op.create_table(
        'reading_documents',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('user_id', sa.Integer(), nullable=False),
        sa.Column('language_code', sa.String(length=10), nullable=False),
        sa.Column('title', sa.String(length=200), nullable=False),
        sa.Column('source_filename', sa.String(length=255), nullable=False),
        sa.Column('content_text', sa.Text(), nullable=False),
        sa.Column('content_hash', sa.String(length=128), nullable=False),
        sa.Column('page_count', sa.Integer(), nullable=False),
        sa.Column('last_position', sa.JSON(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.Column('updated_at', sa.DateTime(), nullable=False),
        sa.Column('intake_source_id', sa.Integer(), nullable=True),
        sa.CheckConstraint("language_code IN ('zh', 'en', 'ja', 'fr')", name='ck_reading_documents_language_code'),
        sa.CheckConstraint('page_count >= 0', name='ck_reading_documents_page_count_nonnegative'),
        sa.ForeignKeyConstraint(['intake_source_id'], ['intake_sources.id'], ondelete='SET NULL'),
        sa.ForeignKeyConstraint(['user_id'], ['users.id']),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('user_id', 'content_hash', name='uq_reading_documents_user_content_hash'),
    )
    op.create_index('ix_reading_documents_user_id', 'reading_documents', ['user_id'])
    op.create_index('ix_reading_documents_user_language', 'reading_documents', ['user_id', 'language_code'])
    op.create_index('ix_reading_documents_intake_source_id', 'reading_documents', ['intake_source_id'])

    op.create_table(
        'reading_lookups',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('document_id', sa.Integer(), nullable=False),
        sa.Column('user_id', sa.Integer(), nullable=False),
        sa.Column('term', sa.String(length=200), nullable=False),
        sa.Column('normalized_term', sa.String(length=200), nullable=True),
        sa.Column('language_code', sa.String(length=10), nullable=False),
        sa.Column('dictionary_result_json', sa.JSON(), nullable=True),
        sa.Column('context_sentence', sa.Text(), nullable=True),
        sa.Column('context_start', sa.Integer(), nullable=True),
        sa.Column('context_end', sa.Integer(), nullable=True),
        sa.Column('candidate_id', sa.Integer(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.CheckConstraint("language_code IN ('zh', 'en', 'ja', 'fr')", name='ck_reading_lookups_language_code'),
        sa.CheckConstraint('context_start IS NULL OR context_start >= 0', name='ck_reading_lookups_context_start_nonnegative'),
        sa.CheckConstraint('context_end IS NULL OR context_end >= 0', name='ck_reading_lookups_context_end_nonnegative'),
        sa.CheckConstraint('context_start IS NULL OR context_end IS NULL OR context_start < context_end', name='ck_reading_lookups_context_order'),
        sa.ForeignKeyConstraint(['candidate_id'], ['word_candidates.id'], ondelete='SET NULL'),
        sa.ForeignKeyConstraint(['document_id'], ['reading_documents.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['user_id'], ['users.id']),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index('ix_reading_lookups_user_document', 'reading_lookups', ['user_id', 'document_id'])
    op.create_index('ix_reading_lookups_user_normalized_term', 'reading_lookups', ['user_id', 'normalized_term'])
    op.create_index('ix_reading_lookups_candidate_id', 'reading_lookups', ['candidate_id'])

    for table in ('reading_documents', 'reading_lookups'):
        op.execute(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY;")
        op.execute(f"ALTER TABLE {table} FORCE ROW LEVEL SECURITY;")
        _create_user_policies(table)


def downgrade():
    for table in ('reading_lookups', 'reading_documents'):
        for suffix in ('sel', 'ins', 'upd', 'del'):
            op.execute(f"DROP POLICY IF EXISTS {table}_{suffix} ON {table};")
        op.execute(f"ALTER TABLE {table} NO FORCE ROW LEVEL SECURITY;")
        op.execute(f"ALTER TABLE {table} DISABLE ROW LEVEL SECURITY;")

    op.drop_index('ix_reading_lookups_candidate_id', table_name='reading_lookups')
    op.drop_index('ix_reading_lookups_user_normalized_term', table_name='reading_lookups')
    op.drop_index('ix_reading_lookups_user_document', table_name='reading_lookups')
    op.drop_table('reading_lookups')

    op.drop_index('ix_reading_documents_intake_source_id', table_name='reading_documents')
    op.drop_index('ix_reading_documents_user_language', table_name='reading_documents')
    op.drop_index('ix_reading_documents_user_id', table_name='reading_documents')
    op.drop_table('reading_documents')

    op.drop_column('word_candidates', 'source_example')
