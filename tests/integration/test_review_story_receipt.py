"""RS3 slice 1: optional post-review story receipt over HTTP/HTMX."""
from __future__ import annotations

import json

import pytest
from sqlalchemy import text

from tests.helpers import login, provision_user, review_attempt_version


PW = "pw12345678"


@pytest.fixture(autouse=True)
def _reset_story_provider():
    yield
    from app.services import llm

    llm.set_registry(None)
    llm.reset_breaker()


class _ValidStoryProvider:
    name = "fake-receipt"

    def __init__(self):
        self.calls = 0

    def call(self, messages, *, timeout, json_mode=False):
        from app.services import llm

        self.calls += 1
        return llm.LLMResult(
            json.dumps(
                {
                    "title": {
                        "target": "Une journée",
                        "translation": "一天",
                    },
                    "sentences": [
                        {
                            "target": "Je vois mot-un.",
                            "translation": "我看见词一。",
                            "terms": [{
                                "key": "t1",
                                "target_form": "mot-un",
                                "translation_form": "词一",
                            }],
                        },
                        {
                            "target": "Je vois mot-deux.",
                            "translation": "我看见词二。",
                            "terms": [{
                                "key": "t2",
                                "target_form": "mot-deux",
                                "translation_form": "词二",
                            }],
                        },
                        {
                            "target": "Je vois mot-trois.",
                            "translation": "我看见词三。",
                            "terms": [{
                                "key": "t3",
                                "target_form": "mot-trois",
                                "translation_form": "词三",
                            }],
                        },
                        {
                            "target": "Je vois mot-quatre et mot-cinq.",
                            "translation": "我看见词四和词五。",
                            "terms": [
                                {
                                    "key": "t4",
                                    "target_form": "mot-quatre",
                                    "translation_form": "词四",
                                },
                                {
                                    "key": "t5",
                                    "target_form": "mot-cinq",
                                    "translation_form": "词五",
                                },
                            ],
                        },
                    ],
                },
                ensure_ascii=False,
            ),
            11,
            17,
            self.name,
            "receipt-model",
        )


def _seed_review_day(
    app,
    client,
    bypass_engine,
    *,
    email,
    grades,
    add_due_word=False,
):
    uid = provision_user(app, email, PW, tz="UTC")
    login(client, email, PW)
    client.post("/language/switch", data={"language_code": "fr"})

    with bypass_engine.begin() as connection:
        list_id = connection.execute(text(
            "SELECT id FROM word_lists "
            "WHERE user_id=:uid AND language_code='fr'"
        ), {"uid": uid}).scalar_one()
        for index, grade in enumerate(grades):
            word_id = connection.execute(text(
                "INSERT INTO words("
                "list_id,word,marked,due_date,interval,ease,reps,lapses"
                ") VALUES ("
                ":list_id,:word,false,now() + interval '1 day',1,2.5,1,0"
                ") RETURNING id"
            ), {
                "list_id": list_id,
                "word": f"receipt-{index}",
            }).scalar_one()
            connection.execute(text(
                "INSERT INTO definitions("
                "word_id,part_of_speech,meaning"
                ") VALUES (:word_id,'n.',:meaning)"
            ), {
                "word_id": word_id,
                "meaning": f"meaning-{index}",
            })
            connection.execute(text(
                "INSERT INTO review_logs("
                "word_id,user_id,ts,grade,source,interval_after"
                ") VALUES (:word_id,:uid,now(),:grade,'review',1)"
            ), {
                "word_id": word_id,
                "uid": uid,
                "grade": grade,
            })

        due_word_id = None
        if add_due_word:
            due_word_id = connection.execute(text(
                "INSERT INTO words("
                "list_id,word,marked,due_date,interval,ease,reps,lapses"
                ") VALUES ("
                ":list_id,'receipt-due',false,now(),1,2.5,0,0"
                ") RETURNING id"
            ), {"list_id": list_id}).scalar_one()
            connection.execute(text(
                "INSERT INTO definitions("
                "word_id,part_of_speech,meaning"
                ") VALUES (:word_id,'n.','due meaning')"
            ), {"word_id": due_word_id})
    return uid, due_word_id


def test_silent_completion_does_not_render_story_receipt(
    app,
    client,
    bypass_engine,
):
    _seed_review_day(
        app,
        client,
        bypass_engine,
        email="receipt-silent@t.com",
        grades=[],
    )

    page = client.get("/")
    body = page.get_data(as_text=True)

    assert page.status_code == 200
    assert 'id="review-story-receipt"' not in body
    assert "今日复习完成" in body
    assert "回到词库" in body


