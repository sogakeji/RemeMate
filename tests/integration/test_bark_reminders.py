from datetime import datetime

from sqlalchemy import text

from app.services import notifications, review_links, words as words_svc
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
    app.config["PUBLIC_BASE_URL"] = "https://rememate.test"
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
            "body": "有单词到期了，回来复习一下。",
            "group": "RemeMate",
            "url": calls[0]["json"]["url"],
        },
        "timeout": 5,
        "allow_redirects": False,
    }]
    assert calls[0]["json"]["url"].startswith(
        "https://rememate.test/bark/review/v1.")
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

    monkeypatch.setattr(
        notifications, "utc_now", lambda: datetime(2026, 7, 9, 12, 0, 0))
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
        "body": "有单词到期了，回来复习一下。\n还有 3 个词待复习。",
        "group": "RemeMate",
    }
    assert "房子" not in payload["body"]


def test_bark_review_link_opens_public_card_and_records_grade(
        app, client, bypass_engine):
    uid = provision_user(app, "link@t.com", "pw12345678", tz="Asia/Shanghai")
    word_id = _make_due_word(bypass_engine, uid)
    token = review_links.make_review_token(app.config["SECRET_KEY"], uid, word_id)

    page = client.get(f"/bark/review/{token}")
    body = page.get_data(as_text=True)
    assert page.status_code == 200
    assert "maison" in body
    assert "没记住" in body and "有点模糊" in body and "秒记起" in body
    assert "/login" not in page.headers.get("Location", "")

    graded = client.post(f"/bark/review/{token}/grade", data={"button": "easy"})
    graded_body = graded.get_data(as_text=True)
    assert graded.status_code == 200
    assert "已回流到你的复习计划" in graded_body
    with bypass_engine.connect() as c:
        row = c.execute(text(
            """
            SELECT w.reps, w.interval, rl.grade, rl.source
            FROM words w
            JOIN review_logs rl ON rl.word_id = w.id
            WHERE w.id = :word_id
            """
        ), {"word_id": word_id}).fetchone()
    assert row == (1, 1, 5, "bark")


def test_bark_review_link_is_single_use_for_grading(
        app, client, bypass_engine):
    uid = provision_user(app, "single-use@t.com", "pw12345678", tz="Asia/Shanghai")
    word_id = _make_due_word(bypass_engine, uid)
    token = review_links.make_review_token(app.config["SECRET_KEY"], uid, word_id)

    first = client.post(f"/bark/review/{token}/grade", data={"button": "easy"})
    second = client.post(f"/bark/review/{token}/grade", data={"button": "forgot"})

    assert first.status_code == 200
    assert second.status_code == 200
    assert "已经回流过" in second.get_data(as_text=True)
    with bypass_engine.connect() as c:
        logs = c.execute(text(
            "SELECT count(*) FROM review_logs WHERE word_id=:word_id"),
            {"word_id": word_id}).scalar()
        reps = c.execute(text(
            "SELECT reps FROM words WHERE id=:word_id"),
            {"word_id": word_id}).scalar()
    assert logs == 1
    assert reps == 1


def test_bark_review_link_rejects_invalid_token(client):
    page = client.get("/bark/review/not-a-token")
    assert page.status_code == 410


def test_invalid_bark_review_token_renders_english(client):
    page = client.get(
        "/bark/review/not-a-token",
        headers={"Accept-Language": "en"},
    )

    body = page.get_data(as_text=True)
    assert page.status_code == 410
    assert '<html lang="en">' in body
    assert "Link unavailable" in body
    assert "This Bark review link has expired" in body
    assert "链接失效" not in body
