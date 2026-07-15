"""阅读收词 v1：加入后的去向感，以及候选/词库中的来源感。"""
import re
from contextlib import contextmanager

from flask import g
from sqlalchemy import event

from app.extensions import db
from app.models.intake import IntakeSource, WordCandidate
from app.models.reading import ReadingDocument
from app.services import intake as intake_svc
from app.services import words as words_svc
from app.services.reading import service as reading_svc
from app.services.reading.dictionary import DictionaryResult
from tests.helpers import login, provision_user


PW = "pw12345678"


class StubDictionary:
    def lookup(self, language_code, term):
        return DictionaryResult(
            term=term,
            normalized_term=term.lower(),
            language_code=language_code,
            part_of_speech="noun",
            meanings=[f"meaning for {term}"],
            examples=[],
            source="test",
            confidence=1.0,
            found=True,
        )


@contextmanager
def _rls_context(app, user_id):
    with app.test_request_context("/"):
        g.rls_uid = user_id
        try:
            yield
        finally:
            db.session.remove()


def _csrf(client, path="/"):
    page = client.get(path).get_data(as_text=True)
    match = re.search(r'name="csrf-token" content="([^"]+)"', page)
    return match.group(1)


def _reading_candidate(app, user_id, *, title="River Notes", term="cat"):
    sentence = f"The {term} rests beside the river."
    with _rls_context(app, user_id):
        document = reading_svc.create_document(
            user_id,
            language_code="en",
            title=title,
            source_filename="river.pdf",
            content_text=sentence,
            content_hash=f"reading-source-{user_id}-{term}",
            page_count=1,
        )
        start = sentence.index(term)
        lookup = reading_svc.lookup_term(
            user_id,
            document.id,
            term,
            start,
            start + len(term),
            dictionary=StubDictionary(),
        )
        result = reading_svc.add_lookup_to_candidate(user_id, lookup.id)
        source = db.session.get(IntakeSource, result["source_id"])
        return {
            "document_id": document.id,
            "lookup_id": lookup.id,
            "candidate_id": result["candidate_id"],
            "source_id": source.id,
            "list_id": source.word_list_id,
            "sentence": sentence,
        }


def test_ajax_add_stays_in_reader_and_exposes_review_destination(app, client):
    uid = provision_user(app, "reading-destination@t.com", PW)
    login(client, "reading-destination@t.com", PW)

    with _rls_context(app, uid):
        document = reading_svc.create_document(
            uid,
            language_code="en",
            title="Destination Test",
            source_filename="destination.pdf",
            content_text="A fox waits here.",
            content_hash="reading-destination-test",
            page_count=1,
        )
        lookup = reading_svc.lookup_term(
            uid, document.id, "fox", 2, 5, dictionary=StubDictionary(),
        )
        doc_id = document.id
        lookup_id = lookup.id

    response = client.post(
        f"/reading/lookups/{lookup_id}/add-candidate",
        data={"csrf_token": _csrf(client, f"/reading/{doc_id}")},
        headers={"X-Requested-With": "XMLHttpRequest"},
    )

    assert response.status_code == 200
    assert "Location" not in response.headers
    payload = response.get_json()
    assert payload["ok"] is True
    assert payload["state"] == "created"
    assert payload["candidate_id"]
    assert payload["source_id"]

    retry = client.post(
        f"/reading/lookups/{lookup_id}/add-candidate",
        data={"csrf_token": _csrf(client, f"/reading/{doc_id}")},
        headers={"X-Requested-With": "XMLHttpRequest"},
    )
    assert retry.status_code == 200
    assert retry.get_json()["state"] == "already-candidate"
    assert retry.get_json()["candidate_id"] == payload["candidate_id"]

    reader = client.get(f"/reading/{doc_id}").get_data(as_text=True)
    assert "candidate-feedback" in reader
    assert f'/intake/{payload["source_id"]}/candidates' in reader
    assert "已加入本篇候选词" in reader


def test_adding_an_ignored_linked_candidate_restores_it_to_pending(app, client):
    uid = provision_user(app, "reading-restore@t.com", PW)
    login(client, "reading-restore@t.com", PW)
    created = _reading_candidate(app, uid, term="fox")
    with _rls_context(app, uid):
        assert intake_svc.ignore_candidate(uid, created["candidate_id"])

    response = client.post(
        f'/reading/lookups/{created["lookup_id"]}/add-candidate',
        data={"csrf_token": _csrf(client, f'/reading/{created["document_id"]}')},
        headers={"X-Requested-With": "XMLHttpRequest"},
    )

    assert response.status_code == 200
    assert response.get_json()["state"] == "restored-candidate"
    with _rls_context(app, uid):
        candidate = db.session.get(WordCandidate, created["candidate_id"])
        assert candidate.status == "pending"


def test_candidate_review_labels_reading_source_and_sentence(app, client):
    uid = provision_user(app, "candidate-source@t.com", PW)
    login(client, "candidate-source@t.com", PW)
    created = _reading_candidate(app, uid)

    page = client.get(
        f'/intake/{created["source_id"]}/candidates'
    ).get_data(as_text=True)

    assert 'class="candidate-reading-source"' in page
    assert "来自《River Notes》" in page
    assert created["sentence"] in page


