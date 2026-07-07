"""Reading service document, lookup, and candidate bridge behavior."""

from contextlib import contextmanager

import pytest

from app.extensions import db
from flask import g
from app.models.intake import IntakeSource, WordCandidate
from app.models.reading import ReadingDocument, ReadingLookup
from app.models.word import Definition, Word
from app.services import intake as intake_svc
from app.services import words as words_svc
from app.services.reading.dictionary import DictionaryResult
from app.services.reading import service as reading_svc
from tests.helpers import provision_user

PW = "pw12345678"


class StubDictionary:
    def lookup(self, language_code, term):
        normalized = term.strip().lower() if language_code in {"en", "fr"} else term.strip()
        return DictionaryResult(
            term=term,
            normalized_term=normalized,
            language_code=language_code,
            part_of_speech="noun",
            meanings=[f"meaning for {normalized}"],
            examples=["dictionary example must not win"],
            source="stub",
            confidence=0.9,
            found=True,
        )


def _user(app, email="reader@example.com"):
    return provision_user(app, email, PW)


@contextmanager
def _rls_context(app, user_id):
    with app.test_request_context("/"):
        g.rls_uid = user_id
        try:
            yield
        finally:
            db.session.remove()


def _document(user_id, **overrides):
    payload = {
        "language_code": "en",
        "title": "Reader Doc",
        "source_filename": "reader.pdf",
        "content_text": "First sentence. The cat purrs softly. Last sentence.",
        "content_hash": "hash-reader-doc",
        "page_count": 2,
    }
    payload.update(overrides)
    return reading_svc.create_document(user_id, **payload)


def _lookup(user_id, document=None, term="cat"):
    document = document or _document(user_id)
    start = document.content_text.index(term)
    return reading_svc.lookup_term(
        user_id,
        document.id,
        term,
        start,
        start + len(term),
        dictionary=StubDictionary(),
    )


def test_create_document_and_list_document(app):
    user_id = _user(app)
    other_user_id = _user(app, "other-reader@example.com")

    with _rls_context(app, user_id):
        document = _document(user_id)

        assert reading_svc.get_document(user_id, document.id).title == "Reader Doc"
        documents = reading_svc.list_documents(user_id)

        assert [doc.id for doc in documents] == [document.id]
        assert documents[0].source_filename == "reader.pdf"

    with _rls_context(app, other_user_id):
        _document(other_user_id, title="Other Doc", content_hash="other-hash")

    with _rls_context(app, user_id):
        assert [doc.id for doc in reading_svc.list_documents(user_id)] == [document.id]


def test_update_last_position_accepts_valid_schema(app):
    user_id = _user(app)

    with _rls_context(app, user_id):
        document = _document(user_id, content_text="abcdef")
        updated = reading_svc.update_last_position(
            user_id,
            document.id,
            {"char_offset": 6, "scroll_ratio": 1},
        )

        assert updated.last_position == {"char_offset": 6, "scroll_ratio": 1.0}


@pytest.mark.parametrize(
    "position",
    [
        {"char_offset": -1, "scroll_ratio": 0.5},
        {"char_offset": 7, "scroll_ratio": 0.5},
        {"char_offset": 3, "scroll_ratio": -0.01},
        {"char_offset": 3, "scroll_ratio": 1.01},
        {"char_offset": "3", "scroll_ratio": 0.5},
        {"char_offset": 3, "scroll_ratio": "0.5"},
        {"char_offset": 3},
        "not a dict",
    ],
)
def test_update_last_position_rejects_invalid_schema_and_ranges(app, position):
    user_id = _user(app)

    with _rls_context(app, user_id):
        document = _document(user_id, content_text="abcdef")

        with pytest.raises(ValueError):
            reading_svc.update_last_position(user_id, document.id, position)


def test_lookup_creates_reading_lookup_with_context_sentence(app):
    user_id = _user(app)

    with _rls_context(app, user_id):
        document = _document(user_id)
        lookup = _lookup(user_id, document)

        saved = ReadingLookup.query.filter_by(id=lookup.id, user_id=user_id).one()
        assert saved.document_id == document.id
        assert saved.term == "cat"
        assert saved.normalized_term == "cat"
        assert saved.context_sentence == "The cat purrs softly."
        assert saved.context_start == document.content_text.index("The")
        assert saved.context_end == saved.context_start + len("The cat purrs softly.")
        assert saved.dictionary_result_json["examples"] == ["dictionary example must not win"]


