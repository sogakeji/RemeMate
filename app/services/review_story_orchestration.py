"""Fail-soft orchestration for one private review-story attempt."""
from __future__ import annotations

from datetime import datetime
import logging

from app.extensions import db
from app.services import quota as quota_svc
from app.services.review_stories import (
    DailyReviewStorySummary,
    ELIGIBILITY_NORMAL,
    ELIGIBILITY_STRONG,
)
from app.services.review_story_events import record_review_story_event
from app.services.review_story_generation import generate_review_story_once
from app.services.review_story_state import (
    ACTION_CACHED,
    ACTION_FAILED,
    ACTION_GENERATE,
    ACTION_PENDING,
    ACTION_READY,
    ReviewStoryRunDecision,
    claim_review_story_run,
    complete_review_story_run,
)


_logger = logging.getLogger(__name__)
_ELIGIBILITY_EVENTS = {
    ELIGIBILITY_NORMAL: "story_eligible_normal",
    ELIGIBILITY_STRONG: "story_eligible_strong",
}


def orchestrate_review_story(
    summary: DailyReviewStorySummary,
    *,
    retry_requested: bool = False,
    now_utc: datetime | None = None,
) -> ReviewStoryRunDecision:
    """Generate or reuse one story without making AI a review-flow gate."""
    decision = claim_review_story_run(
        summary,
        retry_requested=retry_requested,
        now_utc=now_utc,
    )
    _record_event_safely(
        user_id=summary.user_id,
        run_id=decision.run_id,
        event_type=_ELIGIBILITY_EVENTS[summary.eligibility],
        occurred_at=now_utc,
    )

    if decision.action == ACTION_CACHED:
        _record_event_safely(
            user_id=summary.user_id,
            run_id=decision.run_id,
            event_type="story_cache_hit",
            occurred_at=now_utc,
        )
        return decision
    if decision.action == ACTION_FAILED:
        _record_event_safely(
            user_id=summary.user_id,
            run_id=decision.run_id,
            event_type="story_generation_failed",
            attempt_version=decision.attempt_version,
            occurred_at=now_utc,
        )
        return decision
    if decision.action != ACTION_GENERATE:
        return decision

    _record_event_safely(
        user_id=summary.user_id,
        run_id=decision.run_id,
        event_type="story_generation_started",
        attempt_version=decision.attempt_version,
        occurred_at=now_utc,
    )
    result = generate_review_story_once(summary)
    applied = complete_review_story_run(
        user_id=summary.user_id,
        run_id=decision.run_id,
        attempt_version=decision.attempt_version,
        result=result,
        now_utc=now_utc,
    )
    _record_usage_safely(summary.user_id, result)
    if not applied:
        return ReviewStoryRunDecision(
            action=ACTION_PENDING,
            run_id=decision.run_id,
            attempt_count=decision.attempt_count,
            attempt_version=decision.attempt_version,
            lease_expires_at=decision.lease_expires_at,
            story=None,
            error_code=None,
        )

    terminal_action = ACTION_READY if result.story is not None else ACTION_FAILED
    _record_event_safely(
        user_id=summary.user_id,
        run_id=decision.run_id,
        event_type=(
            "story_generation_ready"
            if result.story is not None
            else "story_generation_failed"
        ),
        attempt_version=decision.attempt_version,
        occurred_at=now_utc,
    )
    return ReviewStoryRunDecision(
        action=terminal_action,
        run_id=decision.run_id,
        attempt_count=decision.attempt_count,
        attempt_version=decision.attempt_version,
        lease_expires_at=None,
        story=result.story,
        error_code=result.error_code,
    )


def _record_usage_safely(user_id, result) -> None:
    if (
        result.provider is None
        and result.model is None
        and result.prompt_tokens == 0
        and result.completion_tokens == 0
    ):
        return
    try:
        quota_svc.record_feature_usage(
            user_id,
            prompt_tokens=result.prompt_tokens,
            completion_tokens=result.completion_tokens,
            provider=result.provider,
            model=result.model,
            feature="review_story",
        )
    except Exception:
        db.session.rollback()
        _logger.exception("review story token accounting failed")


def _record_event_safely(**kwargs) -> None:
    try:
        record_review_story_event(**kwargs)
    except Exception:
        db.session.rollback()
        _logger.exception(
            "review story funnel event failed: %s",
            kwargs.get("event_type"),
        )
