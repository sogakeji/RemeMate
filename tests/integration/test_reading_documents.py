"""Reading document persistence constraints and cleanup."""
import pytest
from sqlalchemy import exc, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import configure_mappers

from app.models import ReadingDocument, ReadingLookup
from tests.helpers import make_user


def _insert_document(conn, user_id, *, language_code="en", content_hash="hash-1", page_count=1, title="Doc"):
    return conn.execute(text(
        "INSERT INTO reading_documents("
        "user_id, language_code, title, source_filename, content_text, "
        "content_hash, page_count, created_at, updated_at) "
        "VALUES (:user_id, :language_code, :title, :source_filename, "
        ":content_text, :content_hash, :page_count, now(), now()) "
        "RETURNING id"
    ), {
        "user_id": user_id,
        "language_code": language_code,
        "title": title,
        "source_filename": f"{title}.pdf",
        "content_text": "Hello world.",
        "content_hash": content_hash,
        "page_count": page_count,
    }).scalar()


def test_reading_models_use_jsonb_and_configure_mappers():
    configure_mappers()

    assert isinstance(ReadingDocument.__table__.c.last_position.type, JSONB)
    assert isinstance(ReadingLookup.__table__.c.dictionary_result_json.type, JSONB)


def test_reading_documents_unique_per_user_content_hash(bypass_engine):
    user_id = make_user(bypass_engine, "reader-a@example.com")

    with bypass_engine.begin() as conn:
        _insert_document(conn, user_id, content_hash="same-hash")
        with pytest.raises(exc.IntegrityError):
            _insert_document(conn, user_id, content_hash="same-hash")


def test_reading_documents_reject_unsupported_language(bypass_engine):
    user_id = make_user(bypass_engine, "reader-lang@example.com")

    with pytest.raises(exc.IntegrityError):
        with bypass_engine.begin() as conn:
            _insert_document(conn, user_id, language_code="de")


def test_reading_documents_reject_negative_page_count(bypass_engine):
    user_id = make_user(bypass_engine, "reader-pages@example.com")

    with pytest.raises(exc.IntegrityError):
        with bypass_engine.begin() as conn:
            _insert_document(conn, user_id, page_count=-1)


def _insert_source_and_candidate(conn, user_id):
    list_id = conn.execute(text(
        "INSERT INTO word_lists(user_id, name, language_code, created_at) "
        "VALUES (:user_id, 'L', 'en', now()) RETURNING id"
    ), {"user_id": user_id}).scalar()
    source_id = conn.execute(text(
        "INSERT INTO intake_sources(user_id, source_type, language_code, word_list_id, original_name, status, total_segments, total_candidates, accepted_count, created_at) "
        "VALUES (:user_id, 'text_extract', 'en', :list_id, 'src', 'done', 0, 0, 0, now()) RETURNING id"
    ), {"user_id": user_id, "list_id": list_id}).scalar()
    candidate_id = conn.execute(text(
        "INSERT INTO word_candidates(source_id, user_id, word, meaning, source_example, status, created_at) "
        "VALUES (:source_id, :user_id, 'hello', '你好', 'Hello world.', 'pending', now()) RETURNING id"
    ), {"source_id": source_id, "user_id": user_id}).scalar()
    return source_id, candidate_id


def test_reading_document_rejects_other_users_intake_source(bypass_engine):
    user_a = make_user(bypass_engine, "reader-source-owner@example.com")
    user_b = make_user(bypass_engine, "reader-source-other@example.com")

    with pytest.raises(exc.IntegrityError):
        with bypass_engine.begin() as conn:
            source_id, _ = _insert_source_and_candidate(conn, user_a)
            document_id = _insert_document(conn, user_b, content_hash="other-source-hash")
            conn.execute(text(
                "UPDATE reading_documents SET intake_source_id=:source_id WHERE id=:document_id"
            ), {"source_id": source_id, "document_id": document_id})


def test_reading_lookup_rejects_other_users_document(bypass_engine):
    user_a = make_user(bypass_engine, "reader-doc-owner@example.com")
    user_b = make_user(bypass_engine, "reader-doc-other@example.com")

    with pytest.raises(exc.IntegrityError):
        with bypass_engine.begin() as conn:
            document_id = _insert_document(conn, user_a, content_hash="owner-doc-hash")
            conn.execute(text(
                "INSERT INTO reading_lookups(document_id, user_id, term, normalized_term, language_code, created_at) "
                "VALUES (:document_id, :user_id, 'Hello', 'hello', 'en', now())"
            ), {"document_id": document_id, "user_id": user_b})


def test_reading_lookup_rejects_other_users_candidate(bypass_engine):
    user_a = make_user(bypass_engine, "reader-candidate-owner@example.com")
    user_b = make_user(bypass_engine, "reader-candidate-other@example.com")

    with pytest.raises(exc.IntegrityError):
        with bypass_engine.begin() as conn:
            _, candidate_id = _insert_source_and_candidate(conn, user_a)
            document_id = _insert_document(conn, user_b, content_hash="other-candidate-hash")
            conn.execute(text(
                "INSERT INTO reading_lookups(document_id, user_id, term, normalized_term, language_code, candidate_id, created_at) "
                "VALUES (:document_id, :user_id, 'Hello', 'hello', 'en', :candidate_id, now())"
            ), {"document_id": document_id, "user_id": user_b, "candidate_id": candidate_id})


