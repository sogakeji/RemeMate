"""RLS coverage for reading documents and lookups."""
import pytest
from sqlalchemy import exc, text

from tests.helpers import make_user, set_uid


def _make_document(bypass_engine, user_id, *, content_hash="hash-1", title="Doc"):
    with bypass_engine.begin() as conn:
        return conn.execute(text(
            "INSERT INTO reading_documents("
            "user_id, language_code, title, source_filename, content_text, "
            "content_hash, page_count, created_at, updated_at) "
            "VALUES (:user_id, 'en', :title, :source_filename, 'Hello world.', "
            ":content_hash, 1, now(), now()) RETURNING id"
        ), {
            "user_id": user_id,
            "title": title,
            "source_filename": f"{title}.pdf",
            "content_hash": content_hash,
        }).scalar()


def test_reading_rls_unset_guc_fails_closed(app_engine, bypass_engine):
    user_id = make_user(bypass_engine, "reader-a@example.com")
    document_id = _make_document(bypass_engine, user_id)
    with bypass_engine.begin() as conn:
        conn.execute(text(
            "INSERT INTO reading_lookups(document_id, user_id, term, normalized_term, language_code, created_at) "
            "VALUES (:document_id, :user_id, 'Hello', 'hello', 'en', now())"
        ), {"document_id": document_id, "user_id": user_id})

    with app_engine.connect() as conn:
        assert conn.execute(text("SELECT count(*) FROM reading_documents")).scalar() == 0
        assert conn.execute(text("SELECT count(*) FROM reading_lookups")).scalar() == 0


def test_user_cannot_select_update_or_delete_other_users_reading_document(app_engine, bypass_engine):
    user_a = make_user(bypass_engine, "reader-owner@example.com")
    user_b = make_user(bypass_engine, "reader-other@example.com")
    document_id = _make_document(bypass_engine, user_a)

    with app_engine.begin() as conn:
        set_uid(conn, user_b)
        assert conn.execute(text("SELECT count(*) FROM reading_documents WHERE id=:id"), {"id": document_id}).scalar() == 0
        update_result = conn.execute(text(
            "UPDATE reading_documents SET title='Hacked' WHERE id=:id"
        ), {"id": document_id})
        delete_result = conn.execute(text(
            "DELETE FROM reading_documents WHERE id=:id"
        ), {"id": document_id})
        assert update_result.rowcount == 0
        assert delete_result.rowcount == 0

    with bypass_engine.connect() as conn:
        row = conn.execute(text(
            "SELECT title FROM reading_documents WHERE id=:id"
        ), {"id": document_id}).one()
        assert row[0] == "Doc"


def test_reading_insert_rejects_mismatched_user_id(app_engine, bypass_engine):
    user_a = make_user(bypass_engine, "reader-a@example.com")
    user_b = make_user(bypass_engine, "reader-b@example.com")

    with pytest.raises(exc.DatabaseError):
        with app_engine.begin() as conn:
            set_uid(conn, user_a)
            conn.execute(text(
                "INSERT INTO reading_documents("
                "user_id, language_code, title, source_filename, content_text, "
                "content_hash, page_count, created_at, updated_at) "
                "VALUES (:user_b, 'en', 'Mismatch', 'mismatch.pdf', 'Text', "
                "'mismatch-hash', 1, now(), now())"
            ), {"user_b": user_b})


def test_reading_update_rejects_mismatched_user_id(app_engine, bypass_engine):
    user_a = make_user(bypass_engine, "reader-a@example.com")
    user_b = make_user(bypass_engine, "reader-b@example.com")
    document_id = _make_document(bypass_engine, user_a)

    with pytest.raises(exc.DatabaseError):
        with app_engine.begin() as conn:
            set_uid(conn, user_a)
            conn.execute(text(
                "UPDATE reading_documents SET user_id=:user_b WHERE id=:document_id"
            ), {"user_b": user_b, "document_id": document_id})
