"""Create SessionPad candidates without mixing source, context, and examples."""
from __future__ import annotations

from dataclasses import dataclass, replace

from app.extensions import db
from app.models.intake import IntakeSource, WordCandidate
from app.models.word import Word
from app.services import words as words_svc


MAX_AI_CANDIDATES = 8
MAX_MANUAL_CANDIDATES = 20
MAX_TERM_CHARS = 80
MAX_CONTEXT_CHARS = 300


@dataclass(frozen=True)
class CandidateDraft:
    term: str
    context: str | None
    provenance: str | None


@dataclass(frozen=True)
class CandidateCreationResult:
    source_id: int
    candidate_ids: tuple[int, ...]
    created_count: int
    existing_word_count: int


def create_sessionpad_candidates(
    user_id: int,
    source_id: int,
    drafts: list[CandidateDraft],
) -> CandidateCreationResult | None:
    """Create or reuse active candidates while holding the source row lock."""
    normalized = _validate_creation_drafts(drafts)
    source = (
        IntakeSource.query
        .filter_by(
            id=source_id,
            user_id=user_id,
            source_type="sessionpad",
        )
        .with_for_update()
        .first()
    )
    if source is None:
        return None

    keys = {words_svc.normalize_word_identity(draft.term) for draft in normalized}
    existing_word_keys = {
        words_svc.normalize_word_identity(word)
        for word, in (
            Word.query
            .with_entities(Word.word)
            .filter(
                Word.list_id == source.word_list_id,
                db.func.lower(db.func.btrim(Word.word)).in_(keys),
            )
            .all()
        )
    }
    active_candidates = {
        words_svc.normalize_word_identity(candidate.word): candidate
        for candidate in (
            WordCandidate.query
            .filter(
                WordCandidate.source_id == source.id,
                WordCandidate.user_id == user_id,
                WordCandidate.status.in_(["pending", "accepted"]),
                db.func.lower(db.func.btrim(WordCandidate.word)).in_(keys),
            )
            .all()
        )
    }

    created_count = 0
    existing_word_count = 0
    ordered_candidates: list[WordCandidate] = []
    for draft in normalized:
        key = words_svc.normalize_word_identity(draft.term)
        if key in existing_word_keys:
            existing_word_count += 1
            continue
        candidate = active_candidates.get(key)
        if candidate is None:
            candidate = WordCandidate(
                source_id=source.id,
                user_id=user_id,
                word=draft.term,
                context_excerpt=draft.context,
                context_provenance=draft.provenance,
                status="pending",
            )
            db.session.add(candidate)
            active_candidates[key] = candidate
            created_count += 1
        elif candidate.context_excerpt is None and draft.context is not None:
            candidate.context_excerpt = draft.context
            candidate.context_provenance = draft.provenance
        ordered_candidates.append(candidate)

    db.session.flush()
    if created_count:
        source.total_candidates = (
            source.total_candidates or 0
        ) + created_count
    return CandidateCreationResult(
        source_id=source.id,
        candidate_ids=tuple(candidate.id for candidate in ordered_candidates),
        created_count=created_count,
        existing_word_count=existing_word_count,
    )


def normalize_ai_suggestions(data, source_text: str) -> list[CandidateDraft]:
    """Validate untrusted AI suggestions and anchor contexts to source text."""
    if not isinstance(data, dict) or not isinstance(data.get("candidates"), list):
        return []

    drafts: list[CandidateDraft] = []
    index_by_key: dict[str, int] = {}
    for item in data["candidates"]:
        if not isinstance(item, dict):
            continue
        term = _optional_term(item.get("term"))
        if term is None:
            continue
        context = _located_ai_context(item.get("context"), source_text)
        draft = CandidateDraft(
            term=term,
            context=context,
            provenance="source_quote" if context else None,
        )
        _merge_draft(drafts, index_by_key, draft)
        if len(drafts) == MAX_AI_CANDIDATES:
            break
    return drafts


def normalize_manual_candidates(rows) -> list[CandidateDraft]:
    """Normalize explicit user input into the same term + context contract."""
    if not isinstance(rows, list):
        raise ValueError("candidate rows must be a list")
    if len(rows) > MAX_MANUAL_CANDIDATES:
        raise ValueError("manual submission allows at most 20 candidates")

    drafts: list[CandidateDraft] = []
    index_by_key: dict[str, int] = {}
    for item in rows:
        if not isinstance(item, dict):
            raise ValueError("candidate row must be an object")
        term = _required_term(item.get("term"))
        context = _manual_context(item.get("context"))
        draft = CandidateDraft(
            term=term,
            context=context,
            provenance="user_edited" if context else None,
        )
        _merge_draft(drafts, index_by_key, draft)
    if not drafts:
        raise ValueError("at least one candidate is required")
    return drafts