def test_reading_cleanup_handles_document_lookup_candidate_links(bypass_engine):
    user_id = make_user(bypass_engine, "reader-cleanup@example.com")

    with bypass_engine.begin() as conn:
        list_id = conn.execute(text(
            "INSERT INTO word_lists(user_id, name, language_code, created_at) "
            "VALUES (:user_id, 'L', 'en', now()) RETURNING id"
        ), {"user_id": user_id}).scalar()
        source_id = conn.execute(text(
            "INSERT INTO intake_sources(user_id, source_type, language_code, word_list_id, original_name, status, total_segments, total_candidates, accepted_count, created_at) "
            "VALUES (:user_id, 'text_extract', 'en', :list_id, 'src', 'done', 0, 0, 0, now()) RETURNING id"
        ), {"user_id": user_id, "list_id": list_id}).scalar()
        candidate_id = conn.execute(text(
            "INSERT INTO word_candidates(source_id, user_id, word, meaning, source_example, status, created_at) "
            "VALUES (:source_id, :user_id, 'hello', '你好', 'Hello world.', 'pending', now()) RETURNING id"
        ), {"source_id": source_id, "user_id": user_id}).scalar()
        document_id = _insert_document(conn, user_id, content_hash="cleanup-hash")
        conn.execute(text(
            "UPDATE reading_documents SET intake_source_id=:source_id WHERE id=:document_id"
        ), {"source_id": source_id, "document_id": document_id})
        conn.execute(text(
            "INSERT INTO reading_lookups(document_id, user_id, term, normalized_term, language_code, candidate_id, created_at) "
            "VALUES (:document_id, :user_id, 'Hello', 'hello', 'en', :candidate_id, now())"
        ), {"document_id": document_id, "user_id": user_id, "candidate_id": candidate_id})

    with bypass_engine.begin() as conn:
        for table_name in [
            "reading_lookups",
            "word_candidates",
            "source_segments",
            "reading_documents",
            "intake_sources",
            "word_lists",
            "users",
        ]:
            conn.execute(text(f"DELETE FROM {table_name}"))

    with bypass_engine.connect() as conn:
        assert conn.execute(text("SELECT count(*) FROM users")).scalar() == 0


def test_deleting_intake_source_nulls_reading_document_reference(bypass_engine):
    user_id = make_user(bypass_engine, "reader-source-null@example.com")

    with bypass_engine.begin() as conn:
        source_id, _ = _insert_source_and_candidate(conn, user_id)
        document_id = _insert_document(conn, user_id, content_hash="source-null-hash")
        conn.execute(text(
            "UPDATE reading_documents SET intake_source_id=:source_id WHERE id=:document_id"
        ), {"source_id": source_id, "document_id": document_id})
        conn.execute(text("DELETE FROM reading_lookups"))
        conn.execute(text("DELETE FROM word_candidates WHERE source_id=:source_id"), {"source_id": source_id})
        conn.execute(text("DELETE FROM intake_sources WHERE id=:source_id"), {"source_id": source_id})
        row = conn.execute(text(
            "SELECT intake_source_id FROM reading_documents WHERE id=:document_id"
        ), {"document_id": document_id}).one()

    assert row[0] is None


def test_deleting_candidate_nulls_reading_lookup_reference(bypass_engine):
    user_id = make_user(bypass_engine, "reader-candidate-null@example.com")

    with bypass_engine.begin() as conn:
        source_id, candidate_id = _insert_source_and_candidate(conn, user_id)
        document_id = _insert_document(conn, user_id, content_hash="candidate-null-hash")
        lookup_id = conn.execute(text(
            "INSERT INTO reading_lookups(document_id, user_id, term, normalized_term, language_code, candidate_id, created_at) "
            "VALUES (:document_id, :user_id, 'Hello', 'hello', 'en', :candidate_id, now()) RETURNING id"
        ), {"document_id": document_id, "user_id": user_id, "candidate_id": candidate_id}).scalar()
        conn.execute(text("DELETE FROM word_candidates WHERE id=:candidate_id"), {"candidate_id": candidate_id})
        row = conn.execute(text(
            "SELECT candidate_id FROM reading_lookups WHERE id=:lookup_id"
        ), {"lookup_id": lookup_id}).one()

    assert row[0] is None


def test_composite_reading_owner_fks_are_set_null(bypass_engine):
    with bypass_engine.connect() as conn:
        actions = dict(conn.execute(text(
            "SELECT conname, confdeltype FROM pg_constraint "
            "WHERE conname IN ("
            "'fk_reading_documents_intake_source_owner', "
            "'fk_reading_lookups_candidate_owner')"
        )).all())

    assert actions == {
        "fk_reading_documents_intake_source_owner": "n",
        "fk_reading_lookups_candidate_owner": "n",
    }
