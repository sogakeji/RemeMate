from datetime import datetime

from sqlalchemy import text

from app.services import notifications, words as words_svc
from tests.helpers import provision_user


def _configure_bark(bypass_engine, uid, *, enabled=True):
    with bypass_engine.begin() as c:
        c.execute(text(
            """
            UPDATE user_settings
            SET bark_url='https://api.day.app/test-key',
                notify_review_reminder=:enabled
            WHERE user_id=:uid
            """
        ), {"uid": uid, "enabled": enabled})


def _make_due_word(bypass_engine, uid, *, word="maison", due=True):
    with bypass_engine.begin() as c:
        list_id = c.execute(text(
            """
            INSERT INTO word_lists(user_id,name,language_code,created_at)
            VALUES (:uid,'法语','fr',now()) RETURNING id
            """
        ), {"uid": uid}).scalar()
        due_expr = "timestamp '2026-07-09 11:00:00'" if due else "timestamp '2026-07-10 00:00:00'"
        word_id = c.execute(text(
            f"""
            INSERT INTO words(list_id,word,marked,due_date,interval,ease,reps,lapses)
            VALUES (:list_id,:word,false,{due_expr},1,2.5,0,0) RETURNING id
            """
        ), {"list_id": list_id, "word": word}).scalar()
        c.execute(text(
            """
            INSERT INTO definitions(word_id,part_of_speech,meaning,example)
            VALUES (:word_id,'名词','房子','La maison est bleue.')
            """
        ), {"word_id": word_id})
        return word_id


def test_review_reminder_cli_sends_due_word_and_records_push(
        app, runner, bypass_engine, monkeypatch):
    uid = provision_user(app, "remind@t.com", "pw12345678", tz="Asia/Shanghai")
    word_id = _make_due_word(bypass_engine, uid)
    _configure_bark(bypass_engine, uid)
    calls = []

    class Resp:
        status_code = 200

    monkeypatch.setattr(notifications, "utc_now", lambda: datetime(2026, 7, 9, 12, 0, 0))
    monkeypatch.setattr(
        words_svc.socket,
        "getaddrinfo",
        lambda *args, **kwargs: [(None, None, None, None, ("43.155.109.24", 443))],
    )

    def fake_post(url, *, json, timeout, allow_redirects):
        calls.append({
            "url": url,
            "json": json,
            "timeout": timeout,
            "allow_redirects": allow_redirects,
        })
        return Resp()

    monkeypatch.setattr(notifications.requests, "post", fake_post)

    result = runner.invoke(args=["send-review-reminders"])

    assert result.exit_code == 0
    assert "sent=1" in result.output
    assert calls == [{
        "url": "https://api.day.app/test-key",
        "json": {
            "title": "maison",
            "subtitle": "法语 · 待复习",
            "body": "房子",
            "group": "RemeMate",
        },
        "timeout": 5,
        "allow_redirects": False,
    }]
    with bypass_engine.connect() as c:
        row = c.execute(text(
            """
            SELECT user_id, push_type
            FROM push_log
            WHERE idempotency_key = :key
            """
        ), {"key": f"{uid}:review:{word_id}:2026-07-09"}).fetchone()
    assert row == (uid, "review_reminder")


def test_review_reminder_cli_is_idempotent_for_same_local_day(
        app, runner, bypass_engine, monkeypatch):
    uid = provision_user(app, "dupe-remind@t.com", "pw12345678", tz="Asia/Shanghai")
    _make_due_word(bypass_engine, uid)
    _configure_bark(bypass_engine, uid)
    calls = []

    class Resp:
        status_code = 200

    monkeypatch.setattr(notifications, "utc_now", lambda: datetime(2026, 7, 9, 12, 0, 0))
    monkeypatch.setattr(
        words_svc.socket,
        "getaddrinfo",
        lambda *args, **kwargs: [(None, None, None, None, ("43.155.109.24", 443))],
    )
    monkeypatch.setattr(
        notifications.requests,
        "post",
        lambda *args, **kwargs: calls.append((args, kwargs)) or Resp(),
    )

    first = runner.invoke(args=["send-review-reminders"])
    second = runner.invoke(args=["send-review-reminders"])

    assert first.exit_code == 0
    assert second.exit_code == 0
    assert "sent=1" in first.output
    assert "sent=0" in second.output
    assert "duplicates=1" in second.output
    assert len(calls) == 1


def test_review_reminder_cli_skips_users_without_due_words(
        app, runner, bypass_engine, monkeypatch):
    uid = provision_user(app, "not-due@t.com", "pw12345678")
    _make_due_word(bypass_engine, uid, due=False)
    _configure_bark(bypass_engine, uid)

    def fail_post(*args, **kwargs):
        raise AssertionError("should not send without due words")

    monkeypatch.setattr(notifications.requests, "post", fail_post)

    result = runner.invoke(args=["send-review-reminders"])

    assert result.exit_code == 0
    assert "sent=0" in result.output
    assert "no_due=1" in result.output


def test_build_review_reminder_payload_includes_due_count():
    class Row:
        word = "maison"
        language_code = "fr"
        meaning = "房子"
        example = "La maison est bleue."

    payload = notifications.build_review_reminder_payload(Row, due_count=3)

    assert payload == {
        "title": "maison",
        "subtitle": "法语 · 待复习",
        "body": "房子\n还有 3 个词待复习。",
        "group": "RemeMate",
    }
