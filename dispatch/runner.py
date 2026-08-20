"""RemeMate dispatch runner.

The public ``run_bark`` seam owns user-level isolation. Database setup and the
notification service adapter are added by the command-line entry point.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
import os
import sys
from typing import Callable, Iterable

from sqlalchemy import create_engine, text


@dataclass
class BarkRunStats:
    """Aggregated results from one Bark dispatch heartbeat."""

    users_seen: int = 0
    sent: int = 0
    skipped_no_due: int = 0
    skipped_duplicate: int = 0
    failed: int = 0


def run_bark(
    users: Iterable[object],
    *,
    send_review_reminder: Callable[..., object],
    dry_run: bool = False,
) -> BarkRunStats:
    """Run the review-reminder callback once for every eligible user.

    A callback failure is logged and counted, then dispatch continues with the
    next user. The callback receives ``dry_run`` so it can preserve the same
    no-send semantics as the underlying notification service.
    """
    stats = BarkRunStats()
    for user in users:
        stats.users_seen += 1
        try:
            result = send_review_reminder(user, dry_run=dry_run)
        except Exception as exc:  # one user's failure must not stop the run
            stats.failed += 1
            print(
                f"[dispatch] bark review reminder failed for user {user.id}: {exc}",
                file=sys.stderr,
            )
            continue
        _merge_notification_stats(stats, result)
    return stats


def get_active_bark_users(conn) -> list[object]:
    """Return users eligible for review-reminder dispatch."""
    return list(conn.execute(text(
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
    )).fetchall())


def run_bark_from_database(
    *,
    dispatch_database_url: str | None = None,
    now_utc: datetime | None = None,
    limit_per_user: int = 1,
    dry_run: bool = False,
    post=None,
    secret_key: str | None = None,
    public_base_url: str | None = None,
) -> BarkRunStats:
    """Run one Bark heartbeat using the BYPASSRLS dispatch connection.

    ``send_review_reminders`` already contains the due-word query, Bark
    payload, URL validation, and push-log idempotency. The temporary views
    below scope that existing batch-shaped service to one eligible user per
    callback without changing its sending logic.
    """
    dispatch_database_url = (
        dispatch_database_url or os.environ.get("DISPATCH_DATABASE_URL")
    )
    if not dispatch_database_url:
        raise RuntimeError("DISPATCH_DATABASE_URL missing")

    from app.services import notifications

    engine = create_engine(dispatch_database_url, pool_pre_ping=True)
    try:
        with engine.begin() as conn:
            users = get_active_bark_users(conn)

            def send_review_reminder(user, *, dry_run):
                return _send_one_user(
                    conn,
                    user,
                    now_utc=now_utc,
                    limit_per_user=limit_per_user,
                    dry_run=dry_run,
                    post=post,
                    secret_key=secret_key,
                    public_base_url=public_base_url,
                    send_review_reminders=notifications.send_review_reminders,
                )

            return run_bark(
                users,
                send_review_reminder=send_review_reminder,
                dry_run=dry_run,
            )
    finally:
        engine.dispose()


def _send_one_user(
    conn,
    user,
    *,
    now_utc: datetime | None,
    limit_per_user: int,
    dry_run: bool,
    post,
    secret_key: str | None,
    public_base_url: str | None,
    send_review_reminders: Callable[..., object],
) -> object:
    """Invoke the existing notification service with one user in scope."""
    _set_user_scope(conn, user.id)
    try:
        return send_review_reminders(
            conn,
            now_utc=now_utc,
            limit_per_user=limit_per_user,
            dry_run=dry_run,
            post=post,
            secret_key=secret_key,
            public_base_url=public_base_url,
        )
    finally:
        _clear_user_scope(conn)


def _set_user_scope(conn, user_id: int) -> None:
    """Scope the existing unparameterized user query to one user.

    The dispatch role intentionally bypasses application RLS. Temporary views
    keep the service's existing SQL reusable while ensuring each per-user
    invocation sees only its selected ``users`` and ``user_settings`` rows.
    """
    _clear_user_scope(conn)
    conn.execute(text(
        """
        CREATE TEMP VIEW users AS
        SELECT * FROM public.users WHERE id = :user_id
        """
    ), {"user_id": user_id})
    conn.execute(text(
        """
        CREATE TEMP VIEW user_settings AS
        SELECT * FROM public.user_settings WHERE user_id = :user_id
        """
    ), {"user_id": user_id})
    conn.execute(text("SET LOCAL search_path TO pg_temp, public"))


def _clear_user_scope(conn) -> None:
    conn.execute(text(
        "DROP VIEW IF EXISTS pg_temp.users, pg_temp.user_settings"
    ))


def _merge_notification_stats(target: BarkRunStats, result: object) -> None:
    """Merge the existing notification service's result into runner stats."""
    for field in ("sent", "skipped_no_due", "skipped_duplicate", "failed"):
        setattr(target, field, getattr(target, field) + getattr(result, field, 0))
