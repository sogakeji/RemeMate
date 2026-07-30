"""Focused review state for SessionPad-owned candidates."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date

from sqlalchemy.exc import IntegrityError

from app.extensions import db
from app.models.intake import IntakeSource, WordCandidate
from app.models.packet import PartnerPacket, PartnerPacketIntake
from app.models.partner import LanguagePartner
from app.models.recap import PartnerRecap
from app.models.word import Word
from app.services import words as words_svc


class SessionPadReviewError(ValueError):
    def __init__(self, code: str, message_key: str, source_id: int):
        super().__init__(message_key)
        self.code = code
        self.message_key = message_key
        self.source_id = source_id


@dataclass(frozen=True)
class SessionPadSourceSummary:
    kind: str
    partner_name: str | None
    session_date: date | None
    title: str | None
    packet_id: int | None = None
    partner_id: int | None = None
    recap_id: int | None = None


@dataclass(frozen=True)
class SessionPadReviewState:
    source: IntakeSource
    source_summary: SessionPadSourceSummary
    status: str
    candidates: tuple[WordCandidate, ...]
    current: WordCandidate | None
    existing_word: Word | None
    uncommitted_count: int
    pending_count: int
    position: int
    total: int


def get_review_state(
    user_id: int,
    source_id: int,
    *,
    status: str | None = None,
) -> SessionPadReviewState | None:
    """Return one focused pending candidate or a completed-status list."""
    source = IntakeSource.query.filter_by(
        id=source_id,
        user_id=user_id,
        source_type="sessionpad",
    ).first()
    if source is None:
        return None

    normalized_status = (
        status if status in {"accepted", "ignored"} else "pending"
    )
    rows = (
        WordCandidate.query
        .filter_by(
            source_id=source_id,
            user_id=user_id,
            status=normalized_status,
        )
        .order_by(WordCandidate.created_at.asc(), WordCandidate.id.asc())
        .all()
    )
    total = WordCandidate.query.filter_by(
        source_id=source_id,
        user_id=user_id,
    ).count()
    pending_count = WordCandidate.query.filter_by(
        source_id=source_id,
        user_id=user_id,
        status="pending",
    ).count()
    current = rows[0] if normalized_status == "pending" and rows else None
    position = total - pending_count + 1 if current is not None else total
    return SessionPadReviewState(
        source=source,
        source_summary=_source_summary(user_id, source),
        status=normalized_status,
        candidates=tuple(rows),
        current=current,
        existing_word=(
            _find_existing_word(source.word_list_id, current.word)
            if current is not None else None
        ),
        uncommitted_count=WordCandidate.query.filter_by(
            source_id=source_id,
            user_id=user_id,
            status="accepted",
            word_id=None,
        ).count(),
        pending_count=pending_count,
        position=position,
        total=total,
    )


def accept_candidate(
    user_id: int,
    candidate_id: int,
    edits: dict,
) -> int | None:
    """Accept one pending SessionPad candidate and return its source id."""
    candidate = _locked_candidate(user_id, candidate_id)
    if candidate is None:
        return None
    if candidate.status != "pending":
        return candidate.source_id

    source = IntakeSource.query.filter_by(
        id=candidate.source_id,
        user_id=user_id,
        source_type="sessionpad",
    ).first()
    if source is None:
        return None

    term = str(edits.get("word", candidate.word) or "").strip()
    if not term:
        raise SessionPadReviewError(
            "term", "candidate.error.term_required", source.id,
        )
    if len(term) > 80:
        raise SessionPadReviewError(
            "term", "candidate.error.term_too_long", source.id,
        )

    identity = words_svc.normalize_word_identity(term)
    duplicate = (
        WordCandidate.query
        .filter(
            WordCandidate.source_id == source.id,
            WordCandidate.user_id == user_id,
            WordCandidate.id != candidate.id,
            WordCandidate.status.in_(("pending", "accepted")),
            db.func.lower(db.func.btrim(WordCandidate.word)) == identity,
        )
        .first()
    )
    if duplicate is not None:
        raise SessionPadReviewError(
            "duplicate", "candidate.sessionpad_duplicate_source", source.id,
        )
    existing_word = _find_existing_word(source.word_list_id, term)

    context = candidate.context_excerpt
    if "context_excerpt" in edits:
        try:
            context = _normalize_context(edits.get("context_excerpt"))
        except ValueError as exc:
            raise SessionPadReviewError(
                "context", "candidate.error.context_too_long", source.id,
            ) from exc

    candidate.word = term
    if "context_excerpt" in edits:
        if context != candidate.context_excerpt:
            candidate.context_excerpt = context
            candidate.context_provenance = "user_edited" if context else None
    for field in ("part_of_speech", "meaning", "example", "note"):
        if field in edits and edits[field] is not None:
            setattr(candidate, field, edits[field])

    if existing_word is not None:
        candidate.word_id = existing_word.id
    candidate.status = "accepted"
    try:
        db.session.commit()
    except IntegrityError as exc:
        db.session.rollback()
        raise SessionPadReviewError(
            "duplicate", "candidate.sessionpad_duplicate_source", source.id,
        ) from exc
    return candidate.source_id

def ignore_candidate(user_id: int, candidate_id: int) -> int | None:
    """Ignore one pending SessionPad candidate and return its source id."""
    candidate = _locked_candidate(user_id, candidate_id)
    if candidate is None:
        return None
    if candidate.status == "pending":
        candidate.status = "ignored"
        db.session.commit()
    return candidate.source_id


def _find_existing_word(word_list_id: int, term: str) -> Word | None:
    identity = words_svc.normalize_word_identity(term)
    return (
        Word.query
        .filter(
            Word.list_id == word_list_id,
            db.func.lower(db.func.btrim(Word.word)) == identity,
        )
        .first()
    )


def _normalize_context(value) -> str | None:
    context = str(value or "").strip()
    if not context:
        return None
    if len(context) > 300:
        raise ValueError("candidate context cannot exceed 300 characters")
    return context

def _locked_candidate(
    user_id: int,
    candidate_id: int,
) -> WordCandidate | None:
    return (
        WordCandidate.query
        .join(IntakeSource, IntakeSource.id == WordCandidate.source_id)
        .filter(
            WordCandidate.id == candidate_id,
            WordCandidate.user_id == user_id,
            IntakeSource.user_id == user_id,
            IntakeSource.source_type == "sessionpad",
        )
        .with_for_update()
        .first()
    )


def _source_summary(
    user_id: int,
    source: IntakeSource,
) -> SessionPadSourceSummary:
    packet = (
        PartnerPacket.query
        .join(
            PartnerPacketIntake,
            PartnerPacketIntake.packet_id == PartnerPacket.id,
        )
        .filter(
            PartnerPacketIntake.source_id == source.id,
            PartnerPacketIntake.recipient_user_id == user_id,
            PartnerPacket.recipient_user_id == user_id,
        )
        .first()
    )
    if packet is not None:
        return SessionPadSourceSummary(
            kind="packet",
            partner_name=packet.sender_display_name,
            session_date=packet.session_date,
            title=packet.recap_title,
            packet_id=packet.id,
        )

    recap_row = (
        db.session.query(PartnerRecap, LanguagePartner)
        .join(
            LanguagePartner,
            (LanguagePartner.id == PartnerRecap.partner_id)
            & (LanguagePartner.user_id == PartnerRecap.user_id),
        )
        .filter(
            PartnerRecap.intake_source_id == source.id,
            PartnerRecap.user_id == user_id,
            LanguagePartner.user_id == user_id,
        )
        .first()
    )
    if recap_row is not None:
        recap, partner = recap_row
        return SessionPadSourceSummary(
            kind="recap",
            partner_name=partner.display_name,
            session_date=recap.session_date,
            title=recap.title,
            partner_id=partner.id,
            recap_id=recap.id,
        )

    return SessionPadSourceSummary(
        kind="sessionpad",
        partner_name=None,
        session_date=None,
        title=source.original_name,
    )