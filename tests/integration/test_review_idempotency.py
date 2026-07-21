"""Review grading is exactly-once per due-state across web and Bark."""
from concurrent.futures import ThreadPoolExecutor
from threading import Barrier

import pytest
from sqlalchemy import event, text
from sqlalchemy.orm import Session

from app.services import review_links
from tests.helpers import (
    login,
    make_word,
    provision_user,
    review_attempt_version,
)

PW = "pw12345678"


def _setup_review_user(app, client, bypass_engine, email):
    uid = provision_user(app, email, PW)
    with bypass_engine.begin() as c:
        c.execute(text(
            "UPDATE users "
            "SET learning_languages='fr',current_language='fr' "
            "WHERE id=:uid"
        ), {"uid": uid})
    _, word_id = make_word(bypass_engine, uid, word="maison")
    with bypass_engine.begin() as c:
        c.execute(text(
            "UPDATE words "
            "SET due_date=timezone('UTC', now())-interval '1 second' "
            "WHERE id=:word_id"
        ), {"word_id": word_id})
    login(client, email, PW)
    return uid, word_id, review_attempt_version(bypass_engine, word_id)


def _grade(client, word_id, button, expected_due_at):
    return client.post(
        f"/review/{word_id}/grade",
        data={
            "button": button,
            "expected_due_at": expected_due_at,
        },
    )


def _state(bypass_engine, word_id):
    with bypass_engine.connect() as c:
        word = c.execute(text(
            "SELECT reps,lapses,interval,ease,due_date "
            "FROM words WHERE id=:word_id"
        ), {"word_id": word_id}).one()
        logs = c.execute(text(
            "SELECT grade,source FROM review_logs "
            "WHERE word_id=:word_id ORDER BY id"
        ), {"word_id": word_id}).all()
    return word, logs


def test_review_card_submits_canonical_attempt_version(
    app, client, bypass_engine,
):
    _, word_id, due_version = _setup_review_user(
        app, client, bypass_engine, "review-version@t.com",
    )

    page = client.get("/").get_data(as_text=True)

    assert f'"expected_due_at":"{due_version}"' in page
    assert page.count('"expected_due_at"') == 3
    assert f"/review/{word_id}/grade" in page


@pytest.mark.parametrize("expected_due_at", [
    None,
    "",
    "2026-07-09",
    "2026-07-09T11:00:00",
    "2026-07-09T11:00:00.000000Z",
    "2026-07-09T11:00:00.000000+00:00",
])
def test_review_grade_rejects_missing_or_noncanonical_attempt_version(
    app, client, bypass_engine, expected_due_at,
):
    _, word_id, _ = _setup_review_user(
        app, client, bypass_engine,
        f"bad-review-version-{str(expected_due_at)}@t.com",
    )
    data = {"button": "easy"}
    if expected_due_at is not None:
        data["expected_due_at"] = expected_due_at

    response = client.post(f"/review/{word_id}/grade", data=data)

    assert response.status_code == 400
    word, logs = _state(bypass_engine, word_id)
    assert (word.reps, word.lapses) == (0, 0)
    assert logs == []


def test_same_review_attempt_replay_advances_only_once(
    app, client, bypass_engine,
):
    _, word_id, due_version = _setup_review_user(
        app, client, bypass_engine, "review-replay@t.com",
    )

    first = _grade(client, word_id, "easy", due_version)
    replay = _grade(client, word_id, "forgot", due_version)

    assert first.status_code == 200
    assert replay.status_code == 200
    word, logs = _state(bypass_engine, word_id)
    assert (word.reps, word.lapses, word.interval) == (1, 0, 1)
    assert logs == [(5, "review")]


def test_stale_attempt_does_not_replace_previous_word_session(
    app, client, bypass_engine,
):
    _, first_id, first_version = _setup_review_user(
        app, client, bypass_engine, "review-previous@t.com",
    )
    added = client.post("/words/add", json={
        "language_code": "fr",
        "word": "deuxieme",
        "definitions": [{"meaning": "second"}],
    })
    assert added.status_code == 200
    second_id = added.get_json()["word_id"]
    second_version = review_attempt_version(bypass_engine, second_id)

    assert _grade(
        client, first_id, "easy", first_version,
    ).status_code == 200
    assert _grade(
        client, second_id, "easy", second_version,
    ).status_code == 200
    with client.session_transaction() as session:
        assert session["review_previous_word_id"] == second_id

    stale = _grade(client, first_id, "forgot", first_version)

    assert stale.status_code == 200
    with client.session_transaction() as session:
        assert session["review_previous_word_id"] == second_id
    first, first_logs = _state(bypass_engine, first_id)
    second, second_logs = _state(bypass_engine, second_id)
    assert (first.reps, first.lapses) == (1, 0)
    assert (second.reps, second.lapses) == (1, 0)
    assert first_logs == [(5, "review")]
    assert second_logs == [(5, "review")]


