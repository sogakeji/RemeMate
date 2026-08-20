"""RemeMate dispatch runner.

The public ``run_bark`` seam owns user-level isolation. Database setup and the
notification service adapter are added by the command-line entry point.
"""
from __future__ import annotations

from dataclasses import dataclass
import sys
from typing import Callable, Iterable


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


def _merge_notification_stats(target: BarkRunStats, result: object) -> None:
    """Merge the existing notification service's result into runner stats."""
    for field in ("sent", "skipped_no_due", "skipped_duplicate", "failed"):
        setattr(target, field, getattr(target, field) + getattr(result, field, 0))
