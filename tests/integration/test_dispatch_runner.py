import os
import subprocess
import sys
from datetime import datetime

from sqlalchemy import text

from app.services import notifications, words as words_svc
from dispatch.runner import run_bark_from_database
from tests.helpers import provision_user


def _configure_bark(bypass_engine, uid):
    with bypass_engine.begin() as conn:
        conn.execute(text(
            """
            UPDATE user_settings
            SET bark_url='https://api.day.app/test-key',
                notify_review_reminder=true
            WHERE user_id=:uid
            """
        ), {"uid": uid})


def _make_due_word(bypass_engine, uid):
    with bypass_engine.begin() as conn:
        list_id = conn.execute(text(
            """
            INSERT INTO word_lists(user_id,name,language_code,created_at)
            VALUES (:uid,'法语','fr',now()) RETURNING id
            """
        ), {"uid": uid}).scalar()
        word_id = conn.execute(text(
            """
            INSERT INTO words(
                list_id,word,marked,due_date,interval,ease,reps,lapses
            )
            VALUES (
                :list_id,'maison',false,
                timestamp '2026-07-09 11:00:00',1,2.5,0,0
            ) RETURNING id
            """
        ), {"list_id": list_id}).scalar()
        conn.execute(text(
            """
            INSERT INTO definitions(word_id,part_of_speech,meaning,example)
            VALUES (:word_id,'名词','房子','La maison est bleue.')
            """
        ), {"word_id": word_id})
        return word_id


def test_bark_runner_dry_run_real_run_and_retry_are_idempotent(
        bypass_engine, app, monkeypatch):
    uid = provision_user(app, "dispatch@t.com", "pw12345678", tz="Asia/Shanghai")
    word_id = _make_due_word(bypass_engine, uid)
    _configure_bark(bypass_engine, uid)
    monkeypatch.setenv("DISPATCH_DATABASE_URL", os.environ["TEST_DISPATCH_DATABASE_URL"])

    calls = []

    class Resp:
        status_code = 200

    monkeypatch.setattr(
        words_svc.socket,
        "getaddrinfo",
        lambda *args, **kwargs: [
            (None, None, None, None, ("43.155.109.24", 443))
        ],
    )

    def fake_post(url, *, json, timeout, allow_redirects):
        calls.append((url, json, timeout, allow_redirects))
        return Resp()

    monkeypatch.setattr(notifications.requests, "post", fake_post)
    common = {
        "now_utc": datetime(2026, 7, 9, 12, 0, 0),
        "limit_per_user": 1,
        "secret_key": "test-secret",
        "public_base_url": "https://rememate.test",
    }

    dry = run_bark_from_database(dry_run=True, **common)

    assert dry.users_seen == 1
    assert dry.sent == 1
    assert calls == []
    with bypass_engine.connect() as conn:
        assert conn.execute(text("SELECT count(*) FROM push_log")).scalar() == 0

    live = run_bark_from_database(dry_run=False, **common)

    assert live.users_seen == 1
    assert live.sent == 1
    assert len(calls) == 1
    with bypass_engine.connect() as conn:
        assert conn.execute(text(
            """
            SELECT count(*)
            FROM push_log
            WHERE idempotency_key=:key
            """
        ), {"key": f"{uid}:review:{word_id}:2026-07-09"}).scalar() == 1

    retry = run_bark_from_database(dry_run=False, **common)

    assert retry.users_seen == 1
    assert retry.sent == 0
    assert retry.skipped_duplicate == 1
    assert len(calls) == 1


def test_bark_module_dry_run_entrypoint_exits_successfully(monkeypatch):
    monkeypatch.setenv("DISPATCH_DATABASE_URL", os.environ["TEST_DISPATCH_DATABASE_URL"])

    result = subprocess.run(
        [sys.executable, "-m", "dispatch.runner", "bark", "--dry-run"],
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 0
    assert "bark reminders:" in result.stdout