def test_candidate_review_does_not_fake_reading_source_for_text_import(app, client):
    uid = provision_user(app, "candidate-non-reading@t.com", PW)
    login(client, "candidate-non-reading@t.com", PW)
    with _rls_context(app, uid):
        word_list = words_svc.get_or_create_language_list(uid, "en")
        source = IntakeSource(
            user_id=uid,
            source_type="text_extract",
            language_code="en",
            word_list_id=word_list.id,
            original_name="notes.txt",
            status="done",
            total_segments=1,
            total_candidates=1,
        )
        db.session.add(source)
        db.session.flush()
        db.session.add(WordCandidate(
            source_id=source.id,
            user_id=uid,
            word="ordinary",
            source_example="This came from plain text.",
            status="pending",
        ))
        db.session.commit()
        source_id = source.id

    page = client.get(f"/intake/{source_id}/candidates").get_data(as_text=True)

    assert 'class="candidate-reading-source"' not in page
    assert "来自《notes.txt》" not in page


def test_candidate_review_keeps_filename_fallback_after_document_deletion(app, client):
    uid = provision_user(app, "candidate-deleted-document@t.com", PW)
    login(client, "candidate-deleted-document@t.com", PW)
    created = _reading_candidate(app, uid)
    with _rls_context(app, uid):
        assert reading_svc.delete_document(uid, created["document_id"])

    page = client.get(
        f'/intake/{created["source_id"]}/candidates'
    ).get_data(as_text=True)

    assert 'class="candidate-reading-source"' in page
    assert "来自《river.pdf》" in page
    assert created["sentence"] in page


def test_word_detail_shows_one_reading_source_block_without_example_duplicate(app, client):
    uid = provision_user(app, "word-reading-source@t.com", PW)
    login(client, "word-reading-source@t.com", PW)
    created = _reading_candidate(app, uid)
    with _rls_context(app, uid):
        assert intake_svc.accept_candidate(uid, created["candidate_id"])
        assert intake_svc.commit_intake_source(uid, created["source_id"]) == 1
        words_svc.add_word(
            uid,
            created["list_id"],
            "manualword",
            meaning="manual meaning",
            example="A manual example.",
        )

    page = client.get(f'/words/{created["list_id"]}').get_data(as_text=True)

    assert page.count('class="word-reading-source"') == 1
    assert "来自《River Notes》" in page
    assert page.count(created["sentence"]) == 1
    assert "manualword" in page


def test_reading_source_copy_follows_english_ui_locale(app, client):
    uid = provision_user(app, "reading-source-english@t.com", PW)
    login(client, "reading-source-english@t.com", PW)
    created = _reading_candidate(app, uid, title="River Notes")
    client.post(
        "/ui-language",
        data={
            "ui_locale": "en",
            "next": f'/intake/{created["source_id"]}/candidates',
        },
    )

    candidates = client.get(
        f'/intake/{created["source_id"]}/candidates'
    ).get_data(as_text=True)

    assert "From “River Notes”" in candidates
    assert "Original PDF context" in candidates
    assert "来自《River Notes》" not in candidates

    reader = client.get(f'/reading/{created["document_id"]}').get_data(as_text=True)
    assert "was added to this document\\u0027s candidates" in reader
    assert "is already in this document\\u0027s candidates" in reader

    with _rls_context(app, uid):
        assert intake_svc.accept_candidate(uid, created["candidate_id"])
        assert intake_svc.commit_intake_source(uid, created["source_id"]) == 1

    detail = client.get(f'/words/{created["list_id"]}').get_data(as_text=True)
    assert "From “River Notes”" in detail
    assert "Original PDF context" in detail


def test_reading_provenance_is_user_scoped_and_loaded_in_one_detail_request(app, client):
    owner_id = provision_user(app, "source-owner@t.com", PW)
    other_id = provision_user(app, "source-other@t.com", PW)
    owner = _reading_candidate(app, owner_id, term="cat")
    owner_second = _reading_candidate(app, owner_id, term="bird")
    other = _reading_candidate(app, other_id, term="dog")

    with _rls_context(app, owner_id):
        assert intake_svc.accept_candidate(owner_id, owner["candidate_id"])
        assert intake_svc.commit_intake_source(owner_id, owner["source_id"]) == 1
        owner_word_id = db.session.get(WordCandidate, owner["candidate_id"]).word_id
        assert intake_svc.accept_candidate(owner_id, owner_second["candidate_id"])
        assert intake_svc.commit_intake_source(owner_id, owner_second["source_id"]) == 1
        owner_second_word_id = db.session.get(
            WordCandidate, owner_second["candidate_id"],
        ).word_id

    with _rls_context(app, other_id):
        assert intake_svc.accept_candidate(other_id, other["candidate_id"])
        assert intake_svc.commit_intake_source(other_id, other["source_id"]) == 1
        other_word_id = db.session.get(WordCandidate, other["candidate_id"]).word_id

    statements = []

    def record_statement(_conn, _cursor, statement, _params, _context, _many):
        statements.append(statement)

    with _rls_context(app, owner_id):
        engine = db.engine
        event.listen(engine, "before_cursor_execute", record_statement)
        try:
            sources = words_svc.get_reading_sources_for_words(
                owner_id, [owner_word_id, owner_second_word_id, other_word_id],
            )
        finally:
            event.remove(engine, "before_cursor_execute", record_statement)

    assert set(sources) == {owner_word_id, owner_second_word_id}
    source_queries = [
        statement for statement in statements
        if "word_candidates" in statement and "intake_sources" in statement
    ]
    assert len(source_queries) == 1

    login(client, "source-owner@t.com", PW)
    statements.clear()
    with app.app_context():
        engine = db.engine
        event.listen(engine, "before_cursor_execute", record_statement)
        try:
            response = client.get(f'/words/{owner["list_id"]}')
        finally:
            event.remove(engine, "before_cursor_execute", record_statement)

    assert response.status_code == 200
    detail_source_queries = [
        statement for statement in statements
        if "word_candidates" in statement and "intake_sources" in statement
    ]
    assert len(detail_source_queries) == 1
