"""RemeMate dispatch runner.

The public ``run_bark`` seam owns user-level isolation. Database setup and the
notification service adapter are added by the command-line entry point.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
import argparse
from contextlib import contextmanager
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
    payload, URL validation, and push-log idempotency. The user snapshot is
    taken before dispatch, and every user's work is committed independently.
    """
    dispatch_database_url = (
        dispatch_database_url or os.environ.get("DISPATCH_DATABASE_URL")
    )
    if not dispatch_database_url:
        raise RuntimeError("DISPATCH_DATABASE_URL missing")

    from app.services import notifications

    engine = create_engine(dispatch_database_url, pool_pre_ping=True)
    try:
        with engine.connect() as conn:
            with conn.begin():
                users = get_active_bark_users(conn)

            def send_review_reminder(user, *, dry_run):
                with conn.begin():
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
    """Invoke the existing notification service for one explicit user."""
    return send_review_reminders(
        conn,
        now_utc=now_utc,
        limit_per_user=limit_per_user,
        dry_run=dry_run,
        post=post,
        secret_key=secret_key,
        public_base_url=public_base_url,
        user_id=user.id,
    )


def _positive_limit(value: str) -> int:
    limit = int(value)
    if limit < 1:
        raise argparse.ArgumentTypeError("limit must be >= 1")
    return limit


def _add_bark_arguments(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--limit",
        type=_positive_limit,
        default=1,
        help="maximum due words per user",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="count candidates without sending or writing push_log",
    )
    parser.add_argument(
        "--public-base-url",
        default=None,
        help="public site root for review links; defaults to PUBLIC_BASE_URL",
    )
    parser.add_argument(
        "--flock-lock",
        nargs="?",
        const="/run/rememate/bark.lock",
        default=None,
        metavar="PATH",
        help="acquire a non-blocking flock before dispatching",
    )


def _print_stats(stats: BarkRunStats) -> None:
    print(
        "bark reminders: "
        f"users={stats.users_seen} sent={stats.sent} "
        f"duplicates={stats.skipped_duplicate} "
        f"no_due={stats.skipped_no_due} failed={stats.failed}"
    )


def _execute_bark(args: argparse.Namespace) -> int:
    try:
        stats = run_bark_from_database(
            limit_per_user=args.limit,
            dry_run=args.dry_run,
            secret_key=os.environ.get("SECRET_KEY"),
            public_base_url=(
                args.public_base_url or os.environ.get("PUBLIC_BASE_URL")
            ),
        )
    except Exception as exc:
        print(f"[dispatch] bark runner failed: {exc}", file=sys.stderr)
        return 1
    _print_stats(stats)
    return 1 if stats.failed else 0


@contextmanager
def _non_blocking_flock(path: str):
    """Yield whether a Unix flock was acquired."""
    try:
        import fcntl
    except ImportError as exc:
        raise RuntimeError("--flock-lock is only supported on Unix") from exc

    with open(path, "a+", encoding="utf-8") as handle:
        try:
            fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            yield False
            return
        try:
            yield True
        finally:
            fcntl.flock(handle.fileno(), fcntl.LOCK_UN)


def main(argv: list[str] | None = None) -> int:
    """Command-line entry point for scheduled dispatch jobs."""
    parser = argparse.ArgumentParser(description="RemeMate dispatch runner")
    subparsers = parser.add_subparsers(dest="command")
    bark_parser = subparsers.add_parser(
        "bark", help="send due review reminders through Bark"
    )
    _add_bark_arguments(bark_parser)
    args = parser.parse_args(argv)

    if args.command != "bark":
        parser.print_help(sys.stderr)
        return 2

    if args.flock_lock:
        try:
            with _non_blocking_flock(args.flock_lock) as acquired:
                if not acquired:
                    print("[dispatch] bark runner already running")
                    return 0
                return _execute_bark(args)
        except OSError as exc:
            print(f"[dispatch] cannot acquire flock: {exc}", file=sys.stderr)
            return 1
    return _execute_bark(args)


def _merge_notification_stats(target: BarkRunStats, result: object) -> None:
    """Merge the existing notification service's result into runner stats."""
    for field in ("sent", "skipped_no_due", "skipped_duplicate", "failed"):
        setattr(target, field, getattr(target, field) + getattr(result, field, 0))


if __name__ == "__main__":
    raise SystemExit(main())
