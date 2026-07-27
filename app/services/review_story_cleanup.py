"""Retention cleanup for private review-story data."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

from sqlalchemy import and_, delete, func, or_, select

from app.models.review_story import LearningFunnelEvent, ReviewStoryRun
from app.services.timeutil import utc_now


REVIEW_STORY_RUN_RETENTION_DAYS = 7
REVIEW_STORY_EVENT_RETENTION_DAYS = 180


@dataclass(frozen=True)
class ReviewStoryCleanupStats:
    runs: int
    events: int


def cleanup_review_story_data(
    connection,
    *,
    apply_changes: bool = False,
    now_utc: datetime | None = None,
) -> ReviewStoryCleanupStats:
    """Preview or delete story caches and content-free events past retention."""
    now = _naive_utc(now_utc or utc_now())
    stale_run_cutoff = now - timedelta(
        days=REVIEW_STORY_RUN_RETENTION_DAYS,
    )
    stale_event_cutoff = now - timedelta(
        days=REVIEW_STORY_EVENT_RETENTION_DAYS,
    )
    runs = ReviewStoryRun.__table__
    events = LearningFunnelEvent.__table__

    expired_runs = or_(
        and_(
            runs.c.content_expires_at.isnot(None),
            runs.c.content_expires_at <= now,
        ),
        and_(
            runs.c.content_expires_at.is_(None),
            runs.c.updated_at <= stale_run_cutoff,
        ),
    )
    expired_events = events.c.occurred_at <= stale_event_cutoff

    if apply_changes:
        event_count = connection.execute(
            delete(events).where(expired_events)
        ).rowcount
        run_count = connection.execute(
            delete(runs).where(expired_runs)
        ).rowcount
    else:
        run_count = connection.execute(
            select(func.count()).select_from(runs).where(expired_runs)
        ).scalar_one()
        event_count = connection.execute(
            select(func.count()).select_from(events).where(expired_events)
        ).scalar_one()

    return ReviewStoryCleanupStats(
        runs=run_count,
        events=event_count,
    )


def _naive_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value
    return value.astimezone(timezone.utc).replace(tzinfo=None)
