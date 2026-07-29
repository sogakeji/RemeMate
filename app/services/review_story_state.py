"""Transactional state boundary for private review-story generation."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
import json

from sqlalchemy.dialects.postgresql import insert

from app.extensions import db
from app.models.review_story import ReviewStoryRun
from app.services.review_stories import (
    DailyReviewStorySummary,
    ELIGIBILITY_SILENT,
    REVIEW_STORY_CONTRACT_VERSION,
)
from app.services.review_story_generation import (
    ReviewStoryAttemptResult,
    ValidatedReviewStory,
    validate_review_story_result,
)
from app.services.timeutil import utc_now


REVIEW_STORY_LEASE_SECONDS = 60
ACTION_GENERATE = "generate"
ACTION_PENDING = "pending"
ACTION_CACHED = "cached"
ACTION_READY = "ready"
ACTION_FAILED = "failed"


@dataclass(frozen=True)
class ReviewStoryRunDecision:
    """Immutable result returned to the future RS2-C orchestrator."""

    action: str
    run_id: int
    attempt_count: int
    attempt_version: int
    lease_expires_at: datetime | None
    story: ValidatedReviewStory | None
    error_code: str | None


def claim_review_story_run(
    summary: DailyReviewStorySummary,
    *,
    retry_requested: bool = False,
    now_utc: datetime | None = None,
) -> ReviewStoryRunDecision:
    """Claim the first committed generation lease for one trusted summary."""
    _validate_summary(summary)
    now = _naive_utc(now_utc or utc_now())
    existing = _locked_run(summary)
    if existing is not None:
        return _decide_existing(existing, retry_requested, now)

    lease_expires_at = now + timedelta(seconds=REVIEW_STORY_LEASE_SECONDS)
    statement = (
        insert(ReviewStoryRun)
        .values(
            user_id=summary.user_id,
            local_date=summary.local_date,
            target_language=summary.target_language,
            feedback_language=summary.feedback_language,
            contract_version=REVIEW_STORY_CONTRACT_VERSION,
            input_hash=summary.input_hash,
            term_snapshot=[
                target.snapshot.as_provider_dict()
                for target in summary.targets
            ],
            term_word_ids=summary.term_word_ids,
            status="pending",
            attempt_count=1,
            attempt_version=1,
            lease_expires_at=lease_expires_at,
            created_at=now,
            updated_at=now,
        )
        .on_conflict_do_nothing(
            constraint="uq_review_story_runs_input_identity",
        )
        .returning(ReviewStoryRun.id)
    )
    run_id = db.session.execute(statement).scalar_one_or_none()
    if run_id is None:
        existing = _locked_run(summary)
        if existing is None:
            db.session.rollback()
            raise RuntimeError("review story insert conflict without a row")
        return _decide_existing(existing, retry_requested, now)

    db.session.commit()
    return ReviewStoryRunDecision(
        action=ACTION_GENERATE,
        run_id=run_id,
        attempt_count=1,
        attempt_version=1,
        lease_expires_at=lease_expires_at,
        story=None,
        error_code=None,
    )


def complete_review_story_run(
    *,
    user_id: int,
    run_id: int,
    attempt_version: int,
    result: ReviewStoryAttemptResult,
    now_utc: datetime | None = None,
) -> bool:
    """Apply one attempt result only while its pending version is current."""
    _validate_attempt_result(result)
    now = _naive_utc(now_utc or utc_now())
    run = (
        ReviewStoryRun.query.filter_by(id=run_id, user_id=user_id)
        .with_for_update()
        .one_or_none()
    )
    if (
        run is None
        or run.status != "pending"
        or run.attempt_version != attempt_version
        or run.lease_expires_at is None
        or run.lease_expires_at <= now
    ):
        db.session.commit()
        return False

    run.lease_expires_at = None
    if result.story is not None:
        run.status = "ready"
        run.result_json = _story_as_dict(result.story)
        run.error_code = None
        run.content_expires_at = now + timedelta(days=7)
    else:
        run.status = "failed"
        run.result_json = None
        run.error_code = result.error_code
        run.content_expires_at = None
    db.session.commit()
    return True


def _locked_run(
    summary: DailyReviewStorySummary,
) -> ReviewStoryRun | None:
    return (
        ReviewStoryRun.query.filter_by(
            user_id=summary.user_id,
            local_date=summary.local_date,
            target_language=summary.target_language,
            feedback_language=summary.feedback_language,
            contract_version=REVIEW_STORY_CONTRACT_VERSION,
            input_hash=summary.input_hash,
        )
        .with_for_update()
        .one_or_none()
    )


def _decide_existing(
    run: ReviewStoryRun,
    retry_requested: bool,
    now: datetime,
) -> ReviewStoryRunDecision:
    if run.status == "pending":
        if (
            run.lease_expires_at is not None
            and run.lease_expires_at > now
        ):
            decision = _decision(run, action=ACTION_PENDING)
            db.session.commit()
            return decision
        if run.attempt_count < 2:
            _begin_attempt(run, now)
            decision = _decision(run, action=ACTION_GENERATE)
            db.session.commit()
            return decision
        run.status = "failed"
        run.lease_expires_at = None
        run.error_code = "lease_expired"
        run.result_json = None
        run.content_expires_at = None
        decision = _decision(run, action=ACTION_FAILED)
        db.session.commit()
        return decision

    if run.status == "ready" and run.result_json is not None:
        story = validate_review_story_result(
            json.dumps(run.result_json, ensure_ascii=False),
            target_language=run.target_language,
            feedback_language=run.feedback_language,
            expected_keys=tuple(run.term_word_ids),
        )
        decision = _decision(
            run,
            action=ACTION_CACHED,
            story=story,
        )
        db.session.commit()
        return decision

    if run.status == "failed":
        if retry_requested and run.attempt_count < 2:
            _begin_attempt(run, now)
            decision = _decision(run, action=ACTION_GENERATE)
            db.session.commit()
            return decision
        decision = _decision(run, action=ACTION_FAILED)
        db.session.commit()
        return decision

    db.session.rollback()
    raise RuntimeError("invalid review story run state")


def _decision(
    run: ReviewStoryRun,
    *,
    action: str,
    story: ValidatedReviewStory | None = None,
) -> ReviewStoryRunDecision:
    return ReviewStoryRunDecision(
        action=action,
        run_id=run.id,
        attempt_count=run.attempt_count,
        attempt_version=run.attempt_version,
        lease_expires_at=run.lease_expires_at,
        story=story,
        error_code=run.error_code,
    )


def _story_as_dict(story: ValidatedReviewStory) -> dict:
    return {
        "title": {
            "target": story.title.target,
            "translation": story.title.translation,
        },
        "sentences": [
            {
                "target": sentence.target,
                "translation": sentence.translation,
                "terms": [
                    {
                        "key": anchor.key,
                        "target_form": anchor.target_form,
                        "translation_form": anchor.translation_form,
                    }
                    for anchor in sentence.terms
                ],
            }
            for sentence in story.sentences
        ],
    }


def _validate_attempt_result(result: ReviewStoryAttemptResult) -> None:
    if (result.story is None) == (result.error_code is None):
        raise ValueError("attempt result requires exactly one story or error")


def _begin_attempt(run: ReviewStoryRun, now: datetime) -> None:
    run.status = "pending"
    run.attempt_count += 1
    run.attempt_version += 1
    run.lease_expires_at = now + timedelta(
        seconds=REVIEW_STORY_LEASE_SECONDS,
    )
    run.error_code = None
    run.result_json = None
    run.content_expires_at = None


def _validate_summary(summary: DailyReviewStorySummary) -> None:
    if summary.eligibility == ELIGIBILITY_SILENT:
        raise ValueError("silent review summary cannot generate a story")
    if summary.input_hash is None:
        raise ValueError("eligible review summary requires an input hash")
    if not 3 <= len(summary.targets) <= 5:
        raise ValueError("eligible review summary requires 3 to 5 targets")


def _naive_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value
    return value.astimezone(timezone.utc).replace(tzinfo=None)
