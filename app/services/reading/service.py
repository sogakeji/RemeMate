from __future__ import annotations

import hashlib
import math
from numbers import Real
from typing import Any

from app.extensions import db
from app.models.intake import IntakeSource, WordCandidate
from app.models.reading import ReadingDocument, ReadingLookup
from app.models.word import Word
from app.services import words as words_svc
from app.services.reading.context import extract_context_sentence
from app.services.reading.dictionary import Dictionary, SUPPORTED_LANGUAGES


# Module-level singleton so the 17 MB JSON is parsed once per process
_dict = Dictionary()


class ReadingNotFound(ValueError):
    pass


def create_document(
    user_id: int,
    *,
    language_code: str,
    title: str,
    source_filename: str | None,
    content_text: str,
    content_hash: str | None = None,
    page_count: int = 0,
) -> ReadingDocument:
    if language_code not in SUPPORTED_LANGUAGES:
        raise ValueError("unsupported reading language")
    title = (title or "").strip()
    source_filename = (source_filename or title).strip()
    content_text = content_text or ""
    if not title:
        raise ValueError("title is required")
    if page_count < 0:
        raise ValueError("page_count must be nonnegative")

    content_hash = content_hash or _content_hash(content_text)
    existing = ReadingDocument.query.filter_by(
        user_id=user_id, content_hash=content_hash
    ).first()
    if existing is not None:
        return existing

    document = ReadingDocument(
        user_id=user_id,
        language_code=language_code,
        title=title[:200],
        source_filename=source_filename[:255],
        content_text=content_text,
        content_hash=content_hash,
        page_count=page_count,
    )
    db.session.add(document)
    db.session.commit()
    return document


def get_document(user_id: int, document_id: int) -> ReadingDocument | None:
    return ReadingDocument.query.filter_by(id=document_id, user_id=user_id).first()


def list_documents(user_id: int, *, language_code: str | None = None) -> list[ReadingDocument]:
    q = ReadingDocument.query.filter_by(user_id=user_id)
    if language_code:
        q = q.filter_by(language_code=language_code)
    return q.order_by(ReadingDocument.updated_at.desc(), ReadingDocument.id.desc()).all()


def delete_document(user_id: int, document_id: int) -> bool:
    document = get_document(user_id, document_id)
    if document is None:
        return False
    db.session.delete(document)
    db.session.commit()
    return True


def update_last_position(user_id: int, document_id: int, position: Any) -> ReadingDocument:
    document = _require_document(user_id, document_id)
    document.last_position = _validate_position(position, len(document.content_text or ""))
    db.session.commit()
    return document


def lookup_term(
    user_id: int,
    document_id: int,
    term: str,
    selection_start: int,
    selection_end: int,
    *,
    dictionary: Dictionary | None = None,
) -> ReadingLookup:
    document = _require_document(user_id, document_id)
    term = (term or "").strip()
    if not term:
        raise ValueError("term is required")
    if not _is_int(selection_start) or not _is_int(selection_end):
        raise ValueError("selection offsets must be integers")
    if not 0 <= selection_start < selection_end <= len(document.content_text or ""):
        raise ValueError("selection offsets out of range")

    dictionary = dictionary or _dict
    result = dictionary.lookup(document.language_code, term)
    context = extract_context_sentence(
        document.content_text or "",
        selection_start,
        selection_end,
        document.language_code,
        expected_term=term,
    )

    lookup = ReadingLookup(
        document_id=document.id,
        user_id=user_id,
        term=term,
        normalized_term=result.normalized_term,
        language_code=document.language_code,
        dictionary_result_json=result.as_json(),
        context_sentence=context.sentence,
        context_start=context.start,
        context_end=context.end,
    )
    db.session.add(lookup)
    db.session.commit()
    return lookup


def add_lookup_to_candidate(user_id: int, lookup_id: int) -> dict[str, Any]:
    lookup = (
        ReadingLookup.query
        .filter_by(id=lookup_id, user_id=user_id)
        .with_for_update()
        .first()
    )
    if lookup is None:
        raise ReadingNotFound("reading lookup not found")
    document = _locked_document(user_id, lookup.document_id)
    word_list = words_svc.get_or_create_language_list(user_id, document.language_code)

    if lookup.candidate_id:
        return {"state": "already-candidate", "candidate_id": lookup.candidate_id,
                "source_id": document.intake_source_id, "term": lookup.term}

    # Check existing committed word BEFORE creating any source, so we don't
    # leave a dangling source row if the term is already in the word list.
    existing_word = _find_existing_word(word_list.id, lookup.normalized_term or lookup.term)
    if existing_word is not None:
        return {"state": "existing-word", "word_id": existing_word.id,
                "source_id": document.intake_source_id, "term": lookup.term}

    source = _source_for_document(user_id, document, word_list.id)
    existing_candidate = _find_existing_candidate(source.id, user_id, lookup.normalized_term or lookup.term)
    if existing_candidate is not None:
        lookup.candidate_id = existing_candidate.id
        db.session.commit()
        return {"state": "already-candidate", "candidate_id": existing_candidate.id,
                "source_id": source.id, "term": lookup.term}

    candidate = _create_candidate(user_id, source, _candidate_item(document, lookup))
    source.total_candidates = WordCandidate.query.filter_by(source_id=source.id, user_id=user_id).count()
    lookup.candidate_id = candidate.id
    db.session.commit()
    return {"state": "created", "candidate_id": candidate.id, "source_id": source.id,
            "term": lookup.term}


