from concurrent.futures import ThreadPoolExecutor, TimeoutError
from threading import Barrier, Lock

import pytest
from sqlalchemy import text

from app.services.account_access import RequestReceipt, request_registration


class ThreadSafeRecordingMailer:
    def __init__(self):
        self._lock = Lock()
        self._calls = []

    @property
    def calls(self):
        with self._lock:
            return list(self._calls)

    def send_registration_verification(
            self, email, verification_url, idempotency_key):
        with self._lock:
            self._calls.append({
                "email": email,
                "verification_url": verification_url,
                "idempotency_key": idempotency_key,
            })
        return "fake-provider-id"


@pytest.mark.parametrize(
    ("limited_scope", "limit_key", "emails", "client_keys"),
    [
        (
            "email_minute",
            "AUTH_EMAIL_PER_MINUTE_LIMIT",
            ["same-minute@example.com"] * 8,
            ["minute-client"] * 8,
        ),
        (
            "email_hour",
            "AUTH_EMAIL_PER_HOUR_LIMIT",
            ["same-hour@example.com"] * 8,
            ["hour-client"] * 8,
        ),
        (
            "client_hour",
            "AUTH_CLIENT_PER_HOUR_LIMIT",
            [f"client-{index}@example.com" for index in range(8)],
            ["same-client"] * 8,
        ),
        (
            "global_day",
            "AUTH_GLOBAL_EMAIL_PER_DAY_LIMIT",
            [f"global-{index}@example.com" for index in range(8)],
            [f"global-client-{index}" for index in range(8)],
        ),
    ],
)
def test_registration_rate_limit_has_concurrent_hard_cap(
        bypass_engine, limited_scope, limit_key, emails, client_keys):
    from app import create_app

    settings = {
        "AUTH_EMAIL_PER_MINUTE_LIMIT": 100,
        "AUTH_EMAIL_PER_HOUR_LIMIT": 100,
        "AUTH_CLIENT_PER_HOUR_LIMIT": 100,
        "AUTH_GLOBAL_EMAIL_PER_DAY_LIMIT": 100,
        limit_key: 3,
        "PUBLIC_BASE_URL": "https://example.test",
    }
    mailer = ThreadSafeRecordingMailer()
    barrier = Barrier(8)

    def request_from_thread(email, client_key):
        app = create_app("testing")
        app.config.update(settings)
        app.extensions["auth_mailer"] = mailer
        with app.app_context():
            barrier.wait(timeout=15)
            return request_registration(email, client_key)

    executor = ThreadPoolExecutor(max_workers=8)
    futures = [
        executor.submit(request_from_thread, email, client_key)
        for email, client_key in zip(emails, client_keys)
    ]
    try:
        receipts = [future.result(timeout=30) for future in futures]
    except BaseException:
        barrier.abort()
        raise
    finally:
        executor.shutdown(wait=False, cancel_futures=True)

    assert receipts.count(RequestReceipt(outcome="accepted")) == 3
    assert receipts.count(RequestReceipt(outcome="retry_later")) == 5
    assert len(mailer.calls) == 3

    with bypass_engine.connect() as conn:
        event_counts = conn.execute(text("""
            SELECT count(*) AS total,
                   count(*) FILTER (WHERE delivery_status = 'sent') AS sent
            FROM auth_mail_events
        """)).mappings().one()
        challenge_count = conn.execute(text(
            "SELECT count(*) FROM auth_challenges"
        )).scalar_one()
        buckets = conn.execute(text("""
            SELECT scope, key_digest, used_count
            FROM auth_rate_limit_buckets
            ORDER BY scope, key_digest
        """)).mappings().all()

    assert event_counts["total"] == 3
    assert event_counts["sent"] == 3
    assert challenge_count == 3
    assert all(bucket["used_count"] > 0 for bucket in buckets)

    scope_totals = {}
    for bucket in buckets:
        scope_totals[bucket["scope"]] = (
            scope_totals.get(bucket["scope"], 0) + bucket["used_count"]
        )
    assert scope_totals == {
        "global_day": 3,
        "email_hour": 3,
        "email_minute": 3,
        "client_hour": 3,
    }

    target_buckets = [
        bucket for bucket in buckets if bucket["scope"] == limited_scope
    ]
    assert len(target_buckets) == 1
    assert target_buckets[0]["used_count"] == 3
