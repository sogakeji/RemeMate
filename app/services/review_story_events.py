"""Privacy-safe, idempotent funnel events for review stories."""
from __future__ import annotations

from datetime import datetime, timezone
import hashlib

from sqlalchemy.dialects.postgresql import insert

from app.extensions import db
from app.models.review_story import (
    LEARNING_FUNNEL_EVENT_TYPES,
    LearningFunnelEvent,
    ReviewStoryRun,
)
from app.services.review_stories import REVIEW_STORY_CONTRACT_VERSION
from app.services.timeutil import utc_now


_ATTEMPT_EVENTS = {
    "story_generation_started",
    "story_generation_ready",
    "story_generation_failed",
}


def record_review_story_event(
    *,
    user_id: int,
    run_id: int,
    event_type: str,
    attempt_version: int | None = None,
    occurred_at: datetime | None = None,
) -> bool:
    """Record one content-free semantic event, returning whether it was new."""
    if event_type not in LEARNING_FUNNEL_EVENT_TYPES:
        raise ValueError("unsupported review story event type")
    if event_type in _ATTEMPT_EVENTS:
        if attempt_version is None or attempt_version < 1:
            raise ValueError("generation event requires an attempt version")
    elif attempt_version is not None:
        raise ValueError("non-generation event cannot carry an attempt version")

    run_exists = (
        ReviewStoryRun.query.filter_by(id=run_id, user_id=user_id)
        .with_entities(ReviewStoryRun.id)
        .one_or_none()
    )
    if run_exists is None:
        db.session.commit()
        return False

    semantic_identity = (
        f"{REVIEW_STORY_CONTRACT_VERSION}:{run_id}:{event_type}:"
        f"{attempt_version or 0}"
    )
    dedupe_key = hashlib.sha256(semantic_identity.encode("utf-8")).hexdigest()
    statement = (
        insert(LearningFunnelEvent)
        .values(
            user_id=user_id,
            event_type=event_type,
            occurred_at=_naive_utc(occurred_at or utc_now()),
            dedupe_key=dedupe_key,
        )
        .on_conflict_do_nothing(
            constraint="uq_learning_funnel_events_semantic_identity",
        )
        .returning(LearningFunnelEvent.id)
    )
    event_id = db.session.execute(statement).scalar_one_or_none()
    db.session.commit()
    return event_id is not None


def _naive_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value
    return value.astimezone(timezone.utc).replace(tzinfo=None)
