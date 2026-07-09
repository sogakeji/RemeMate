"""Bark notification sending and review reminder dispatch.

This module is deliberately service-style: callers pass explicit user ids or a
dispatch connection. Web requests keep using the settings routes; background
jobs use DISPATCH_DATABASE_URL and never depend on request context.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

import requests
from sqlalchemy import text

from app.services.timeutil import utc_now
from app.services.words import _language_name, _validate_push_url
from app.services.review_links import make_review_token, review_link_url


BARK_GROUP = "RemeMate"
PUSH_TYPE_REVIEW = "review_reminder"


@dataclass
class ReviewReminderStats:
    users_seen: int = 0
    sent: int = 0
    skipped_no_due: int = 0
    skipped_duplicate: int = 0
    failed: int = 0


class NotificationError(ValueError):
    """A notification could not be sent."""


def build_review_reminder_payload(row, *, due_count: int,
                                  review_url: str | None = None) -> dict:
    """Build a Bark payload for one due word."""
    meaning = (row.meaning or "").strip()
    example = (row.example or "").strip()
    body = meaning or example or "有单词到期了，回来复习一下。"
    if due_count > 1:
        body = f"{body}\n还有 {due_count} 个词待复习。"
    payload = {
        "title": row.word,
        "subtitle": f"{_language_name(row.language_code)} · 待复习",
        "body": body,
        "group": BARK_GROUP,
    }
    if review_url:
        payload["url"] = review_url
    return payload


def send_bark_payload(
    bark_url: str | None,
    payload: dict,
    *,
    timeout: int = 5,
    post=None,
) -> None:
    """Send a Bark payload after URL validation.

    The same validation is used for saved settings and actual sends. Redirects
    are disabled to avoid turning a safe URL into an internal request.
    """
    try:
        url = _validate_push_url(bark_url)
    except ValueError as exc:
        raise NotificationError(str(exc)) from exc
    if not url:
        raise NotificationError("请先保存 Bark 地址")
    post = post or requests.post
    try:
        resp = post(url, json=payload, timeout=timeout, allow_redirects=False)
    except requests.RequestException as exc:
        raise NotificationError("Bark 推送发送失败") from exc
    if not 200 <= resp.status_code < 300:
        raise NotificationError("Bark 推送发送失败")


def send_review_reminders(
    conn,
    *,
    now_utc: datetime | None = None,
    limit_per_user: int = 1,
    dry_run: bool = False,
    post=None,
    secret_key: str | None = None,
    public_base_url: str | None = None,
) -> ReviewReminderStats:
    """Send at most ``limit_per_user`` due-word reminders per configured user.

    A reminder is idempotent per user + word + user-local date. This allows an
    overdue word to remind again tomorrow while preventing repeated timer runs
    from sending duplicates on the same day.
    """
    if limit_per_user < 1:
        raise ValueError("limit_per_user must be >= 1")

    now_utc = now_utc or utc_now()
    stats = ReviewReminderStats()
    users = conn.execute(text(
        """
        SELECT u.id, u.timezone, s.bark_url
        FROM users u
        JOIN user_settings s ON s.user_id = u.id
        WHERE u.is_active = true
          AND s.bark_url IS NOT NULL
          AND s.bark_url <> ''
          AND s.notify_review_reminder = true
        ORDER BY u.id
        """
    )).fetchall()

    for user in users:
        stats.users_seen += 1
        due_words = conn.execute(text(
            """
            SELECT w.id, w.word, wl.language_code,
                   COALESCE(d.part_of_speech, '') AS part_of_speech,
                   COALESCE(d.meaning, '') AS meaning,
                   COALESCE(d.example, '') AS example
            FROM words w
            JOIN word_lists wl ON wl.id = w.list_id
            LEFT JOIN LATERAL (
                SELECT part_of_speech, meaning, example
                FROM definitions
                WHERE word_id = w.id
                ORDER BY id
                LIMIT 1
            ) d ON true
            WHERE wl.user_id = :user_id
              AND w.due_date <= :now_utc
            ORDER BY w.due_date ASC, w.id DESC
            LIMIT :limit
            """
        ), {
            "user_id": user.id,
            "now_utc": now_utc,
            "limit": limit_per_user,
        }).fetchall()

        if not due_words:
            stats.skipped_no_due += 1
            continue

        local_date = _local_date(now_utc, user.timezone)
        due_count = _due_count(conn, user.id, now_utc)
        for word in due_words:
            key = f"{user.id}:review:{word.id}:{local_date}"
            if _already_pushed(conn, key):
                stats.skipped_duplicate += 1
                continue
            url = None
            if secret_key and public_base_url:
                token = make_review_token(secret_key, user.id, word.id)
                url = review_link_url(public_base_url, token)
            payload = build_review_reminder_payload(
                word, due_count=due_count, review_url=url)
            if not dry_run:
                try:
                    send_bark_payload(user.bark_url, payload, post=post)
                except NotificationError:
                    stats.failed += 1
                    continue
                _record_push(conn, user.id, key, PUSH_TYPE_REVIEW, now_utc)
            stats.sent += 1
    return stats


def _local_date(now_utc: datetime, timezone_name: str | None) -> str:
    tz = ZoneInfo(timezone_name or "Asia/Shanghai")
    aware = now_utc.replace(tzinfo=timezone.utc) if now_utc.tzinfo is None else now_utc
    return aware.astimezone(tz).date().isoformat()


def _due_count(conn, user_id: int, now_utc: datetime) -> int:
    return conn.execute(text(
        """
        SELECT count(*)
        FROM words w
        JOIN word_lists wl ON wl.id = w.list_id
        WHERE wl.user_id = :user_id
          AND w.due_date <= :now_utc
        """
    ), {"user_id": user_id, "now_utc": now_utc}).scalar() or 0


def _already_pushed(conn, idempotency_key: str) -> bool:
    return bool(conn.execute(text(
        "SELECT 1 FROM push_log WHERE idempotency_key = :key"
    ), {"key": idempotency_key}).first())


def _record_push(conn, user_id: int, idempotency_key: str,
                 push_type: str, created_at: datetime) -> None:
    conn.execute(text(
        """
        INSERT INTO push_log(idempotency_key, user_id, push_type, created_at)
        VALUES (:key, :user_id, :push_type, :created_at)
        ON CONFLICT (idempotency_key) DO NOTHING
        """
    ), {
        "key": idempotency_key,
        "user_id": user_id,
        "push_type": push_type,
        "created_at": created_at,
    })
