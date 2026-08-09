from hashlib import sha256

import pytest
from sqlalchemy import text

from app.services.account_access import (
    RequestReceipt,
    request_password_reset,
    request_registration,
)
from app.services.provisioning import create_user_with_defaults


class RecordingMailer:
    def __init__(self):
        self.calls = []

    def send_registration_verification(
            self, email, verification_url, idempotency_key):
        self.calls.append({
            "kind": "registration",
            "email": email,
            "verification_url": verification_url,
            "idempotency_key": idempotency_key,
        })
        return "fake-provider-id"

    def send_password_reset(self, email, reset_url, idempotency_key):
        self.calls.append({
            "kind": "password_reset",
            "email": email,
            "reset_url": reset_url,
            "idempotency_key": idempotency_key,
        })
        return "fake-reset-provider-id"


@pytest.mark.parametrize(
    ("limited_scope", "limit_key", "emails", "client_keys"),
    [
        (
            "email_minute",
            "AUTH_EMAIL_PER_MINUTE_LIMIT",
            ["minute@example.com"] * 3,
            ["minute-client"] * 3,
        ),
        (
            "email_hour",
            "AUTH_EMAIL_PER_HOUR_LIMIT",
            ["hour@example.com"] * 3,
            ["hour-client"] * 3,
        ),
        (
            "client_hour",
            "AUTH_CLIENT_PER_HOUR_LIMIT",
            [
                "client-one@example.com",
                "client-two@example.com",
                "client-three@example.com",
            ],
            ["shared-client"] * 3,
        ),
        (
            "global_day",
            "AUTH_GLOBAL_EMAIL_PER_DAY_LIMIT",
            [
                "global-one@example.com",
                "global-two@example.com",
                "global-three@example.com",
            ],
            ["global-client-one", "global-client-two", "global-client-three"],
        ),
    ],
)
def test_registration_rate_limit_boundaries_are_atomic(
        app, bypass_engine, limited_scope, limit_key, emails, client_keys):
    app.config.update({
        "AUTH_EMAIL_PER_MINUTE_LIMIT": 100,
        "AUTH_EMAIL_PER_HOUR_LIMIT": 100,
        "AUTH_CLIENT_PER_HOUR_LIMIT": 100,
        "AUTH_GLOBAL_EMAIL_PER_DAY_LIMIT": 100,
        limit_key: 2,
        "PUBLIC_BASE_URL": "https://example.test",
    })
    mailer = RecordingMailer()
    app.extensions["auth_mailer"] = mailer

    with app.app_context():
        receipts = [
            request_registration(email, client_key)
            for email, client_key in zip(emails, client_keys)
        ]

    assert receipts[:2] == [
        RequestReceipt(outcome="accepted"),
        RequestReceipt(outcome="accepted"),
    ]
    assert receipts[2] == RequestReceipt(outcome="retry_later")
    assert len(mailer.calls) == 2

    with bypass_engine.connect() as conn:
        events = conn.execute(text(
            "SELECT count(*) FROM auth_mail_events"
        )).scalar_one()
        challenges = conn.execute(text(
            "SELECT count(*) FROM auth_challenges"
        )).scalar_one()
        buckets = conn.execute(text("""
            SELECT scope, key_digest, used_count
            FROM auth_rate_limit_buckets
            ORDER BY scope, key_digest
        """)).mappings().all()

    assert events == 2
    assert challenges == 2
    assert len(buckets) == (
        1
        + len(set(emails[:2]))
        + len(set(emails[:2]))
        + len(set(client_keys[:2]))
    )
    assert sum(bucket["used_count"] for bucket in buckets) == 8
    assert all(bucket["used_count"] > 0 for bucket in buckets)
    assert all(bucket["used_count"] <= 2 for bucket in buckets)

    scope_totals = {}
    for bucket in buckets:
        scope_totals[bucket["scope"]] = (
            scope_totals.get(bucket["scope"], 0) + bucket["used_count"]
        )
    assert scope_totals == {
        "global_day": 2,
        "email_hour": 2,
        "email_minute": 2,
        "client_hour": 2,
    }

    limited_buckets = [
        bucket for bucket in buckets if bucket["scope"] == limited_scope
    ]
    assert len(limited_buckets) == 1
    if limited_scope in {"email_minute", "email_hour"}:
        expected_key = sha256(emails[0].encode("utf-8")).hexdigest()
        assert limited_buckets[0]["key_digest"] == expected_key
    elif limited_scope == "client_hour":
        expected_key = sha256(client_keys[0].encode("utf-8")).hexdigest()
        assert limited_buckets[0]["key_digest"] == expected_key
    assert limited_buckets[0]["used_count"] == 2


def test_password_reset_rate_limit_is_enumeration_safe(app, bypass_engine):
    app.config.update({
        "AUTH_EMAIL_PER_MINUTE_LIMIT": 100,
        "AUTH_EMAIL_PER_HOUR_LIMIT": 100,
        "AUTH_CLIENT_PER_HOUR_LIMIT": 100,
        "AUTH_GLOBAL_EMAIL_PER_DAY_LIMIT": 100,
        "PUBLIC_BASE_URL": "https://example.test",
    })
    mailer = RecordingMailer()
    app.extensions["auth_mailer"] = mailer

    with app.app_context():
        create_user_with_defaults("known@example.com", "Known")
        unknown_receipt = request_password_reset(
            "unknown@example.com", "shared-client"
        )
        known_receipt = request_password_reset(
            "known@example.com", "shared-client"
        )

    assert unknown_receipt == RequestReceipt(outcome="accepted")
    assert known_receipt == RequestReceipt(outcome="accepted")
    assert [call["kind"] for call in mailer.calls] == ["password_reset"]

    def snapshot():
        with bypass_engine.connect() as conn:
            buckets = conn.execute(text("""
                SELECT scope, key_digest, used_count
                FROM auth_rate_limit_buckets
                ORDER BY scope, key_digest
            """)).mappings().all()
            events = conn.execute(text(
                "SELECT count(*) FROM auth_mail_events"
            )).scalar_one()
            challenges = conn.execute(text(
                "SELECT count(*) FROM auth_challenges"
            )).scalar_one()
        return buckets, events, challenges

    buckets, events, challenges = snapshot()
    assert events == 1
    assert challenges == 1
    assert {
        bucket["scope"] for bucket in buckets
    } == {"global_day", "email_hour", "email_minute", "client_hour"}
    assert sum(
        bucket["used_count"] for bucket in buckets
        if bucket["scope"] == "global_day"
    ) == 1
    assert sum(
        bucket["used_count"] for bucket in buckets
        if bucket["scope"] == "client_hour"
    ) == 2
    assert sum(
        bucket["used_count"] for bucket in buckets
        if bucket["scope"] in {"email_hour", "email_minute"}
    ) == 4

    app.config["AUTH_GLOBAL_EMAIL_PER_DAY_LIMIT"] = 0
    with app.app_context():
        unknown_retry = request_password_reset(
            "unknown-two@example.com", "shared-client"
        )
        known_retry = request_password_reset(
            "known@example.com", "shared-client"
        )

    assert unknown_retry == RequestReceipt(outcome="retry_later")
    assert known_retry == RequestReceipt(outcome="retry_later")
    assert mailer.calls == [mailer.calls[0]]
    assert snapshot() == (buckets, events, challenges)