def test_eligible_receipt_calls_provider_only_after_click_and_reuses_cache(
    app,
    client,
    bypass_engine,
):
    from app.services import llm

    provider = _ValidStoryProvider()
    llm.set_registry({"general": [provider]})
    llm.reset_breaker()
    _seed_review_day(
        app,
        client,
        bypass_engine,
        email="receipt-normal@t.com",
        grades=[5] * 10,
    )

    home = client.get("/").get_data(as_text=True)
    compatibility_page = client.get("/review").get_data(as_text=True)

    assert 'id="review-story-receipt"' in home
    assert 'data-state="normal"' in home
    assert "生成小故事" in home
    assert 'id="review-story-receipt"' in compatibility_page
    assert provider.calls == 0

    generated = client.post(
        "/review/story",
        headers={"HX-Request": "true"},
    )
    generated_body = generated.get_data(as_text=True)
    assert generated.status_code == 200
    assert 'data-state="ready"' in generated_body
    assert "Une journée" in generated_body
    assert "我看见词一" in generated_body
    assert provider.calls == 1

    cached = client.post(
        "/review/story",
        headers={"HX-Request": "true"},
    )
    assert cached.status_code == 200
    assert 'data-state="cached"' in cached.get_data(as_text=True)
    assert provider.calls == 1


def test_strong_receipt_is_visible_without_automatic_generation(
    app,
    client,
    bypass_engine,
):
    from app.services import llm

    provider = _ValidStoryProvider()
    llm.set_registry({"general": [provider]})
    llm.reset_breaker()
    _seed_review_day(
        app,
        client,
        bypass_engine,
        email="receipt-strong@t.com",
        grades=[2] * 3 + [3] * 3 + [5] * 4,
    )

    body = client.get("/").get_data(as_text=True)

    assert 'data-state="strong"' in body
    assert "模糊或遗忘的词有点多" in body
    assert provider.calls == 0


def test_last_grade_response_adds_receipt_without_generating(
    app,
    client,
    bypass_engine,
):
    from app.services import llm

    provider = _ValidStoryProvider()
    llm.set_registry({"general": [provider]})
    llm.reset_breaker()
    _, due_word_id = _seed_review_day(
        app,
        client,
        bypass_engine,
        email="receipt-last-grade@t.com",
        grades=[5] * 9,
        add_due_word=True,
    )

    response = client.post(
        f"/review/{due_word_id}/grade",
        data={
            "button": "easy",
            "expected_due_at": review_attempt_version(
                bypass_engine,
                due_word_id,
            ),
        },
        headers={"HX-Request": "true"},
    )
    body = response.get_data(as_text=True)

    assert response.status_code == 200
    assert "今日复习完成" in body
    assert 'data-state="normal"' in body
    assert provider.calls == 0


def test_story_is_available_after_threshold_with_due_words_remaining(
    app,
    client,
    bypass_engine,
):
    from app.services import llm

    provider = _ValidStoryProvider()
    llm.set_registry({"general": [provider]})
    llm.reset_breaker()
    _seed_review_day(
        app,
        client,
        bypass_engine,
        email="receipt-incomplete@t.com",
        grades=[5] * 10,
        add_due_word=True,
    )

    page = client.get("/").get_data(as_text=True)
    response = client.post(
        "/review/story",
        headers={"HX-Request": "true"},
    )
    body = response.get_data(as_text=True)

    assert "receipt-due" in page
    assert 'class="srs-grade-group"' in page
    assert "今日复习完成" not in page
    assert 'id="review-story-receipt"' in page
    assert page.index('class="srs-grade-group"') < page.index('id="review-story-receipt"')
    assert response.status_code == 200
    assert 'data-state="ready"' in body
    assert provider.calls == 1


def test_provider_failure_stays_inside_receipt_and_offers_one_retry(
    app,
    client,
    bypass_engine,
):
    from app.services import llm

    llm.set_registry({"general": []})
    llm.reset_breaker()
    _seed_review_day(
        app,
        client,
        bypass_engine,
        email="receipt-provider-down@t.com",
        grades=[5] * 10,
    )

    response = client.post(
        "/review/story",
        headers={"HX-Request": "true"},
    )
    body = response.get_data(as_text=True)

    assert response.status_code == 200
    assert 'id="review-story-receipt"' in body
    assert 'data-state="failed"' in body
    assert "复习记录不受影响" in body
    assert 'name="retry"' in body