def test_add_lookup_creates_candidate_with_example_and_source_example(app):
    user_id = _user(app)

    with _rls_context(app, user_id):
        lookup = _lookup(user_id)
        result = reading_svc.add_lookup_to_candidate(user_id, lookup.id)

        assert result["state"] == "created"
        candidate = db_candidate(result["candidate_id"])
        assert candidate.word == "cat"
        assert candidate.meaning == "meaning for cat"
        assert candidate.part_of_speech == "noun"
        assert candidate.example == "The cat purrs softly."
        assert candidate.source_example == "The cat purrs softly."
        assert candidate.context_start == lookup.context_start
        assert candidate.context_end == lookup.context_end
        assert candidate.note == "来自《reader.pdf》"


def test_retry_after_linked_candidate_commit_returns_already_candidate(app):
    user_id = _user(app)

    with _rls_context(app, user_id):
        lookup = _lookup(user_id)
        result = reading_svc.add_lookup_to_candidate(user_id, lookup.id)
        candidate = db_candidate(result["candidate_id"])
        intake_svc.accept_candidate(user_id, candidate.id)
        intake_svc.commit_intake_source(user_id, candidate.source_id)

        retry = reading_svc.add_lookup_to_candidate(user_id, lookup.id)

        assert retry["state"] == "already-candidate"
        assert retry["candidate_id"] == candidate.id


def test_candidate_edit_cannot_override_final_definition_example(app):
    user_id = _user(app)

    with _rls_context(app, user_id):
        lookup = _lookup(user_id)
        result = reading_svc.add_lookup_to_candidate(user_id, lookup.id)
        candidate = db_candidate(result["candidate_id"])

        assert intake_svc.accept_candidate(user_id, candidate.id, {"example": "edited example"})
        assert intake_svc.commit_intake_source(user_id, candidate.source_id) == 1

        definition = Definition.query.join(Word).filter(Word.word == "cat").one()
        assert definition.example == "The cat purrs softly."


def test_two_lookups_from_one_document_reuse_one_intake_source(app):
    user_id = _user(app)

    with _rls_context(app, user_id):
        document = _document(
            user_id,
            content_text="The cat purrs softly. The dog barks loudly.",
        )
        cat_lookup = _lookup(user_id, document, "cat")
        dog_lookup = _lookup(user_id, document, "dog")

        first = reading_svc.add_lookup_to_candidate(user_id, cat_lookup.id)
        second = reading_svc.add_lookup_to_candidate(user_id, dog_lookup.id)
        db_document = ReadingDocument.query.get(document.id)
        source_ids = {
            db_candidate(first["candidate_id"]).source_id,
            db_candidate(second["candidate_id"]).source_id,
        }

        assert len(source_ids) == 1
        assert db_document.intake_source_id in source_ids
        source = IntakeSource.query.get(db_document.intake_source_id)
        assert source.source_type == "reading_pdf"
        assert source.language_code == "en"
        assert source.original_name == "reader.pdf"
        assert source.status == "done"
        assert source.total_segments == 0
        assert source.total_candidates == 2


def test_add_lookup_links_candidate_created_for_this_lookup_when_other_candidate_exists(app):
    user_id = _user(app)

    with _rls_context(app, user_id):
        document = _document(user_id)
        lookup = _lookup(user_id, document)
        word_list = words_svc.get_or_create_language_list(user_id, document.language_code)
        source = IntakeSource(
            user_id=user_id,
            source_type="reading_pdf",
            language_code=document.language_code,
            word_list_id=word_list.id,
            original_name=document.source_filename,
            status="done",
            total_segments=0,
        )
        db.session.add(source)
        db.session.flush()
        document.intake_source_id = source.id
        older_candidate = WordCandidate(
            source_id=source.id,
            user_id=user_id,
            word="aardvark",
            status="pending",
        )
        db.session.add(older_candidate)
        db.session.commit()

        result = reading_svc.add_lookup_to_candidate(user_id, lookup.id)

        candidate = db_candidate(result["candidate_id"])
        assert candidate.word == "cat"
        assert candidate.id != older_candidate.id
        assert ReadingLookup.query.get(lookup.id).candidate_id == candidate.id
        assert IntakeSource.query.get(source.id).total_candidates == 2


