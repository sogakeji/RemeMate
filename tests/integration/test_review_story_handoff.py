"""RS3 slice 2: story-to-writing handoff through public HTTP behavior."""
from __future__ import annotations

import pytest
from sqlalchemy import text

from tests.helpers import login, provision_user
from tests.integration.test_review_story_receipt import (
    PW,
    _ValidStoryProvider,
    _seed_review_day,
)


@pytest.fixture(autouse=True)
def _reset_story_provider():
    yield
    from app.services import llm

    llm.set_registry(None)
    llm.reset_breaker()


def _generate_ready_story(app, client, bypass_engine, *, email):
    from app.services import llm

    provider = _ValidStoryProvider()
    llm.set_registry({"general": [provider]})
    llm.reset_breaker()
    uid, _ = _seed_review_day(
        app,
        client,
        bypass_engine,
        email=email,
        grades=[5] * 10,
    )
    response = client.post(
        "/review/story",
        headers={"HX-Request": "true"},
    )
    assert response.status_code == 200
    assert 'data-state="ready"' in response.get_data(as_text=True)

    with bypass_engine.connect() as connection:
        run_id, term_word_ids = connection.execute(text(
            "SELECT id, term_word_ids FROM review_story_runs "
            "WHERE user_id=:uid AND status='ready'"
        ), {"uid": uid}).one()
        term_key = sorted(term_word_ids)[-1]
        word_id = int(term_word_ids[term_key])
        word = connection.execute(text(
            "SELECT word FROM words WHERE id=:word_id"
        ), {"word_id": word_id}).scalar_one()
    return uid, run_id, term_key, word_id, word


def test_ready_story_handoff_selects_server_owned_word_without_saving(
    app,
    client,
    bypass_engine,
):
    uid, run_id, term_key, word_id, word = _generate_ready_story(
        app,
        client,
        bypass_engine,
        email="receipt-handoff@t.com",
    )

    cached = client.post(
        "/review/story",
        headers={"HX-Request": "true"},
    )
    cached_body = cached.get_data(as_text=True)
    assert 'action="/write/from-story"' in cached_body
    assert f'value="{run_id}"' in cached_body
    assert f'value="{term_key}"' in cached_body

    page = client.post(
        "/write/from-story",
        data={"story_run_id": run_id, "term_key": term_key},
        follow_redirects=True,
    )
    body = page.get_data(as_text=True)

    assert page.status_code == 200
    assert word in body
    assert 'name="story_handoff" value="1"' in body
    assert "从今日复习故事中选择" in body
    with bypass_engine.connect() as connection:
        assert connection.execute(text(
            "SELECT count(*) FROM output_entries WHERE user_id=:uid"
        ), {"uid": uid}).scalar_one() == 0
        assert connection.execute(text(
            "SELECT count(*) FROM learning_funnel_events "
            "WHERE user_id=:uid "
            "AND event_type='story_writing_handoff'"
        ), {"uid": uid}).scalar_one() == 1
        assert connection.execute(text(
            "SELECT id FROM words WHERE id=:word_id"
        ), {"word_id": word_id}).scalar_one() == word_id


def test_story_handoff_rejects_unknown_term_and_cross_user_run(
    app,
    client,
    bypass_engine,
):
    owner, run_id, term_key, _, _ = _generate_ready_story(
        app,
        client,
        bypass_engine,
        email="receipt-handoff-owner@t.com",
    )

    unknown = client.post(
        "/write/from-story",
        data={"story_run_id": run_id, "term_key": "not-a-term"},
    )
    assert unknown.status_code == 404

    client.get("/logout")
    peer = provision_user(
        app,
        "receipt-handoff-peer@t.com",
        PW,
        tz="UTC",
    )
    login(client, "receipt-handoff-peer@t.com", PW)
    cross_user = client.post(
        "/write/from-story",
        data={"story_run_id": run_id, "term_key": term_key},
    )
    assert cross_user.status_code == 404

    with bypass_engine.connect() as connection:
        count = connection.execute(text(
            "SELECT count(*) FROM learning_funnel_events "
            "WHERE event_type='story_writing_handoff' "
            "AND user_id IN (:owner, :peer)"
        ), {"owner": owner, "peer": peer}).scalar_one()
    assert count == 0


