"""Deterministic daily review summary for post-review stories.

RS1 is intentionally read-only: no provider calls, routes, UI, run creation,
or funnel-event writes live here.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timezone
import hashlib
import json
import re
import unicodedata
from zoneinfo import ZoneInfo

from sqlalchemy import func

from app.extensions import db
from app.models.user import User
from app.models.word import Definition, ReviewLog, Word, WordList
from app.services.timeutil import local_day_window_utc, utc_now


REVIEW_STORY_CONTRACT_VERSION = "review_story_v1"
SUPPORTED_TARGET_LANGUAGES = frozenset(
    {"fr", "en", "ja", "ko", "es", "zh"}
)
SUPPORTED_FEEDBACK_LANGUAGES = frozenset({"zh", "en", "fr", "ja", "ko", "es"})
VALID_REVIEW_GRADES = frozenset({2, 3, 5})
VALID_REVIEW_SOURCES = frozenset({"review", "bark"})
ELIGIBILITY_SILENT = "silent"
ELIGIBILITY_NORMAL = "normal"
ELIGIBILITY_STRONG = "strong"
_COMMON_APOSTROPHES = str.maketrans({"’": "'", "‘": "'", "ʼ": "'", "＇": "'"})
_WHITESPACE = re.compile(r"\s+")


@dataclass(frozen=True)
class ReviewedWord:
    word_id: int
    surface: str
    worst_grade: int


@dataclass(frozen=True)
class ReviewStoryTermSnapshot:
    key: str
    surface: str
    part_of_speech: str
    meaning: str

    def as_provider_dict(self) -> dict[str, str]:
        """Return the only term fields RS2 may send to a provider."""
        return {
            "key": self.key,
            "surface": self.surface,
            "part_of_speech": self.part_of_speech,
            "meaning": self.meaning,
        }


@dataclass(frozen=True)
class ReviewStoryTarget:
    """Internal word identity paired with a provider-safe snapshot."""

    word_id: int
    worst_grade: int
    snapshot: ReviewStoryTermSnapshot


@dataclass(frozen=True)
class DailyReviewStorySummary:
    user_id: int
    local_date: date
    day_start_utc: datetime
    day_end_utc: datetime
    target_language: str
    feedback_language: str
    reviewed_word_count: int
    forgotten_word_count: int
    eligibility: str
    targets: tuple[ReviewStoryTarget, ...]
    input_hash: str | None
    weak_word_count: int = 0

    @property
    def provider_terms(self) -> tuple[dict[str, str], ...]:
        return tuple(target.snapshot.as_provider_dict() for target in self.targets)

    @property
    def term_word_ids(self) -> dict[str, int]:
        return {
            target.snapshot.key: target.word_id
            for target in self.targets
        }


def get_daily_review_story_summary(
    user_id: int,
    *,
    now_utc: datetime | None = None,
    local_date: date | None = None,
) -> DailyReviewStorySummary | None:
    """Build today's summary from trusted user settings and owned review data.

    ``local_date`` exists for deterministic tests and maintenance tooling. A
    request routes must never accept it from the client.
    """
    user = db.session.get(User, user_id)
    if user is None:
        return None
    target_language = (user.current_language or "").strip()
    if target_language not in SUPPORTED_TARGET_LANGUAGES:
        return None
    settings = user.settings
    feedback_language = (
        (settings.feedback_language if settings else None) or "zh"
    )
    if feedback_language not in SUPPORTED_FEEDBACK_LANGUAGES:
        feedback_language = "zh"
    return build_daily_review_story_summary(
        user_id=user_id,
        timezone_name=user.timezone or "Asia/Shanghai",
        target_language=target_language,
        feedback_language=feedback_language,
        now_utc=now_utc,
        local_date=local_date,
    )


def build_daily_review_story_summary(
    *,
    user_id: int,
    timezone_name: str,
    target_language: str,
    feedback_language: str,
    now_utc: datetime | None = None,
    local_date: date | None = None,
) -> DailyReviewStorySummary:
    """Aggregate one user's local day without trusting client word ids."""
    if target_language not in SUPPORTED_TARGET_LANGUAGES:
        raise ValueError(f"unsupported target language: {target_language!r}")
    if feedback_language not in SUPPORTED_FEEDBACK_LANGUAGES:
        raise ValueError(f"unsupported feedback language: {feedback_language!r}")

    now_utc = now_utc or utc_now()
    day_start, day_end = local_day_window_utc(
        timezone_name,
        local_date=local_date,
        now_utc=now_utc,
    )
    effective_date = local_date or _local_date(now_utc, timezone_name)
    reviewed_words = _reviewed_words(
        user_id=user_id,
        target_language=target_language,
        day_start_utc=day_start,
        day_end_utc=day_end,
    )
    forgotten_count = sum(row.worst_grade == 2 for row in reviewed_words)
    weak_count = sum(row.worst_grade in {2, 3} for row in reviewed_words)
    eligibility = review_story_eligibility(
        reviewed_word_count=len(reviewed_words),
        weak_word_count=weak_count,
    )

    targets: tuple[ReviewStoryTarget, ...] = ()
    input_hash = None
    if eligibility != ELIGIBILITY_SILENT:
        selected = select_review_story_targets(reviewed_words)
        targets = _build_target_snapshots(user_id, selected)
        input_hash = review_story_input_hash(
            contract_version=REVIEW_STORY_CONTRACT_VERSION,
            target_language=target_language,
            feedback_language=feedback_language,
            terms=tuple(target.snapshot for target in targets),
        )

    return DailyReviewStorySummary(
        user_id=user_id,
        local_date=effective_date,
        day_start_utc=day_start,
        day_end_utc=day_end,
        target_language=target_language,
        feedback_language=feedback_language,
        reviewed_word_count=len(reviewed_words),
        forgotten_word_count=forgotten_count,
        eligibility=eligibility,
        targets=targets,
        input_hash=input_hash,
        weak_word_count=weak_count,
    )


