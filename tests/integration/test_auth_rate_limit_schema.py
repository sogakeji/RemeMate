from datetime import datetime, timezone

import pytest
from sqlalchemy import inspect, text
from sqlalchemy.exc import IntegrityError

from app.extensions import db
from app.models.account_access import AuthRateLimitBucket


def test_auth_rate_limit_bucket_schema_is_registered_and_unscoped(
        app, bypass_engine):
    assert AuthRateLimitBucket.__tablename__ == "auth_rate_limit_buckets"
    assert AuthRateLimitBucket.__table__ is db.metadata.tables[
        "auth_rate_limit_buckets"
    ]

    inspector = inspect(bypass_engine)
    columns = {
        column["name"]: column
        for column in inspector.get_columns("auth_rate_limit_buckets")
    }
    assert set(columns) == {
        "scope",
        "key_digest",
        "window_start",
        "used_count",
        "created_at",
        "updated_at",
    }
    assert columns["scope"]["type"].__class__.__name__ == "VARCHAR"
    assert columns["key_digest"]["type"].__class__.__name__ == "CHAR"
    assert columns["window_start"]["type"].timezone is True
    assert columns["created_at"]["type"].timezone is True
    assert columns["updated_at"]["type"].timezone is True
    assert "now()" in columns["created_at"]["default"].lower()
    assert "now()" in columns["updated_at"]["default"].lower()

    primary_key = inspector.get_pk_constraint("auth_rate_limit_buckets")
    assert primary_key["constrained_columns"] == [
        "scope", "key_digest", "window_start",
    ]

    checks = {
        check["name"]: check["sqltext"]
        for check in inspector.get_check_constraints(
            "auth_rate_limit_buckets"
        )
    }
    assert "ck_auth_rate_limit_buckets_scope" in checks
    assert "ck_auth_rate_limit_buckets_used_count" in checks
    assert "global_day" in checks["ck_auth_rate_limit_buckets_scope"]
    assert "email_hour" in checks["ck_auth_rate_limit_buckets_scope"]
    assert "email_minute" in checks["ck_auth_rate_limit_buckets_scope"]
    assert "client_hour" in checks["ck_auth_rate_limit_buckets_scope"]
    assert ">= 0" in checks["ck_auth_rate_limit_buckets_used_count"]

    with bypass_engine.connect() as conn:
        rls = conn.execute(text("""
            SELECT c.relrowsecurity, c.relforcerowsecurity,
                   count(p.policyname) AS policy_count
            FROM pg_class AS c
            LEFT JOIN pg_policies AS p
              ON p.tablename = c.relname
             AND p.schemaname = 'public'
            WHERE c.relname = 'auth_rate_limit_buckets'
            GROUP BY c.relrowsecurity, c.relforcerowsecurity
        """)).mappings().one()

    assert rls["relrowsecurity"] is False
    assert rls["relforcerowsecurity"] is False
    assert rls["policy_count"] == 0

    with pytest.raises(IntegrityError):
        with bypass_engine.begin() as conn:
            conn.execute(text("""
                INSERT INTO auth_rate_limit_buckets
                    (scope, key_digest, window_start, used_count)
                VALUES
                    ('not_a_scope', :key_digest, :window_start, 0)
            """), {
                "key_digest": "a" * 64,
                "window_start": datetime(2026, 8, 9, tzinfo=timezone.utc),
            })

    with pytest.raises(IntegrityError):
        with bypass_engine.begin() as conn:
            conn.execute(text("""
                INSERT INTO auth_rate_limit_buckets
                    (scope, key_digest, window_start, used_count)
                VALUES
                    ('global_day', :key_digest, :window_start, -1)
            """), {
                "key_digest": "b" * 64,
                "window_start": datetime(2026, 8, 9, tzinfo=timezone.utc),
            })