def _validate_position(position: Any, content_length: int) -> dict[str, float | int]:
    if not isinstance(position, dict):
        raise ValueError("position must be an object")
    if set(position.keys()) != {"char_offset", "scroll_ratio"}:
        raise ValueError("position must include char_offset and scroll_ratio")

    char_offset = position["char_offset"]
    scroll_ratio = position["scroll_ratio"]
    if not _is_int(char_offset):
        raise ValueError("char_offset must be an integer")
    if not _is_number(scroll_ratio):
        raise ValueError("scroll_ratio must be numeric")
    if char_offset < 0 or char_offset > content_length:
        raise ValueError("char_offset out of range")
    if scroll_ratio < 0 or scroll_ratio > 1:
        raise ValueError("scroll_ratio out of range")
    return {"char_offset": int(char_offset), "scroll_ratio": float(scroll_ratio)}


def _source_for_document(user_id: int, document: ReadingDocument, word_list_id: int) -> IntakeSource:
    if document.intake_source_id:
        source = IntakeSource.query.filter_by(
            id=document.intake_source_id,
            user_id=user_id,
            source_type="reading_pdf",
        ).with_for_update().first()
        if source is not None:
            return source

    source = IntakeSource(
        user_id=user_id,
        source_type="reading_pdf",
        language_code=document.language_code,
        word_list_id=word_list_id,
        original_name=document.source_filename or document.title,
        status="done",
        total_segments=0,
    )
    db.session.add(source)
    db.session.flush()
    document.intake_source_id = source.id
    db.session.flush()
    return source


def _create_candidate(user_id: int, source: IntakeSource, item: dict[str, Any]) -> WordCandidate:
    word = (item.get("word") or "").strip()
    if not word:
        raise ValueError("candidate word is required")
    candidate = WordCandidate(
        source_id=source.id,
        user_id=user_id,
        word=word,
        part_of_speech=item.get("part_of_speech"),
        meaning=item.get("meaning"),
        example=item.get("example"),
        source_example=item.get("source_example"),
        note=item.get("note"),
        context_start=item.get("context_start"),
        context_end=item.get("context_end"),
        status="pending",
    )
    db.session.add(candidate)
    db.session.flush()
    return candidate


def _find_existing_candidate(source_id: int, user_id: int, term: str) -> WordCandidate | None:
    normalized = (term or "").strip().lower()
    if not normalized:
        return None
    return (
        WordCandidate.query
        .filter(
            WordCandidate.source_id == source_id,
            WordCandidate.user_id == user_id,
            WordCandidate.status.in_(["pending", "accepted"]),
            db.func.lower(WordCandidate.word) == normalized,
        )
        .with_for_update()
        .first()
    )


def _candidate_item(document: ReadingDocument, lookup: ReadingLookup) -> dict[str, Any]:
    dictionary_result = lookup.dictionary_result_json or {}
    meaning = _first(dictionary_result.get("meanings"))
    source_example = lookup.context_sentence
    # Use normalized_term (or term) as the candidate word so that dedup
    # (_find_existing_candidate) compares the same normalized value that
    # the dictionary lookup already produced.  If two lookups produce the
    # same normalized form they should map to one candidate.
    return {
        "word": lookup.normalized_term or lookup.term,
        "part_of_speech": dictionary_result.get("part_of_speech"),
        "meaning": meaning,
        "example": source_example,
        "source_example": source_example,
        "context_start": lookup.context_start,
        "context_end": lookup.context_end,
        "note": f"来自《{document.source_filename or document.title}》",
    }


def _find_existing_word(word_list_id: int, term: str):
    normalized = (term or "").strip().lower()
    if not normalized:
        return None
    return Word.query.filter_by(list_id=word_list_id).filter(
        db.func.lower(Word.word) == normalized
    ).first()


def _locked_document(user_id: int, document_id: int) -> ReadingDocument:
    document = (
        ReadingDocument.query
        .filter_by(id=document_id, user_id=user_id)
        .with_for_update()
        .first()
    )
    if document is None:
        raise ReadingNotFound("reading document not found")
    return document


def _require_document(user_id: int, document_id: int) -> ReadingDocument:
    document = get_document(user_id, document_id)
    if document is None:
        raise ReadingNotFound("reading document not found")
    return document


def _content_hash(content_text: str) -> str:
    return hashlib.sha256(content_text.encode("utf-8")).hexdigest()


def _first(values: Any) -> Any:
    return values[0] if isinstance(values, list) and values else None


def _is_int(value: Any) -> bool:
    return isinstance(value, int) and not isinstance(value, bool)


def _is_number(value: Any) -> bool:
    return isinstance(value, Real) and not isinstance(value, bool) and math.isfinite(float(value))