def test_story_output_event_is_recorded_only_after_explicit_save(
    app,
    client,
    bypass_engine,
    fake_llm,
):
    uid, run_id, term_key, word_id, word = _generate_ready_story(
        app,
        client,
        bypass_engine,
        email="receipt-attributed-save@t.com",
    )
    handoff = client.post(
        "/write/from-story",
        data={"story_run_id": run_id, "term_key": term_key},
        follow_redirects=True,
    )
    assert handoff.status_code == 200

    fake_llm["reinstall"]()
    corrected = client.post(
        "/write/submit",
        data={
            "mode": "sentence",
            "word_id": word_id,
            "story_handoff": "1",
            "sentence": f"J'utilise {word}.",
        },
    )
    assert corrected.status_code == 200
    assert "保存" in corrected.get_data(as_text=True)

    with bypass_engine.connect() as connection:
        assert connection.execute(text(
            "SELECT count(*) FROM output_entries WHERE user_id=:uid"
        ), {"uid": uid}).scalar_one() == 0
        assert connection.execute(text(
            "SELECT count(*) FROM learning_funnel_events "
            "WHERE user_id=:uid AND event_type='story_output_saved'"
        ), {"uid": uid}).scalar_one() == 0

    saved = client.post("/write/save")
    assert saved.status_code == 200
    assert "已保存到造句历史" in saved.get_data(as_text=True)

    replay = client.post("/write/save")
    assert "过期" in replay.get_data(as_text=True)
    with bypass_engine.connect() as connection:
        assert connection.execute(text(
            "SELECT count(*) FROM output_entries "
            "WHERE user_id=:uid AND word_id=:word_id"
        ), {"uid": uid, "word_id": word_id}).scalar_one() == 1
        assert connection.execute(text(
            "SELECT count(*) FROM learning_funnel_events "
            "WHERE user_id=:uid AND event_type='story_output_saved'"
        ), {"uid": uid}).scalar_one() == 1


def test_story_handoff_rejects_expired_ready_run(
    app,
    client,
    bypass_engine,
):
    uid, run_id, term_key, _, _ = _generate_ready_story(
        app,
        client,
        bypass_engine,
        email="receipt-handoff-expired@t.com",
    )
    with bypass_engine.begin() as connection:
        connection.execute(text(
            "UPDATE review_story_runs "
            "SET content_expires_at=now() - interval '1 second' "
            "WHERE id=:run_id"
        ), {"run_id": run_id})

    response = client.post(
        "/write/from-story",
        data={"story_run_id": run_id, "term_key": term_key},
    )
    assert response.status_code == 404
    with bypass_engine.connect() as connection:
        assert connection.execute(text(
            "SELECT count(*) FROM learning_funnel_events "
            "WHERE user_id=:uid "
            "AND event_type='story_writing_handoff'"
        ), {"uid": uid}).scalar_one() == 0


def test_observation_failure_does_not_block_handoff_or_saved_output(
    app,
    client,
    bypass_engine,
    fake_llm,
    monkeypatch,
):
    from app.blueprints.write import routes

    uid, run_id, term_key, word_id, word = _generate_ready_story(
        app,
        client,
        bypass_engine,
        email="receipt-handoff-observation-down@t.com",
    )

    def fail_observation(**_kwargs):
        raise RuntimeError("observation unavailable")

    monkeypatch.setattr(
        routes.story_events_svc,
        "record_review_story_event",
        fail_observation,
    )
    handoff = client.post(
        "/write/from-story",
        data={"story_run_id": run_id, "term_key": term_key},
        follow_redirects=True,
    )
    assert handoff.status_code == 200
    assert word in handoff.get_data(as_text=True)

    fake_llm["reinstall"]()
    corrected = client.post(
        "/write/submit",
        data={
            "mode": "sentence",
            "word_id": word_id,
            "story_handoff": "1",
            "sentence": f"J'utilise {word}.",
        },
    )
    assert corrected.status_code == 200
    saved = client.post("/write/save")
    assert saved.status_code == 200
    assert "已保存到造句历史" in saved.get_data(as_text=True)

    with bypass_engine.connect() as connection:
        assert connection.execute(text(
            "SELECT count(*) FROM output_entries "
            "WHERE user_id=:uid AND word_id=:word_id"
        ), {"uid": uid, "word_id": word_id}).scalar_one() == 1


def test_story_handoff_does_not_change_global_language_preferences(
    app,
    client,
    bypass_engine,
    fake_llm,
):
    uid, run_id, term_key, word_id, word = _generate_ready_story(
        app,
        client,
        bypass_engine,
        email="receipt-handoff-language@t.com",
    )
    with bypass_engine.begin() as connection:
        connection.execute(text(
            "UPDATE users SET current_language='en', learning_languages='en' "
            "WHERE id=:uid"
        ), {"uid": uid})

    handoff = client.post(
        "/write/from-story",
        data={"story_run_id": run_id, "term_key": term_key},
        follow_redirects=True,
    )

    assert handoff.status_code == 200
    assert word in handoff.get_data(as_text=True)
    with bypass_engine.connect() as connection:
        preferences = connection.execute(text(
            "SELECT current_language, learning_languages "
            "FROM users WHERE id=:uid"
        ), {"uid": uid}).one()
    assert preferences == ("en", "en")

    fake_llm["reinstall"]()
    corrected = client.post(
        "/write/submit",
        data={
            "mode": "sentence",
            "word_id": word_id,
            "story_handoff": "1",
            "sentence": f"J'utilise {word}.",
        },
    )

    assert corrected.status_code == 200
    assert "保存" in corrected.get_data(as_text=True)
    with bypass_engine.connect() as connection:
        preferences = connection.execute(text(
            "SELECT current_language, learning_languages "
            "FROM users WHERE id=:uid"
        ), {"uid": uid}).one()
    assert preferences == ("en", "en")