def test_concurrent_web_grades_advance_only_once(
    app, client, bypass_engine,
):
    email = "review-concurrent@t.com"
    _, word_id, due_version = _setup_review_user(
        app, client, bypass_engine, email,
    )
    barrier = Barrier(2)

    def submit(button):
        with app.test_client() as thread_client:
            login(thread_client, email, PW)
            barrier.wait(timeout=5)
            return _grade(
                thread_client, word_id, button, due_version,
            ).status_code

    with ThreadPoolExecutor(max_workers=2) as pool:
        statuses = list(pool.map(submit, ("easy", "forgot")))

    assert statuses == [200, 200]
    word, logs = _state(bypass_engine, word_id)
    assert len(logs) == 1
    assert (word.reps, word.lapses) in {(1, 0), (0, 1)}


def test_forgot_replay_is_ignored_but_new_due_version_can_be_graded(
    app, client, bypass_engine,
):
    _, word_id, first_version = _setup_review_user(
        app, client, bypass_engine, "review-lapse@t.com",
    )

    first = _grade(client, word_id, "forgot", first_version)
    replay = _grade(client, word_id, "easy", first_version)
    assert first.status_code == replay.status_code == 200
    word, logs = _state(bypass_engine, word_id)
    assert (word.reps, word.lapses) == (0, 1)
    assert logs == [(2, "review")]

    # Simulate the ten-minute delay elapsing while preserving the new attempt
    # version that the next rendered card would submit.
    with bypass_engine.begin() as c:
        c.execute(text(
            "UPDATE words "
            "SET due_date=timezone('UTC', now())-interval '1 second' "
            "WHERE id=:word_id"
        ), {"word_id": word_id})
    second_version = review_attempt_version(bypass_engine, word_id)

    second = _grade(client, word_id, "easy", second_version)

    assert second.status_code == 200
    word, logs = _state(bypass_engine, word_id)
    assert (word.reps, word.lapses) == (1, 1)
    assert logs == [(2, "review"), (5, "review")]


def test_failed_transaction_keeps_attempt_retryable(
    app, client, bypass_engine,
):
    _, word_id, due_version = _setup_review_user(
        app, client, bypass_engine, "review-retry@t.com",
    )
    failed = False

    def fail_after_flush(session, flush_context):
        nonlocal failed
        if not failed:
            failed = True
            raise RuntimeError("forced post-flush failure")

    event.listen(Session, "after_flush", fail_after_flush)
    try:
        with pytest.raises(RuntimeError, match="forced post-flush failure"):
            _grade(client, word_id, "easy", due_version)
    finally:
        event.remove(Session, "after_flush", fail_after_flush)

    word, logs = _state(bypass_engine, word_id)
    assert (word.reps, word.lapses) == (0, 0)
    assert review_attempt_version(bypass_engine, word_id) == due_version
    assert logs == []

    retry = _grade(client, word_id, "easy", due_version)

    assert retry.status_code == 200
    word, logs = _state(bypass_engine, word_id)
    assert (word.reps, word.lapses) == (1, 0)
    assert logs == [(5, "review")]


def _bark_token(app, uid, word_id):
    return review_links.make_review_token(
        app.config["SECRET_KEY"], uid, word_id,
    )


def test_web_then_bark_does_not_double_advance(
    app, client, bypass_engine,
):
    uid, word_id, due_version = _setup_review_user(
        app, client, bypass_engine, "review-web-bark@t.com",
    )
    token = _bark_token(app, uid, word_id)

    web = _grade(client, word_id, "easy", due_version)
    bark = client.post(
        f"/bark/review/{token}/grade",
        data={"button": "forgot"},
    )

    assert web.status_code == bark.status_code == 200
    assert "已经回流过" in bark.get_data(as_text=True)
    word, logs = _state(bypass_engine, word_id)
    assert (word.reps, word.lapses) == (1, 0)
    assert logs == [(5, "review")]


def test_bark_then_web_does_not_double_advance(
    app, client, bypass_engine,
):
    uid, word_id, due_version = _setup_review_user(
        app, client, bypass_engine, "review-bark-web@t.com",
    )
    token = _bark_token(app, uid, word_id)

    bark = client.post(
        f"/bark/review/{token}/grade",
        data={"button": "easy"},
    )
    web = _grade(client, word_id, "forgot", due_version)

    assert bark.status_code == web.status_code == 200
    word, logs = _state(bypass_engine, word_id)
    assert (word.reps, word.lapses) == (1, 0)
    assert logs == [(5, "bark")]


def test_concurrent_web_and_bark_advance_only_once(
    app, client, bypass_engine,
):
    email = "review-web-bark-concurrent@t.com"
    uid, word_id, due_version = _setup_review_user(
        app, client, bypass_engine, email,
    )
    token = _bark_token(app, uid, word_id)
    barrier = Barrier(2)

    def submit_web():
        with app.test_client() as thread_client:
            login(thread_client, email, PW)
            barrier.wait(timeout=5)
            return _grade(
                thread_client, word_id, "easy", due_version,
            ).status_code

    def submit_bark():
        with app.test_client() as thread_client:
            barrier.wait(timeout=5)
            return thread_client.post(
                f"/bark/review/{token}/grade",
                data={"button": "easy"},
            ).status_code

    with ThreadPoolExecutor(max_workers=2) as pool:
        web_future = pool.submit(submit_web)
        bark_future = pool.submit(submit_bark)
        statuses = [web_future.result(), bark_future.result()]

    assert statuses == [200, 200]
    word, logs = _state(bypass_engine, word_id)
    assert (word.reps, word.lapses) == (1, 0)
    assert len(logs) == 1
    assert logs[0][0] == 5