def normalize_submitted_candidates(
    rows,
    source_text: str,
) -> list[CandidateDraft]:
    """Normalize editable form rows while preserving unchanged AI excerpts."""
    if not isinstance(rows, list):
        raise ValueError("candidate rows must be a list")
    if len(rows) > MAX_MANUAL_CANDIDATES:
        raise ValueError("manual submission allows at most 20 candidates")

    drafts: list[CandidateDraft] = []
    index_by_key: dict[str, int] = {}
    for item in rows:
        if not isinstance(item, dict):
            raise ValueError("candidate row must be an object")
        term = _required_term(item.get("term"))
        context = _manual_context(item.get("context"))
        provenance = None
        if context is not None:
            original = item.get("original_context")
            unchanged_ai_context = (
                item.get("origin") == "source_quote"
                and isinstance(original, str)
                and original.strip() == context
            )
            located = (
                locate_source_excerpt(source_text, context)
                if unchanged_ai_context else None
            )
            if located is not None:
                context = located
                provenance = "source_quote"
            else:
                provenance = "user_edited"
        _merge_draft(
            drafts,
            index_by_key,
            CandidateDraft(term, context, provenance),
        )
    if not drafts:
        raise ValueError("at least one candidate is required")
    return drafts


def locate_source_excerpt(source_text: str, suggested_context: str) -> str | None:
    """Return the continuous source slice matching a whitespace-folded context."""
    if not isinstance(source_text, str) or not isinstance(suggested_context, str):
        return None
    needle = " ".join(suggested_context.split())
    if not needle or len(needle) > MAX_CONTEXT_CHARS:
        return None

    normalized, starts, ends = _fold_source_whitespace(source_text)
    offset = normalized.find(needle)
    if offset < 0:
        return None
    excerpt = source_text[
        starts[offset]:ends[offset + len(needle) - 1]
    ].strip()
    if not excerpt or len(excerpt) > MAX_CONTEXT_CHARS:
        return None
    return excerpt


def _fold_source_whitespace(value: str) -> tuple[str, list[int], list[int]]:
    chars: list[str] = []
    starts: list[int] = []
    ends: list[int] = []
    pending_space_start: int | None = None
    pending_space_end: int | None = None

    for index, char in enumerate(value):
        if char.isspace():
            if chars and pending_space_start is None:
                pending_space_start = index
            if pending_space_start is not None:
                pending_space_end = index + 1
            continue
        if pending_space_start is not None:
            chars.append(" ")
            starts.append(pending_space_start)
            ends.append(pending_space_end or pending_space_start + 1)
            pending_space_start = None
            pending_space_end = None
        chars.append(char)
        starts.append(index)
        ends.append(index + 1)
    return "".join(chars), starts, ends


def _optional_term(value) -> str | None:
    if not isinstance(value, str):
        return None
    term = value.strip()
    if not term or len(term) > MAX_TERM_CHARS:
        return None
    return term


def _required_term(value) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError("candidate term is required")
    term = value.strip()
    if len(term) > MAX_TERM_CHARS:
        raise ValueError("candidate term cannot exceed 80 characters")
    return term


def _manual_context(value) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str):
        raise ValueError("candidate context must be text")
    context = value.strip()
    if not context:
        return None
    if len(context) > MAX_CONTEXT_CHARS:
        raise ValueError("candidate context cannot exceed 300 characters")
    return context


def _located_ai_context(value, source_text: str) -> str | None:
    if not isinstance(value, str):
        return None
    return locate_source_excerpt(source_text, value)


def _merge_draft(
    drafts: list[CandidateDraft],
    index_by_key: dict[str, int],
    draft: CandidateDraft,
) -> None:
    key = words_svc.normalize_word_identity(draft.term)
    existing_index = index_by_key.get(key)
    if existing_index is None:
        index_by_key[key] = len(drafts)
        drafts.append(draft)
        return
    if drafts[existing_index].context is None and draft.context is not None:
        drafts[existing_index] = replace(
            drafts[existing_index],
            context=draft.context,
            provenance=draft.provenance,
        )


def _validate_creation_drafts(
    drafts: list[CandidateDraft],
) -> list[CandidateDraft]:
    if not isinstance(drafts, list) or not drafts:
        raise ValueError("at least one candidate is required")
    if len(drafts) > MAX_MANUAL_CANDIDATES:
        raise ValueError("candidate submission allows at most 20 items")

    normalized: list[CandidateDraft] = []
    index_by_key: dict[str, int] = {}
    for draft in drafts:
        if not isinstance(draft, CandidateDraft):
            raise ValueError("invalid candidate draft")
        term = _required_term(draft.term)
        context = _manual_context(draft.context)
        if context is None:
            if draft.provenance is not None:
                raise ValueError("empty candidate context cannot have provenance")
            provenance = None
        else:
            if draft.provenance not in {"source_quote", "user_edited"}:
                raise ValueError("invalid candidate context provenance")
            provenance = draft.provenance
        _merge_draft(
            normalized,
            index_by_key,
            CandidateDraft(term, context, provenance),
        )
    return normalized
