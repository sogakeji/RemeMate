"""Fixed, content-free aggregates for private closed-beta observation."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta

from sqlalchemy import create_engine, text


@dataclass(frozen=True)
class RateMetric:
    numerator: int
    denominator: int

    @property
    def percent(self) -> float | None:
        if self.denominator == 0:
            return None
        return round(self.numerator * 100 / self.denominator, 1)


@dataclass(frozen=True)
class WindowMetrics:
    start: datetime
    end: datetime
    active_users: int
    repeat_active_users: int
    active_user_days: int
    review_users: int
    output_users: int
    review_to_output: RateMetric
    story_eligible_users: int
    story_started_users: int
    story_ready_users: int
    story_handoff_users: int
    story_saved_users: int
    recap_users: int
    packet_sent_users: int
    thank_users: int
    adoption_users: int
    practice_completed_users: int
    practice_repeat: RateMetric


@dataclass(frozen=True)
class ObservationReport:
    current: WindowMetrics
    previous: WindowMetrics


_ACTIVE_OUTPUTS = text("""
    WITH active_events AS (
        SELECT user_id, ts AS occurred_at
        FROM review_logs
        WHERE source IN ('review', 'bark') AND grade IN (2, 3, 5)
        UNION ALL
        SELECT user_id, created_at FROM output_entries
        UNION ALL
        SELECT user_id, created_at FROM intake_sources
        UNION ALL
        SELECT user_id, completed_at FROM intake_sources WHERE completed_at IS NOT NULL
        UNION ALL
        SELECT user_id, created_at FROM partner_recaps
        UNION ALL
        SELECT sender_user_id, created_at FROM partner_packets
        UNION ALL
        SELECT recipient_user_id, thanked_at FROM partner_packet_thanks
        UNION ALL
        SELECT recipient_user_id, created_at FROM partner_packet_item_adoptions
        UNION ALL
        SELECT user_id, occurred_at FROM learning_funnel_events
        UNION ALL
        SELECT user_id, completed_at
        FROM practice_sessions
        WHERE status = 'completed' AND completed_at IS NOT NULL
    ), user_days AS (
        SELECT DISTINCT user_id, CAST(occurred_at AS date) AS active_date
        FROM active_events
        WHERE occurred_at >= :start AND occurred_at < :end
    ), per_user AS (
        SELECT user_id, count(*) AS active_days
        FROM user_days
        GROUP BY user_id
    )
    SELECT
        count(*) AS active_users,
        count(*) FILTER (WHERE active_days >= 2) AS repeat_active_users,
        COALESCE(sum(active_days), 0) AS active_user_days
    FROM per_user