def review_story_eligibility(
    *, reviewed_word_count: int, weak_word_count: int,
) -> str:
    if reviewed_word_count < 0 or weak_word_count < 0:
        raise ValueError("review counts cannot be negative")
    if weak_word_count > reviewed_word_count:
        raise ValueError("weak count cannot exceed reviewed count")
    if reviewed_word_count < 10:
        return ELIGIBILITY_SILENT
    if weak_word_count > 5:
        return ELIGIBILITY_STRONG
    return ELIGIBILITY_NORMAL


def select_review_story_targets(
    reviewed_words: list[ReviewedWord] | tuple[ReviewedWord, ...],
    *,
    limit: int = 5,
) -> tuple[ReviewedWord, ...]:
    """Select up to five terms with a stable grade/id ordering."""
    if limit < 1:
        raise ValueError("limit must be positive")
    valid = [row for row in reviewed_words if row.worst_grade in VALID_REVIEW_GRADES]
    return tuple(sorted(valid, key=lambda row: (row.worst_grade, row.word_id))[:limit])


def review_story_input_hash(
    *,
    contract_version: str,
    target_language: str,
    feedback_language: str,
    terms: tuple[ReviewStoryTermSnapshot, ...],
) -> str:
    if not contract_version.strip():
        raise ValueError("contract version cannot be empty")
    if target_language not in SUPPORTED_TARGET_LANGUAGES:
        raise ValueError(f"unsupported target language: {target_language!r}")
    if feedback_language not in SUPPORTED_FEEDBACK_LANGUAGES:
        raise ValueError(f"unsupported feedback language: {feedback_language!r}")
    normalized_terms = [
        {
            "key": _snapshot_text(term.key, 10),
            "surface": _snapshot_text(term.surface, 200),
            "part_of_speech": _snapshot_text(term.part_of_speech, 50),
            "meaning": _snapshot_text(term.meaning, 400),
        }
        for term in terms
    ]
    payload = {
        "contract_version": contract_version.strip(),
        "target_language": target_language,
        "feedback_language": feedback_language,
        "terms": normalized_terms,
    }
    canonical = json.dumps(
        payload,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _reviewed_words(
    *,
    user_id: int,
    target_language: str,
    day_start_utc: datetime,
    day_end_utc: datetime,
) -> list[ReviewedWord]:
    worst_grade = func.min(ReviewLog.grade).label("worst_grade")
    rows = (
        db.session.query(Word.id, Word.word, worst_grade)
        .join(ReviewLog, ReviewLog.word_id == Word.id)
        .join(WordList, Word.list_id == WordList.id)
        .filter(
            ReviewLog.user_id == user_id,
            ReviewLog.ts >= day_start_utc,
            ReviewLog.ts < day_end_utc,
            ReviewLog.grade.in_(VALID_REVIEW_GRADES),
            ReviewLog.source.in_(VALID_REVIEW_SOURCES),
            WordList.user_id == user_id,
            WordList.language_code == target_language,
            func.length(func.btrim(Word.word)) > 0,
        )
        .group_by(Word.id, Word.word)
        .order_by(worst_grade.asc(), Word.id.asc())
        .all()
    )
    return [
        ReviewedWord(
            word_id=row.id,
            surface=row.word,
            worst_grade=row.worst_grade,
        )
        for row in rows
    ]


def _build_target_snapshots(
    user_id: int,
    selected: tuple[ReviewedWord, ...],
) -> tuple[ReviewStoryTarget, ...]:
    if not selected:
        return ()
    definitions = (
        Definition.query.join(Word, Definition.word_id == Word.id)
        .join(WordList, Word.list_id == WordList.id)
        .filter(
            Definition.word_id.in_([row.word_id for row in selected]),
            WordList.user_id == user_id,
        )
        .order_by(Definition.word_id.asc(), Definition.id.asc())
        .all()
    )
    definitions_by_word: dict[int, list[Definition]] = {}
    for definition in definitions:
        definitions_by_word.setdefault(definition.word_id, []).append(definition)

    targets = []
    for position, row in enumerate(selected, start=1):
        definition = _main_definition(definitions_by_word.get(row.word_id, []))
        targets.append(ReviewStoryTarget(
            word_id=row.word_id,
            worst_grade=row.worst_grade,
            snapshot=ReviewStoryTermSnapshot(
                key=f"t{position}",
                surface=_snapshot_text(row.surface, 200),
                part_of_speech=_snapshot_text(
                    definition.part_of_speech if definition else "", 50,
                ),
                meaning=_snapshot_text(
                    definition.meaning if definition else "", 400,
                ),
            ),
        ))
    return tuple(targets)


def _main_definition(definitions: list[Definition]) -> Definition | None:
    for definition in definitions:
        if definition.meaning and definition.meaning.strip():
            return definition
    return definitions[0] if definitions else None


def _snapshot_text(value: str | None, limit: int) -> str:
    normalized = unicodedata.normalize("NFKC", value or "")
    normalized = normalized.translate(_COMMON_APOSTROPHES)
    normalized = _WHITESPACE.sub(" ", normalized).strip()
    return normalized[:limit]


def _local_date(now_utc: datetime, timezone_name: str) -> date:
    aware = (
        now_utc.replace(tzinfo=timezone.utc)
        if now_utc.tzinfo is None
        else now_utc.astimezone(timezone.utc)
    )
    return aware.astimezone(ZoneInfo(timezone_name)).date()