def test_separate_lookup_for_same_term_reuses_existing_candidate(app):
    user_id = _user(app)

    with _rls_context(app, user_id):
        document = _document(
            user_id,
            content_text="The cat purrs softly. Another cat sleeps.",
        )
        first_lookup = _lookup(user_id, document, "cat")
        second_start = document.content_text.index("cat", first_lookup.context_end)
        second_lookup = reading_svc.lookup_term(
            user_id,
            document.id,
            "cat",
            second_start,
            second_start + len("cat"),
            dictionary=StubDictionary(),
        )

        first = reading_svc.add_lookup_to_candidate(user_id, first_lookup.id)
        second = reading_svc.add_lookup_to_candidate(user_id, second_lookup.id)

        assert first["state"] == "created"
        assert second["state"] == "already-candidate"
        assert second["candidate_id"] == first["candidate_id"]
        assert WordCandidate.query.filter_by(user_id=user_id, word="cat").count() == 1
        assert ReadingLookup.query.get(second_lookup.id).candidate_id == first["candidate_id"]


def test_existing_word_in_same_language_returns_existing_word_state(app):
    user_id = _user(app)

    with _rls_context(app, user_id):
        word_list = words_svc.get_or_create_language_list(user_id, "en")
        existing = Word(list_id=word_list.id, word="cat")
        db.session.add(existing)
        db.session.commit()

        lookup = _lookup(user_id)
        result = reading_svc.add_lookup_to_candidate(user_id, lookup.id)

        assert result["state"] == "existing-word"
        assert result["word_id"] == existing.id
        # No IntakeSource should have been created (existing-word check now
        # happens before source creation).
        assert IntakeSource.query.filter_by(user_id=user_id).count() == 0
        assert WordCandidate.query.filter_by(user_id=user_id).count() == 0
        assert ReadingLookup.query.get(lookup.id).candidate_id is None


def test_create_reading_candidate_uses_normalized_term_for_dedup(app):
    """Different surface forms ('CATS' vs 'cat') that normalize to the same
    term via the dictionary must reuse one candidate, not create two."""
    user_id = _user(app)

    class NormalizingDict:
        def lookup(self, language_code, term):
            return DictionaryResult(
                term=term,
                normalized_term="cat",
                language_code=language_code,
                part_of_speech="noun",
                meanings=["meaning for cat"],
                examples=[],
                source="normalized",
                confidence=0.9,
                found=True,
            )

    with _rls_context(app, user_id):
        document = _document(
            user_id,
            content_text="The CATS sleep. A cat purrs.",
        )
        start_cats = document.content_text.index("CATS")
        lookup_cats = reading_svc.lookup_term(
            user_id, document.id, "CATS", start_cats, start_cats + 4,
            dictionary=NormalizingDict(),
        )
        start_cat = document.content_text.index("cat", start_cats + 1)
        lookup_cat = reading_svc.lookup_term(
            user_id, document.id, "cat", start_cat, start_cat + 3,
            dictionary=NormalizingDict(),
        )

        first = reading_svc.add_lookup_to_candidate(user_id, lookup_cats.id)
        second = reading_svc.add_lookup_to_candidate(user_id, lookup_cat.id)

        assert first["state"] == "created"
        assert second["state"] == "already-candidate"
        assert second["candidate_id"] == first["candidate_id"]
        assert WordCandidate.query.filter_by(user_id=user_id).count() == 1
        candidate = db_candidate(first["candidate_id"])
        assert candidate.word == "cat"  # normalized form, not surface form


def test_reading_candidate_commits_into_document_language_word_list(app):
    user_id = _user(app)

    with _rls_context(app, user_id):
        document = _document(
            user_id,
            language_code="fr",
            content_text="Le chat dort paisiblement.",
            content_hash="hash-fr-doc",
        )
        lookup = _lookup(user_id, document, "chat")
        result = reading_svc.add_lookup_to_candidate(user_id, lookup.id)
        candidate = db_candidate(result["candidate_id"])

        assert intake_svc.accept_candidate(user_id, candidate.id)
        assert intake_svc.commit_intake_source(user_id, candidate.source_id) == 1

        word = Word.query.filter_by(word="chat").one()
        word_list = words_svc.get_or_create_language_list(user_id, "fr")
        assert word.list_id == word_list.id


def db_candidate(candidate_id):
    return WordCandidate.query.get(candidate_id)
