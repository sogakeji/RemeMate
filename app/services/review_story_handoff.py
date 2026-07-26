"""Resolve a private review-story term into an owned writing target."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone

from app.extensions import db
from app.models.review_story import ReviewStoryRun
from app.models.word import Word, WordList
from app.services.timeutil import utc_now
from app.services.words import get_word


@dataclass(frozen=True)
class ReviewStoryWritingTarget:
    run_id: int
    term_key: str
    word_id: int
    target_language: str
    word: Word


def resolve_review_story_writing_target(
    *,
    user_id: int,
    run_id: int,
    term_key: str,
    now_utc: datetime | None = None,
) -> ReviewStoryWritingTarget | None:
    """Return one ready, unexpired, user-owned story term for writing."""
    if run_id < 1 or not term_key:
        return None
    now = _naive_utc(now_utc or utc_now())
    run = ReviewStoryRun.query.filter(
        ReviewStoryRun.id == run_id,
        ReviewStoryRun.user_id == user_id,
        ReviewStoryRun.status == "ready",
        ReviewStoryRun.content_expires_at.isnot(None),
        ReviewStoryRun.content_expires_at > now,
    ).one_or_none()
    if run is None or not isinstance(run.term_word_ids, dict):
        return None

    word_id = run.term_word_ids.get(term_key)
    if isinstance(word_id, bool) or not isinstance(word_id, int):
        return None
    word = get_word(user_id, word_id)
    if word is None:
        return None
    word_list = db.session.get(WordList, word.list_id)
    if word_list is None or word_list.language_code != run.target_language:
        return None

    return ReviewStoryWritingTarget(
        run_id=run.id,
        term_key=term_key,
        word_id=word.id,
        target_language=run.target_language,
        word=word,
    )


def _naive_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value
    return value.astimezone(timezone.utc).replace(tzinfo=None)