""")

_DETAILS = text("""
    WITH valid_reviews AS (
        SELECT user_id, word_id, ts
        FROM review_logs
        WHERE ts >= :start AND ts < :end
          AND source IN ('review', 'bark') AND grade IN (2, 3, 5)
    ), attributed_users AS (
        SELECT DISTINCT reviews.user_id
        FROM valid_reviews reviews
        JOIN output_entries outputs
          ON outputs.user_id = reviews.user_id
         AND outputs.word_id = reviews.word_id
         AND outputs.created_at >= reviews.ts
         AND outputs.created_at <= reviews.ts + interval '24 hours'
         AND outputs.created_at >= :start AND outputs.created_at < :end
    ), practice_days AS (
        SELECT DISTINCT user_id, CAST(completed_at AS date) AS completed_date
        FROM practice_sessions
        WHERE status = 'completed'
          AND completed_at >= :start AND completed_at < :end
    ), practice_by_user AS (
        SELECT user_id, count(*) AS completed_days
        FROM practice_days
        GROUP BY user_id
    )
    SELECT
        (SELECT count(DISTINCT user_id) FROM valid_reviews) AS review_users,
        (SELECT count(DISTINCT user_id) FROM output_entries
         WHERE created_at >= :start AND created_at < :end) AS output_users,
        (SELECT count(*) FROM attributed_users) AS attributed_users,
        (SELECT count(DISTINCT user_id) FROM learning_funnel_events
         WHERE occurred_at >= :start AND occurred_at < :end
           AND event_type IN ('story_eligible_normal', 'story_eligible_strong'))
            AS story_eligible_users,
        (SELECT count(DISTINCT user_id) FROM learning_funnel_events
         WHERE occurred_at >= :start AND occurred_at < :end
           AND event_type = 'story_generation_started') AS story_started_users,
        (SELECT count(DISTINCT user_id) FROM learning_funnel_events
         WHERE occurred_at >= :start AND occurred_at < :end
           AND event_type = 'story_generation_ready') AS story_ready_users,
        (SELECT count(DISTINCT user_id) FROM learning_funnel_events
         WHERE occurred_at >= :start AND occurred_at < :end
           AND event_type = 'story_writing_handoff') AS story_handoff_users,
        (SELECT count(DISTINCT user_id) FROM learning_funnel_events
         WHERE occurred_at >= :start AND occurred_at < :end
           AND event_type = 'story_output_saved') AS story_saved_users,
        (SELECT count(DISTINCT user_id) FROM partner_recaps
         WHERE created_at >= :start AND created_at < :end) AS recap_users,
        (SELECT count(DISTINCT sender_user_id) FROM partner_packets
         WHERE created_at >= :start AND created_at < :end) AS packet_sent_users,
        (SELECT count(DISTINCT recipient_user_id) FROM partner_packet_thanks
         WHERE thanked_at >= :start AND thanked_at < :end) AS thank_users,
        (SELECT count(DISTINCT recipient_user_id) FROM partner_packet_item_adoptions
         WHERE created_at >= :start AND created_at < :end) AS adoption_users,
        (SELECT count(*) FROM practice_by_user) AS practice_completed_users,
        (SELECT count(*) FROM practice_by_user WHERE completed_days >= 2)
            AS practice_repeat_users
""")


def _window(connection, start: datetime, end: datetime) -> WindowMetrics:
    parameters = {"start": start, "end": end}
    activity = connection.execute(
        _ACTIVE_OUTPUTS, parameters,
    ).mappings().one()
    details = connection.execute(_DETAILS, parameters).mappings().one()
    review_users = int(details["review_users"])
    practice_completed_users = int(details["practice_completed_users"])
    return WindowMetrics(
        start=start,
        end=end,
        active_users=int(activity["active_users"]),
        repeat_active_users=int(activity["repeat_active_users"]),
        active_user_days=int(activity["active_user_days"]),
        review_users=review_users,
        output_users=int(details["output_users"]),
        review_to_output=RateMetric(
            int(details["attributed_users"]), review_users,
        ),
        story_eligible_users=int(details["story_eligible_users"]),
        story_started_users=int(details["story_started_users"]),
        story_ready_users=int(details["story_ready_users"]),
        story_handoff_users=int(details["story_handoff_users"]),
        story_saved_users=int(details["story_saved_users"]),
        recap_users=int(details["recap_users"]),
        packet_sent_users=int(details["packet_sent_users"]),
        thank_users=int(details["thank_users"]),
        adoption_users=int(details["adoption_users"]),
        practice_completed_users=practice_completed_users,
        practice_repeat=RateMetric(
            int(details["practice_repeat_users"]), practice_completed_users,
        ),
    )


def build_report(dispatch_database_url: str, *, now: datetime) -> ObservationReport:
    """Build adjacent rolling seven-day windows through the BYPASSRLS role."""
    current_start = now - timedelta(days=7)
    previous_start = now - timedelta(days=14)
    engine = create_engine(dispatch_database_url, pool_pre_ping=True)
    try:
        with engine.connect() as connection:
            return ObservationReport(
                current=_window(connection, current_start, now),
                previous=_window(connection, previous_start, current_start),
            )
    finally:
        engine.dispose()
