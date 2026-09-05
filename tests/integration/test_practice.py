"""Authenticated HTTP behavior for French contextual dictation practice."""

import re

from sqlalchemy import text

from tests.helpers import login, make_word, provision_user


PW = "pw12345678"


def _session_id_from_url(session_url):
    return int(session_url.rstrip("/").split("/")[-1])


def _post_continue(client, session_url):
    session_id = _session_id_from_url(session_url)
    response = client.post(session_url.rstrip("/") + "/continue")
    assert response.status_code == 303
    location = response.headers["Location"]
    assert location.rstrip("/").endswith(f"/practice/{session_id}")
    return client.get(location)


_UI_SWITCH_FORM = re.compile(
    r'<form[^>]*class="ui-locale-form"[^>]*>.*?'
    r'name="ui_locale" value="(?P<locale>[^"]*)".*?'
    r'name="next" value="(?P<next>[^"]*)"',
    re.S,
)


def _ui_switch_fields(html):
    match = _UI_SWITCH_FORM.search(html)
    assert match is not None
    return match.group("locale"), match.group("next")


def _follow_redirect(client, response):
    assert response.status_code in {301, 302, 303, 307, 308}
    return client.get(response.headers["Location"])


def _start_zh_practice(app, client, bypass_engine, email, learning="zh"):
    user_id = provision_user(app, email, PW)
    with bypass_engine.begin() as connection:
        connection.execute(text(
            "UPDATE users SET current_language='zh', learning_languages=:learning "
            "WHERE id=:user_id"
        ), {"user_id": user_id, "learning": learning})
    _seed_examples(
        bypass_engine,
        user_id,
        language_code="zh",
        words=["学校"],
        examples=["今天我去学校上课。"],
    )
    login(client, email, PW)
    started = client.post("/practice/start", data={"voice_available": "1"})
    assert started.status_code == 303
    return user_id, started.headers["Location"]


def _seed_examples(
    bypass_engine, user_id, count=None, words=None, examples=None,
    language_code="fr",
):
    words = words or [f"mot{index}" for index in range(count)]
    examples = examples or [f"Je connais {word} aujourd'hui." for word in words]
    with bypass_engine.begin() as connection:
        list_id = connection.execute(text(
            "INSERT INTO word_lists(user_id, name, language_code, created_at) "
            "VALUES (:user_id, 'Practice', :language_code, now()) RETURNING id"
        ), {"user_id": user_id, "language_code": language_code}).scalar_one()
        for index, word in enumerate(words):
            word_id = connection.execute(text(
                "INSERT INTO words(list_id, word, marked, due_date, interval, ease, reps, lapses) "
                "VALUES (:list_id, :word, false, CURRENT_TIMESTAMP AT TIME ZONE 'UTC' - interval '1 second', 1, 2.5, 0, 0) RETURNING id"
            ), {"list_id": list_id, "word": word}).scalar_one()
            connection.execute(text(
                "INSERT INTO definitions(word_id, meaning, example) "
                "VALUES (:word_id, :meaning, :example)"
            ), {
                "word_id": word_id,
                "meaning": f"meaning {index}",
                "example": examples[index],
            })


def test_french_learner_sees_practice_start_with_eligible_count(
    app, client, bypass_engine,
):
    user_id = provision_user(app, "practice-start@t.com", PW)
    with bypass_engine.begin() as connection:
        connection.execute(text(
            "UPDATE users SET current_language='fr', learning_languages='fr' "
            "WHERE id=:user_id"
        ), {"user_id": user_id})
    _, word_id = make_word(bypass_engine, user_id, word="voudrais")
    with bypass_engine.begin() as connection:
        connection.execute(text(
            "UPDATE words SET due_date=CURRENT_TIMESTAMP AT TIME ZONE 'UTC' - interval '1 second' "
            "WHERE id=:word_id"
        ), {"word_id": word_id})
        connection.execute(text(
            "INSERT INTO definitions(word_id, meaning, example) "
            "VALUES (:word_id, '想要', 'Je voudrais un café.')"
        ), {"word_id": word_id})

    login(client, "practice-start@t.com", PW)

    response = client.get("/practice")

    assert response.status_code == 200
    body = response.get_data(as_text=True)
    assert "听写" in body
    assert "1 道题" in body
    assert 'data-practice-screen="start"' in body
    assert 'data-practice-voice-select' in body
    assert 'data-practice-rate-select' in body
    assert 'data-practice-preview' in body


def test_japanese_learner_sees_practice_start_with_eligible_count(
    app, client, bypass_engine,
):
    user_id = provision_user(app, "practice-ja-start@t.com", PW)
    with bypass_engine.begin() as connection:
        connection.execute(text(
            "UPDATE users SET current_language='ja', learning_languages='ja' "
            "WHERE id=:user_id"
        ), {"user_id": user_id})
    _seed_examples(
        bypass_engine,
        user_id,
        language_code="ja",
        words=["学校"],
        examples=["今日は学校に行きます。"],
    )
    login(client, "practice-ja-start@t.com", PW)

    response = client.get("/practice")

    assert response.status_code == 200
    body = response.get_data(as_text=True)
    assert "1 道题" in body
    assert 'data-practice-screen="start"' in body
    assert "data-practice-start" in body
    assert "法语" not in body
    assert 'data-practice-voice-lang="ja"' in body
    assert 'data-practice-voice-locale="ja-JP"' in body


def test_japanese_device_examples_open_start_and_session(
    app, client, bypass_engine,
):
    user_id = provision_user(app, "practice-ja-device@t.com", PW)
    with bypass_engine.begin() as connection:
        connection.execute(text(
            "UPDATE users SET current_language='ja', learning_languages='ja' "
            "WHERE id=:user_id"
        ), {"user_id": user_id})
    _seed_examples(
        bypass_engine,
        user_id,
        language_code="ja",
        words=["学校", "コーヒー", "音楽", "電車", "友達"],
        examples=[
            "今日は学校に行きます。",
            "朝にコーヒーを飲みます。",
            "私は音楽を聞きます。",
            "電車で東京へ行きます。",
            "友達と映画を見ました。",
        ],
    )
    login(client, "practice-ja-device@t.com", PW)

    response = client.get("/practice")

    assert response.status_code == 200
    body = response.get_data(as_text=True)
    assert "Internal Server Error" not in body
    assert "5 道题" in body
    assert 'data-practice-voice-lang="ja"' in body
    started = client.post("/practice/start", data={"voice_available": "1"})
    assert started.status_code == 303
    assert "/practice/" in started.headers["Location"]
    question = client.get(started.headers["Location"])
    assert question.status_code == 200
    assert "ja-JP" in question.get_data(as_text=True)


def test_japanese_question_clozes_the_unique_substring(
    app, client, bypass_engine,
):
    user_id = provision_user(app, "practice-ja-cloze@t.com", PW)
    with bypass_engine.begin() as connection:
        connection.execute(text(
            "UPDATE users SET current_language='ja', learning_languages='ja' "
            "WHERE id=:user_id"
        ), {"user_id": user_id})
    _seed_examples(
        bypass_engine,
        user_id,
        language_code="ja",
        words=["学校"],
        examples=["今日は学校に行きます。"],
    )
    login(client, "practice-ja-cloze@t.com", PW)
    started = client.post("/practice/start", data={"voice_available": "1"})
    body = client.get(started.headers["Location"]).get_data(as_text=True)

    assert started.status_code == 303
    assert "今日は<span class=\"practice-blank\"" in body
    assert "に行きます。" in body
    assert 'data-practice-voice-lang="ja"' in body
    assert 'data-practice-voice-locale="ja-JP"' in body


def test_japanese_question_uses_japanese_html_lang(
    app, client, bypass_engine,
):
    user_id = provision_user(app, "practice-ja-lang@t.com", PW)
    with bypass_engine.begin() as connection:
        connection.execute(text(
            "UPDATE users SET current_language='ja', learning_languages='ja' "
            "WHERE id=:user_id"
        ), {"user_id": user_id})
    _seed_examples(
        bypass_engine,
        user_id,
        language_code="ja",
        words=["学校"],
        examples=["今日は学校に行きます。"],
    )
    login(client, "practice-ja-lang@t.com", PW)
    started = client.post("/practice/start", data={"voice_available": "1"})
    body = client.get(started.headers["Location"]).get_data(as_text=True)

    assert 'class="practice-prompt" lang="ja-JP"' in body
    assert 'name="answer" type="text" lang="ja-JP"' in body


def test_japanese_kana_reading_is_not_accepted_for_kanji_target(
    app, client, bypass_engine,
):
    user_id = provision_user(app, "practice-ja-reading@t.com", PW)
    with bypass_engine.begin() as connection:
        connection.execute(text(
            "UPDATE users SET current_language='ja', learning_languages='ja' "
            "WHERE id=:user_id"
        ), {"user_id": user_id})
    _seed_examples(
        bypass_engine,
        user_id,
        language_code="ja",
        words=["学校"],
        examples=["今日は学校に行きます。"],
    )
    login(client, "practice-ja-reading@t.com", PW)
    started = client.post("/practice/start", data={"voice_available": "1"})
    question = client.get(started.headers["Location"])
    answer_url = re.search(
        r'<form[^>]+action="(/practice/[^"]+/items/[^"]+/answer)"',
        question.get_data(as_text=True),
    ).group(1)

    response = client.post(answer_url, data={"answer": "がっこう"})

    assert response.status_code == 200
    assert "不正确" in response.get_data(as_text=True)


def test_japanese_halfwidth_katakana_answer_is_accepted(
    app, client, bypass_engine,
):
    user_id = provision_user(app, "practice-ja-halfwidth@t.com", PW)
    with bypass_engine.begin() as connection:
        connection.execute(text(
            "UPDATE users SET current_language='ja', learning_languages='ja' "
            "WHERE id=:user_id"
        ), {"user_id": user_id})
    _seed_examples(
        bypass_engine,
        user_id,
        language_code="ja",
        words=["コーヒー"],
        examples=["コーヒーを飲みます。"],
    )
    login(client, "practice-ja-halfwidth@t.com", PW)
    started = client.post("/practice/start", data={"voice_available": "1"})
    question = client.get(started.headers["Location"])
    answer_url = re.search(
        r'<form[^>]+action="(/practice/[^"]+/items/[^"]+/answer)"',
        question.get_data(as_text=True),
    ).group(1)

    response = client.post(answer_url, data={"answer": "ｺｰﾋｰ"})

    assert response.status_code == 200
    body = response.get_data(as_text=True)
    assert "正确" in body
    assert 'lang="ja-JP"' in body


def test_chinese_learner_sees_practice_start_with_eligible_count(
    app, client, bypass_engine,
):
    user_id = provision_user(app, "practice-zh-start@t.com", PW)
    with bypass_engine.begin() as connection:
        connection.execute(text(
            "UPDATE users SET current_language='zh', learning_languages='zh' "
            "WHERE id=:user_id"
        ), {"user_id": user_id})
    _seed_examples(
        bypass_engine,
        user_id,
        language_code="zh",
        words=["学校"],
        examples=["今天我去学校上课。"],
    )
    login(client, "practice-zh-start@t.com", PW)

    response = client.get("/practice")

    assert response.status_code == 200
    body = response.get_data(as_text=True)
    assert "1 道题" in body
    assert 'data-practice-screen="start"' in body
    assert "data-practice-start" in body
    assert "暂未开放" not in body
    assert 'data-practice-voice-lang="zh"' in body
    assert 'data-practice-voice-locale="zh-CN"' in body


def test_chinese_device_examples_open_start_and_session(
    app, client, bypass_engine,
):
    user_id = provision_user(app, "practice-zh-device@t.com", PW)
    with bypass_engine.begin() as connection:
        connection.execute(text(
            "UPDATE users SET current_language='zh', learning_languages='zh' "
            "WHERE id=:user_id"
        ), {"user_id": user_id})
    _seed_examples(
        bypass_engine,
        user_id,
        language_code="zh",
        words=["学校", "咖啡", "音乐", "火车", "朋友"],
        examples=[
            "今天我去学校上课。",
            "早上喝了一杯咖啡。",
            "她喜欢听音乐。",
            "我们坐火车去北京。",
            "我和朋友看电影。",
        ],
    )
    login(client, "practice-zh-device@t.com", PW)

    response = client.get("/practice")

    assert response.status_code == 200
    body = response.get_data(as_text=True)
    assert "Internal Server Error" not in body
    assert "5 道题" in body
    assert 'data-practice-voice-lang="zh"' in body
    started = client.post("/practice/start", data={"voice_available": "1"})
    assert started.status_code == 303
    assert "/practice/" in started.headers["Location"]
    question = client.get(started.headers["Location"])
    assert question.status_code == 200
    assert "zh-CN" in question.get_data(as_text=True)


def test_chinese_question_clozes_the_unique_substring(
    app, client, bypass_engine,
):
    user_id = provision_user(app, "practice-zh-cloze@t.com", PW)
    with bypass_engine.begin() as connection:
        connection.execute(text(
            "UPDATE users SET current_language='zh', learning_languages='zh' "
            "WHERE id=:user_id"
        ), {"user_id": user_id})
    _seed_examples(
        bypass_engine,
        user_id,
        language_code="zh",
        words=["学校"],
        examples=["今天我去学校上课。"],
    )
    login(client, "practice-zh-cloze@t.com", PW)
    started = client.post("/practice/start", data={"voice_available": "1"})
    body = client.get(started.headers["Location"]).get_data(as_text=True)

    assert started.status_code == 303
    assert "今天我去<span class=\"practice-blank\"" in body
    assert "上课。" in body
    assert 'data-practice-voice-lang="zh"' in body
    assert 'data-practice-voice-locale="zh-CN"' in body


def test_chinese_question_uses_chinese_html_lang(
    app, client, bypass_engine,
):
    user_id = provision_user(app, "practice-zh-lang@t.com", PW)
    with bypass_engine.begin() as connection:
        connection.execute(text(
            "UPDATE users SET current_language='zh', learning_languages='zh' "
            "WHERE id=:user_id"
        ), {"user_id": user_id})
    _seed_examples(
        bypass_engine,
        user_id,
        language_code="zh",
        words=["学校"],
        examples=["今天我去学校上课。"],
    )
    login(client, "practice-zh-lang@t.com", PW)
    started = client.post("/practice/start", data={"voice_available": "1"})
    body = client.get(started.headers["Location"]).get_data(as_text=True)

    assert 'class="practice-prompt" lang="zh-CN"' in body
    assert 'name="answer" type="text" lang="zh-CN"' in body


def test_chinese_pinyin_is_not_accepted_for_hanzi_target(
    app, client, bypass_engine,
):
    user_id = provision_user(app, "practice-zh-pinyin@t.com", PW)
    with bypass_engine.begin() as connection:
        connection.execute(text(
            "UPDATE users SET current_language='zh', learning_languages='zh' "
            "WHERE id=:user_id"
        ), {"user_id": user_id})
    _seed_examples(
        bypass_engine,
        user_id,
        language_code="zh",
        words=["学校"],
        examples=["今天我去学校上课。"],
    )
    login(client, "practice-zh-pinyin@t.com", PW)
    started = client.post("/practice/start", data={"voice_available": "1"})
    question = client.get(started.headers["Location"])
    answer_url = re.search(
        r'<form[^>]+action="(/practice/[^"]+/items/[^"]+/answer)"',
        question.get_data(as_text=True),
    ).group(1)

    response = client.post(answer_url, data={"answer": "xuexiao"})

    assert response.status_code == 200
    body = response.get_data(as_text=True)
    assert "不正确" in body
    assert 'lang="zh-CN"' in body


def test_chinese_fullwidth_digit_answer_is_accepted(
    app, client, bypass_engine,
):
    user_id = provision_user(app, "practice-zh-fullwidth@t.com", PW)
    with bypass_engine.begin() as connection:
        connection.execute(text(
            "UPDATE users SET current_language='zh', learning_languages='zh' "
            "WHERE id=:user_id"
        ), {"user_id": user_id})
    _seed_examples(
        bypass_engine,
        user_id,
        language_code="zh",
        words=["3号"],
        examples=["我们在3号门口见。"],
    )
    login(client, "practice-zh-fullwidth@t.com", PW)
    started = client.post("/practice/start", data={"voice_available": "1"})
    question = client.get(started.headers["Location"])
    answer_url = re.search(
        r'<form[^>]+action="(/practice/[^"]+/items/[^"]+/answer)"',
        question.get_data(as_text=True),
    ).group(1)

    response = client.post(answer_url, data={"answer": "３号"})

    assert response.status_code == 200
    body = response.get_data(as_text=True)
    assert "正确" in body
    assert 'lang="zh-CN"' in body


def test_chinese_session_completes_after_correct_answer(
    app, client, bypass_engine,
):
    user_id = provision_user(app, "practice-zh-complete@t.com", PW)
    with bypass_engine.begin() as connection:
        connection.execute(text(
            "UPDATE users SET current_language='zh', learning_languages='zh' "
            "WHERE id=:user_id"
        ), {"user_id": user_id})
    _seed_examples(
        bypass_engine,
        user_id,
        language_code="zh",
        words=["学校"],
        examples=["今天我去学校上课。"],
    )
    login(client, "practice-zh-complete@t.com", PW)
    started = client.post("/practice/start", data={"voice_available": "1"})
    session_url = started.headers["Location"]
    question = client.get(session_url)
    answer_url = re.search(
        r'<form[^>]+action="(/practice/[^"]+/items/[^"]+/answer)"',
        question.get_data(as_text=True),
    ).group(1)
    feedback = client.post(answer_url, data={"answer": "学校"})

    assert feedback.status_code == 200
    assert "正确" in feedback.get_data(as_text=True)
    completed = _post_continue(client, session_url)

    assert completed.status_code == 200
    body = completed.get_data(as_text=True)
    assert "练习完成" in body
    assert "1 / 1" in body


def test_start_creates_a_five_question_frozen_session(
    app, client, bypass_engine,
):
    user_id = provision_user(app, "practice-cap@t.com", PW)
    with bypass_engine.begin() as connection:
        connection.execute(text(
            "UPDATE users SET current_language='fr', learning_languages='fr' "
            "WHERE id=:user_id"
        ), {"user_id": user_id})
    _seed_examples(bypass_engine, user_id, 6)
    login(client, "practice-cap@t.com", PW)

    response = client.post("/practice/start", data={"voice_available": "1"})

    assert response.status_code == 303
    session_page = client.get(response.headers["Location"])
    assert session_page.status_code == 200
    body = session_page.get_data(as_text=True)
    assert "1 / 5" in body
    assert "Je connais" in body
    assert "practice-blank" in body


def test_start_refuses_without_explicit_voice_availability(
    app, client, bypass_engine,
):
    user_id = provision_user(app, "practice-voice-required@t.com", PW)
    with bypass_engine.begin() as connection:
        connection.execute(text(
            "UPDATE users SET current_language='fr', learning_languages='fr' "
            "WHERE id=:user_id"
        ), {"user_id": user_id})
    _seed_examples(
        bypass_engine,
        user_id,
        words=["bonjour"],
        examples=["Bonjour, madame."],
    )
    login(client, "practice-voice-required@t.com", PW)

    response = client.post("/practice/start", data={"voice_available": "0"})

    assert response.status_code == 409
    with bypass_engine.begin() as connection:
        assert connection.execute(text(
            "SELECT count(*) FROM practice_sessions WHERE user_id=:user_id"
        ), {"user_id": user_id}).scalar_one() == 0
        assert connection.execute(text(
            "SELECT count(*) FROM practice_items WHERE user_id=:user_id"
        ), {"user_id": user_id}).scalar_one() == 0


def test_voice_unavailable_report_is_idempotent_and_never_exposes_a_question(
    app, client, bypass_engine,
):
    user_id = provision_user(app, "practice-voice-blocked@t.com", PW)
    with bypass_engine.begin() as connection:
        connection.execute(text(
            "UPDATE users SET current_language='fr', learning_languages='fr' "
            "WHERE id=:user_id"
        ), {"user_id": user_id})
    _seed_examples(
        bypass_engine,
        user_id,
        words=["bonjour"],
        examples=["Bonjour, madame."],
    )
    login(client, "practice-voice-blocked@t.com", PW)
    app.config["WTF_CSRF_ENABLED"] = True

    assert client.post("/practice/voice-unavailable").status_code == 400
    start_page = client.get("/practice")
    assert start_page.status_code == 200
    csrf_token = re.search(
        r'name="csrf_token" value="([^"]+)"',
        start_page.get_data(as_text=True),
    ).group(1)
    first = client.post(
        "/practice/voice-unavailable",
        data={"csrf_token": csrf_token},
    )
    assert first.status_code == 200
    first_payload = first.get_json()
    assert first_payload["status"] == "blocked"
    assert client.get(first_payload["session_url"]).status_code == 404

    second = client.post(
        "/practice/voice-unavailable",
        data={"csrf_token": csrf_token},
    )
    assert second.status_code == 200
    assert second.get_json()["session_id"] == first_payload["session_id"]

    with bypass_engine.begin() as connection:
        assert connection.execute(text(
            "SELECT count(*) FROM practice_sessions "
            "WHERE user_id=:user_id AND status='blocked'"
        ), {"user_id": user_id}).scalar_one() == 1
        assert connection.execute(text(
            "SELECT count(*) FROM practice_items WHERE user_id=:user_id"
        ), {"user_id": user_id}).scalar_one() == 0


def test_recent_forgotten_words_are_prioritized_for_practice(
    app, client, bypass_engine,
):
    user_id = provision_user(app, "practice-priority@t.com", PW)
    with bypass_engine.begin() as connection:
        connection.execute(text(
            "UPDATE users SET current_language='fr', learning_languages='fr' "
            "WHERE id=:user_id"
        ), {"user_id": user_id})
    _seed_examples(
        bypass_engine,
        user_id,
        words=["facile", "difficile"],
        examples=["La maison est facile.", "Le voyage est difficile."],
    )
    with bypass_engine.begin() as connection:
        connection.execute(text(
            "INSERT INTO review_logs(word_id, user_id, ts, grade, source, interval_after) "
            "SELECT w.id, :user_id, now() - interval '1 day', 2, 'review', 1 "
            "FROM words w WHERE w.word='difficile'"
        ), {"user_id": user_id})
    login(client, "practice-priority@t.com", PW)

    response = client.post("/practice/start", data={"voice_available": "1"})
    body = client.get(response.headers["Location"]).get_data(as_text=True)

    assert "Le voyage" in body
    assert "La maison" not in body


def test_recent_weak_review_tie_break_uses_review_timestamp_before_lapses(
    app, client, bypass_engine,
):
    user_id = provision_user(app, "practice-weak-tie@t.com", PW)
    with bypass_engine.begin() as connection:
        connection.execute(text(
            "UPDATE users SET current_language='fr', learning_languages='fr' "
            "WHERE id=:user_id"
        ), {"user_id": user_id})
    _seed_examples(
        bypass_engine,
        user_id,
        words=["recent", "older"],
        examples=["Le mot recent est ici.", "Le mot older est ici."],
    )
    with bypass_engine.begin() as connection:
        connection.execute(text(
            "UPDATE words SET lapses=CASE word WHEN 'recent' THEN 0 ELSE 5 END "
            "WHERE word IN ('recent', 'older')"
        ))
        connection.execute(text(
            "INSERT INTO review_logs(word_id, user_id, ts, grade, source, interval_after) "
            "SELECT w.id, :user_id, CASE w.word "
            "WHEN 'recent' THEN now() - interval '1 hour' "
            "ELSE now() - interval '2 hours' END, 2, 'review', 1 "
            "FROM words w WHERE w.word IN ('recent', 'older')"
        ), {"user_id": user_id})
    login(client, "practice-weak-tie@t.com", PW)

    started = client.post("/practice/start", data={"voice_available": "1"})
    session_id = int(started.headers["Location"].rstrip("/").split("/")[-1])
    with bypass_engine.begin() as connection:
        first_word = connection.execute(text(
            "SELECT w.word FROM practice_items pi "
            "JOIN words w ON w.id=pi.word_id "
            "WHERE pi.session_id=:session_id AND pi.position=0"
        ), {"session_id": session_id}).scalar_one()

    assert first_word == "recent"


def test_future_unreviewed_zero_lapse_words_are_excluded_from_practice(
    app, client, bypass_engine,
):
    user_id = provision_user(app, "practice-future-excluded@t.com", PW)
    with bypass_engine.begin() as connection:
        connection.execute(text(
            "UPDATE users SET current_language='fr', learning_languages='fr' "
            "WHERE id=:user_id"
        ), {"user_id": user_id})
    _seed_examples(
        bypass_engine,
        user_id,
        words=["fragile", "avenir"],
        examples=["Cette tasse est fragile.", "Nous parlerons de l'avenir."],
    )
    with bypass_engine.begin() as connection:
        connection.execute(text(
            "UPDATE words SET due_date=now() + interval '7 days' "
            "WHERE word='avenir'"
        ))
        connection.execute(text(
            "INSERT INTO review_logs(word_id, user_id, ts, grade, source, interval_after) "
            "SELECT w.id, :user_id, now() - interval '1 day', 2, 'review', 1 "
            "FROM words w WHERE w.word='fragile'"
        ), {"user_id": user_id})
    login(client, "practice-future-excluded@t.com", PW)

    started = client.post("/practice/start", data={"voice_available": "1"})
    body = client.get(started.headers["Location"]).get_data(as_text=True)

    assert "Cette tasse est fragile." in body
    assert "Nous parlerons de l'avenir." not in body
    assert "1 / 1" in body


def test_submitting_an_answer_returns_server_feedback(
    app, client, bypass_engine,
):
    user_id = provision_user(app, "practice-answer@t.com", PW)
    with bypass_engine.begin() as connection:
        connection.execute(text(
            "UPDATE users SET current_language='fr', learning_languages='fr' "
            "WHERE id=:user_id"
        ), {"user_id": user_id})
    _seed_examples(
        bypass_engine,
        user_id,
        words=["voudrais"],
        examples=["Je voudrais un café."],
    )
    with bypass_engine.begin() as connection:
        connection.execute(text(
            "UPDATE definitions SET meaning='想要' "
            "WHERE word_id=(SELECT id FROM words WHERE word='voudrais')"
        ))
    login(client, "practice-answer@t.com", PW)

    started = client.post("/practice/start", data={"voice_available": "1"})
    question = client.get(started.headers["Location"])
    answer_url = re.search(
        r'<form[^>]+action="(/practice/[^"]+/items/[^"]+/answer)"',
        question.get_data(as_text=True),
    ).group(1)

    response = client.post(answer_url, data={"answer": "voudrais"})

    assert response.status_code == 200
    body = response.get_data(as_text=True)
    assert "正确" in body
    assert "voudrais" in body
    assert "Je voudrais un café." in body
    assert "想要" in body


def test_answer_normalization_ignores_case_and_surrounding_whitespace(
    app, client, bypass_engine,
):
    user_id = provision_user(app, "practice-normalize@t.com", PW)
    with bypass_engine.begin() as connection:
        connection.execute(text(
            "UPDATE users SET current_language='fr', learning_languages='fr' "
            "WHERE id=:user_id"
        ), {"user_id": user_id})
    _seed_examples(
        bypass_engine,
        user_id,
        words=["rendez-vous"],
        examples=["Nous avons un rendez-vous à midi."],
    )
    login(client, "practice-normalize@t.com", PW)

    started = client.post("/practice/start", data={"voice_available": "1"})
    question = client.get(started.headers["Location"])
    answer_url = re.search(
        r'<form[^>]+action="(/practice/[^"]+/items/[^"]+/answer)"',
        question.get_data(as_text=True),
    ).group(1)

    response = client.post(answer_url, data={"answer": "  RENDEZ-VOUS  "})

    assert response.status_code == 200
    assert '<p class="practice-verdict">正确</p>' in response.get_data(as_text=True)


def test_empty_answer_is_rejected_without_consuming_the_question(
    app, client, bypass_engine,
):
    user_id = provision_user(app, "practice-empty@t.com", PW)
    with bypass_engine.begin() as connection:
        connection.execute(text(
            "UPDATE users SET current_language='fr', learning_languages='fr' "
            "WHERE id=:user_id"
        ), {"user_id": user_id})
    _seed_examples(
        bypass_engine,
        user_id,
        words=["maison"],
        examples=["La maison est grande."],
    )
    login(client, "practice-empty@t.com", PW)

    started = client.post("/practice/start", data={"voice_available": "1"})
    session_url = started.headers["Location"]
    question = client.get(session_url)
    answer_url = re.search(
        r'<form[^>]+action="(/practice/[^"]+/items/[^"]+/answer)"',
        question.get_data(as_text=True),
    ).group(1)

    response = client.post(answer_url, data={"answer": "   "})

    assert response.status_code == 400
    assert '<form class="practice-form"' in client.get(session_url).get_data(as_text=True)


def test_replayed_submission_returns_the_first_frozen_outcome(
    app, client, bypass_engine,
):
    user_id = provision_user(app, "practice-idempotent@t.com", PW)
    with bypass_engine.begin() as connection:
        connection.execute(text(
            "UPDATE users SET current_language='fr', learning_languages='fr' "
            "WHERE id=:user_id"
        ), {"user_id": user_id})
    _seed_examples(
        bypass_engine,
        user_id,
        words=["hôtel"],
        examples=["Ils restent à l'hôtel ce soir."],
    )
    login(client, "practice-idempotent@t.com", PW)

    started = client.post("/practice/start", data={"voice_available": "1"})
    question = client.get(started.headers["Location"])
    answer_url = re.search(
        r'<form[^>]+action="(/practice/[^"]+/items/[^"]+/answer)"',
        question.get_data(as_text=True),
    ).group(1)

    first = client.post(answer_url, data={"answer": "hôtel"})
    replay = client.post(answer_url, data={"answer": "hotel"})

    assert first.status_code == replay.status_code == 200
    assert '<p class="practice-verdict">正确</p>' in replay.get_data(as_text=True)


def test_continue_after_final_feedback_renders_completion_summary(
    app, client, bypass_engine,
):
    user_id = provision_user(app, "practice-complete@t.com", PW)
    with bypass_engine.begin() as connection:
        connection.execute(text(
            "UPDATE users SET current_language='fr', learning_languages='fr' "
            "WHERE id=:user_id"
        ), {"user_id": user_id})
    _seed_examples(
        bypass_engine,
        user_id,
        words=["café"],
        examples=["Je bois un café."],
    )
    login(client, "practice-complete@t.com", PW)

    started = client.post("/practice/start", data={"voice_available": "1"})
    session_url = started.headers["Location"]
    question = client.get(session_url)
    answer_url = re.search(
        r'<form[^>]+action="(/practice/[^"]+/items/[^"]+/answer)"',
        question.get_data(as_text=True),
    ).group(1)
    feedback = client.post(answer_url, data={"answer": "café"})

    assert feedback.status_code == 200
    completed = _post_continue(client, session_url)

    assert completed.status_code == 200
    body = completed.get_data(as_text=True)
    assert "练习完成" in body
    assert "1 / 1" in body
    assert "再来一次" in body
    assert "返回首页" in body


def test_get_continue_redirects_to_session_without_advancing(
    app, client, bypass_engine,
):
    user_id = provision_user(app, "practice-get-continue@t.com", PW)
    with bypass_engine.begin() as connection:
        connection.execute(text(
            "UPDATE users SET current_language='fr', learning_languages='fr' "
            "WHERE id=:user_id"
        ), {"user_id": user_id})
    _seed_examples(
        bypass_engine,
        user_id,
        words=["un", "deux"],
        examples=["J'en ai un.", "J'en ai deux."],
    )
    login(client, "practice-get-continue@t.com", PW)
    started = client.post("/practice/start", data={"voice_available": "1"})
    session_url = started.headers["Location"]
    session_id = _session_id_from_url(session_url)
    question = client.get(session_url)
    answer_url = re.search(
        r'<form[^>]+action="(/practice/[^"]+/items/[^"]+/answer)"',
        question.get_data(as_text=True),
    ).group(1)
    client.post(answer_url, data={"answer": "un"})
    with bypass_engine.connect() as connection:
        before = connection.execute(text(
            "SELECT current_position, status FROM practice_sessions "
            "WHERE id=:session_id"
        ), {"session_id": session_id}).one()

    response = client.get(f"/practice/{session_id}/continue")

    assert response.status_code == 303
    assert response.headers["Location"].rstrip("/").endswith(
        f"/practice/{session_id}"
    )
    with bypass_engine.connect() as connection:
        after = connection.execute(text(
            "SELECT current_position, status FROM practice_sessions "
            "WHERE id=:session_id"
        ), {"session_id": session_id}).one()
    assert after.current_position == before.current_position == 0
    assert after.status == before.status == "active"


def test_post_continue_uses_prg_and_advances_once(
    app, client, bypass_engine,
):
    user_id = provision_user(app, "practice-prg-continue@t.com", PW)
    with bypass_engine.begin() as connection:
        connection.execute(text(
            "UPDATE users SET current_language='fr', learning_languages='fr' "
            "WHERE id=:user_id"
        ), {"user_id": user_id})
    _seed_examples(
        bypass_engine,
        user_id,
        words=["un", "deux"],
        examples=["J'en ai un.", "J'en ai deux."],
    )
    login(client, "practice-prg-continue@t.com", PW)
    started = client.post("/practice/start", data={"voice_available": "1"})
    session_url = started.headers["Location"]
    session_id = _session_id_from_url(session_url)
    first_question = client.get(session_url)
    first_answer_url = re.search(
        r'<form[^>]+action="(/practice/[^"]+/items/[^"]+/answer)"',
        first_question.get_data(as_text=True),
    ).group(1)
    client.post(first_answer_url, data={"answer": "un"})

    continued = client.post(session_url + "/continue")

    assert continued.status_code == 303
    assert continued.headers["Location"].rstrip("/").endswith(
        f"/practice/{session_id}"
    )
    assert "practice-blank" not in continued.get_data(as_text=True)
    with bypass_engine.connect() as connection:
        position = connection.execute(text(
            "SELECT current_position FROM practice_sessions WHERE id=:session_id"
        ), {"session_id": session_id}).scalar_one()
    assert position == 1
    next_question = client.get(continued.headers["Location"])
    next_body = next_question.get_data(as_text=True)
    assert next_question.status_code == 200
    assert "2 / 2" in next_body
    assert "practice-blank" in next_body
    assert "en ai" in next_body
    second_answer_url = re.search(
        r'<form[^>]+action="(/practice/[^"]+/items/[^"]+/answer)"',
        next_body,
    ).group(1)
    client.post(second_answer_url, data={"answer": "deux"})
    completed = client.post(session_url + "/continue")
    assert completed.status_code == 303
    complete_page = client.get(completed.headers["Location"])
    assert complete_page.status_code == 200
    assert "练习完成" in complete_page.get_data(as_text=True)


def test_english_feedback_continue_form_posts_to_continue(
    app, client, bypass_engine,
):
    user_id = provision_user(app, "practice-en-continue-form@t.com", PW)
    with bypass_engine.begin() as connection:
        connection.execute(text(
            "UPDATE users SET current_language='fr', learning_languages='fr' "
            "WHERE id=:user_id"
        ), {"user_id": user_id})
    _seed_examples(
        bypass_engine,
        user_id,
        words=["bonjour"],
        examples=["Bonjour, madame."],
    )
    login(client, "practice-en-continue-form@t.com", PW)
    client.post("/ui-language", data={"ui_locale": "en", "next": "/practice"})
    started = client.post("/practice/start", data={"voice_available": "1"})
    session_url = started.headers["Location"]
    session_id = _session_id_from_url(session_url)
    question = client.get(session_url)
    answer_url = re.search(
        r'<form[^>]+action="(/practice/[^"]+/items/[^"]+/answer)"',
        question.get_data(as_text=True),
    ).group(1)
    feedback = client.post(answer_url, data={"answer": "bonjour"}).get_data(as_text=True)
    form = re.search(
        r'<form[^>]+action="(/practice/[^"]+/continue)"[^>]*>',
        feedback,
    ).group(0)

    assert 'method="post"' in form
    assert f"/practice/{session_id}/continue" in form
    assert ">Continue</button>" in feedback


def test_authenticated_navigation_includes_practice_entry(app, client, bypass_engine):
    provision_user(app, "practice-nav@t.com", PW)
    login(client, "practice-nav@t.com", PW)

    page = client.get("/").get_data(as_text=True)

    assert 'href="/practice"' in page
    assert "练习" in page


def test_practice_navigation_is_localized_and_has_a_mobile_icon(
    app, client, bypass_engine,
):
    provision_user(app, "practice-nav-i18n@t.com", PW)
    login(client, "practice-nav-i18n@t.com", PW)

    client.post("/ui-language", data={"ui_locale": "en", "next": "/"})
    english = client.get("/").get_data(as_text=True)
    english_link = re.search(
        r'<a class="nav-link nav-primary[^>]+href="/practice".*?</a>',
        english,
        flags=re.DOTALL,
    ).group(0)
    assert 'title="Practice"' in english_link
    assert '<span class="nav-desktop-label">Practice</span>' in english_link
    assert '<svg class="nav-mobile-icon"' in english_link

    client.post("/ui-language", data={"ui_locale": "zh", "next": "/"})
    chinese = client.get("/").get_data(as_text=True)
    chinese_link = re.search(
        r'<a class="nav-link nav-primary[^>]+href="/practice".*?</a>',
        chinese,
        flags=re.DOTALL,
    ).group(0)
    assert 'title="练习"' in chinese_link
    assert '<span class="nav-desktop-label">练习</span>' in chinese_link
    assert '<svg class="nav-mobile-icon"' in chinese_link


def test_practice_templates_render_translated_copy(
    app, client, bypass_engine,
):
    user_id = provision_user(app, "practice-templates-i18n@t.com", PW)
    with bypass_engine.begin() as connection:
        connection.execute(text(
            "UPDATE users SET current_language='fr', learning_languages='fr' "
            "WHERE id=:user_id"
        ), {"user_id": user_id})
    _seed_examples(
        bypass_engine,
        user_id,
        words=["voudrais"],
        examples=["Je voudrais un café."],
    )
    login(client, "practice-templates-i18n@t.com", PW)
    client.post("/ui-language", data={"ui_locale": "zh", "next": "/practice"})

    start = client.get("/practice").get_data(as_text=True)
    assert "听音填词" in start
    assert "一次练习一个句子" in start
    assert ">开始</button>" in start

    started = client.post("/practice/start", data={"voice_available": "1"})
    session_url = started.headers["Location"]
    question = client.get(session_url).get_data(as_text=True)
    assert 'aria-label="播放"' in question
    assert "缺失的单词或短语" in question
    assert ">提交</button>" in question
    answer_url = re.search(
        r'<form[^>]+action="(/practice/[^\"]+/items/[^\"]+/answer)"',
        question,
    ).group(1)

    feedback = client.post(answer_url, data={"answer": "wrong"})
    feedback_body = feedback.get_data(as_text=True)
    assert "不正确" in feedback_body
    assert "你的答案" in feedback_body
    assert "完整句子" in feedback_body
    assert "释义" in feedback_body
    assert ">继续</button>" in feedback_body

    complete = _post_continue(client, session_url)
    complete_body = complete.get_data(as_text=True)
    assert "练习完成" in complete_body
    assert "错题" in complete_body
    assert "句子" in complete_body
    assert "再来一次" in complete_body
    assert "返回首页" in complete_body


def test_practice_surface_is_hidden_when_beta_gate_is_disabled(
    app, client, bypass_engine,
):
    app.config["PRACTICE_ENABLED"] = False
    provision_user(app, "practice-gate@t.com", PW)
    login(client, "practice-gate@t.com", PW)

    response = client.get("/practice")

    assert response.status_code == 404


def test_completion_summary_lists_missed_items_after_explicit_continuation(
    app, client, bypass_engine,
):
    user_id = provision_user(app, "practice-missed@t.com", PW)
    with bypass_engine.begin() as connection:
        connection.execute(text(
            "UPDATE users SET current_language='fr', learning_languages='fr' "
            "WHERE id=:user_id"
        ), {"user_id": user_id})
    _seed_examples(
        bypass_engine,
        user_id,
        words=["maison", "voyage"],
        examples=["La maison est grande.", "Le voyage est long."],
    )
    login(client, "practice-missed@t.com", PW)

    started = client.post("/practice/start", data={"voice_available": "1"})
    session_url = started.headers["Location"]
    first_question = client.get(session_url)
    first_answer_url = re.search(
        r'<form[^>]+action="(/practice/[^"]+/items/[^"]+/answer)"',
        first_question.get_data(as_text=True),
    ).group(1)
    client.post(first_answer_url, data={"answer": "mauvais"})
    second_question = _post_continue(client, session_url)
    second_answer_url = re.search(
        r'<form[^>]+action="(/practice/[^"]+/items/[^"]+/answer)"',
        second_question.get_data(as_text=True),
    ).group(1)
    client.post(second_answer_url, data={"answer": "voyage"})

    completed = _post_continue(client, session_url)

    assert completed.status_code == 200
    body = completed.get_data(as_text=True)
    assert "错题" in body
    assert "mauvais" in body
    assert "maison" in body
    assert "La maison est grande." in body


def test_practice_start_loads_focused_card_voice_controls(
    app, client, bypass_engine,
):
    user_id = provision_user(app, "practice-voice@t.com", PW)
    with bypass_engine.begin() as connection:
        connection.execute(text(
            "UPDATE users SET current_language='fr', learning_languages='fr' "
            "WHERE id=:user_id"
        ), {"user_id": user_id})
    _seed_examples(
        bypass_engine,
        user_id,
        words=["bonjour"],
        examples=["Bonjour, madame."],
    )
    login(client, "practice-voice@t.com", PW)

    body = client.get("/practice").get_data(as_text=True)

    assert "/static/practice.css" in body
    assert "/static/practice.js" in body
    assert "data-practice-start" in body
    assert "data-practice-voice-status" in body
    assert "data-practice-retry" in body
    assert "/practice/voice-unavailable" in body


def test_session_start_records_voice_availability_observation(
    app, client, bypass_engine,
):
    user_id = provision_user(app, "practice-voice-observation@t.com", PW)
    with bypass_engine.begin() as connection:
        connection.execute(text(
            "UPDATE users SET current_language='fr', learning_languages='fr' "
            "WHERE id=:user_id"
        ), {"user_id": user_id})
    _seed_examples(
        bypass_engine,
        user_id,
        words=["salut"],
        examples=["Salut, mon ami."],
    )
    login(client, "practice-voice-observation@t.com", PW)

    response = client.post("/practice/start", data={"voice_available": "1"})
    session_id = int(response.headers["Location"].rstrip("/").split("/")[-1])

    with bypass_engine.connect() as connection:
        observed = connection.execute(text(
            "SELECT voice_available FROM practice_sessions WHERE id=:session_id"
        ), {"session_id": session_id}).scalar_one()
    assert observed is True


def test_sentence_replay_increments_item_replay_count(
    app, client, bypass_engine,
):
    user_id = provision_user(app, "practice-replay@t.com", PW)
    with bypass_engine.begin() as connection:
        connection.execute(text(
            "UPDATE users SET current_language='fr', learning_languages='fr' "
            "WHERE id=:user_id"
        ), {"user_id": user_id})
    _seed_examples(
        bypass_engine,
        user_id,
        words=["écouter"],
        examples=["J'aime écouter la radio."],
    )
    login(client, "practice-replay@t.com", PW)

    started = client.post("/practice/start", data={"voice_available": "1"})
    question = client.get(started.headers["Location"])
    answer_url = re.search(
        r'<form[^>]+action="(/practice/[^"]+/items/[^"]+/answer)"',
        question.get_data(as_text=True),
    ).group(1)
    replay_url = answer_url.rsplit("/answer", 1)[0] + "/replay"

    response = client.post(replay_url)

    assert response.status_code == 204
    item_id = int(answer_url.split("/items/")[1].split("/")[0])
    with bypass_engine.connect() as connection:
        count = connection.execute(text(
            "SELECT replay_count FROM practice_items WHERE id=:item_id"
        ), {"item_id": item_id}).scalar_one()
    assert count == 1


def test_answer_duration_is_recorded_as_bounded_client_observation(
    app, client, bypass_engine,
):
    user_id = provision_user(app, "practice-duration@t.com", PW)
    with bypass_engine.begin() as connection:
        connection.execute(text(
            "UPDATE users SET current_language='fr', learning_languages='fr' "
            "WHERE id=:user_id"
        ), {"user_id": user_id})
    _seed_examples(
        bypass_engine,
        user_id,
        words=["attendre"],
        examples=["Je vais attendre ici."],
    )
    login(client, "practice-duration@t.com", PW)

    started = client.post("/practice/start", data={"voice_available": "1"})
    question = client.get(started.headers["Location"])
    answer_url = re.search(
        r'<form[^>]+action="(/practice/[^"]+/items/[^"]+/answer)"',
        question.get_data(as_text=True),
    ).group(1)
    client.post(answer_url, data={"answer": "attendre", "answer_duration_ms": "1234"})
    item_id = int(answer_url.split("/items/")[1].split("/")[0])

    with bypass_engine.connect() as connection:
        duration = connection.execute(text(
            "SELECT answer_duration_ms FROM practice_items WHERE id=:item_id"
        ), {"item_id": item_id}).scalar_one()
    assert duration == 1234


def test_practice_answer_has_no_srs_or_review_log_side_effects(
    app, client, bypass_engine,
):
    user_id = provision_user(app, "practice-no-srs@t.com", PW)
    with bypass_engine.begin() as connection:
        connection.execute(text(
            "UPDATE users SET current_language='fr', learning_languages='fr' "
            "WHERE id=:user_id"
        ), {"user_id": user_id})
    _seed_examples(
        bypass_engine,
        user_id,
        words=["réussir"],
        examples=["Je veux réussir cet examen."],
    )
    with bypass_engine.connect() as connection:
        before = connection.execute(text(
            "SELECT w.reps, w.lapses, w.interval, w.ease, w.due_date "
            "FROM words w WHERE w.word='réussir'"
        )).one()
        logs_before = connection.execute(text(
            "SELECT count(*) FROM review_logs WHERE user_id=:user_id"
        ), {"user_id": user_id}).scalar_one()
    login(client, "practice-no-srs@t.com", PW)

    started = client.post("/practice/start", data={"voice_available": "1"})
    question = client.get(started.headers["Location"])
    answer_url = re.search(
        r'<form[^>]+action="(/practice/[^"]+/items/[^"]+/answer)"',
        question.get_data(as_text=True),
    ).group(1)
    client.post(answer_url, data={"answer": "mauvais"})

    with bypass_engine.connect() as connection:
        after = connection.execute(text(
            "SELECT w.reps, w.lapses, w.interval, w.ease, w.due_date "
            "FROM words w WHERE w.word='réussir'"
        )).one()
        logs_after = connection.execute(text(
            "SELECT count(*) FROM review_logs WHERE user_id=:user_id"
        ), {"user_id": user_id}).scalar_one()

    assert after == before
    assert logs_after == logs_before


def test_other_authenticated_user_cannot_open_another_users_session(
    app, client, bypass_engine,
):
    owner_id = provision_user(app, "practice-http-owner@t.com", PW)
    attacker_id = provision_user(app, "practice-http-attacker@t.com", PW)
    with bypass_engine.begin() as connection:
        connection.execute(text(
            "UPDATE users SET current_language='fr', learning_languages='fr' "
            "WHERE id IN (:owner_id, :attacker_id)"
        ), {"owner_id": owner_id, "attacker_id": attacker_id})
    _seed_examples(
        bypass_engine,
        owner_id,
        words=["privé"],
        examples=["C'est un exemple privé."],
    )
    login(client, "practice-http-owner@t.com", PW)
    started = client.post("/practice/start", data={"voice_available": "1"})
    session_url = started.headers["Location"]

    attacker_client = app.test_client()
    login(attacker_client, "practice-http-attacker@t.com", PW)

    response = attacker_client.get(session_url)

    assert response.status_code == 404


def test_abandonment_records_active_session_position(
    app, client, bypass_engine,
):
    user_id = provision_user(app, "practice-abandon@t.com", PW)
    with bypass_engine.begin() as connection:
        connection.execute(text(
            "UPDATE users SET current_language='fr', learning_languages='fr' "
            "WHERE id=:user_id"
        ), {"user_id": user_id})
    _seed_examples(
        bypass_engine,
        user_id,
        words=["un", "deux"],
        examples=["J'en ai un.", "J'en ai deux."],
    )
    login(client, "practice-abandon@t.com", PW)

    started = client.post("/practice/start", data={"voice_available": "1"})
    session_url = started.headers["Location"]
    response = client.post(session_url + "/abandon")

    assert response.status_code == 204
    session_id = int(session_url.rstrip("/").split("/")[-1])
    with bypass_engine.connect() as connection:
        state = connection.execute(text(
            "SELECT status, current_position, abandoned_at "
            "FROM practice_sessions WHERE id=:session_id"
        ), {"session_id": session_id}).one()
    assert state.status == "abandoned"
    assert state.current_position == 0
    assert state.abandoned_at is not None


def test_feedback_keeps_a_deliberate_full_sentence_replay_control(
    app, client, bypass_engine,
):
    user_id = provision_user(app, "practice-feedback-replay@t.com", PW)
    with bypass_engine.begin() as connection:
        connection.execute(text(
            "UPDATE users SET current_language='fr', learning_languages='fr' "
            "WHERE id=:user_id"
        ), {"user_id": user_id})
    _seed_examples(
        bypass_engine,
        user_id,
        words=["soir"],
        examples=["Nous sortons ce soir."],
    )
    login(client, "practice-feedback-replay@t.com", PW)

    started = client.post("/practice/start", data={"voice_available": "1"})
    question = client.get(started.headers["Location"])
    answer_url = re.search(
        r'<form[^>]+action="(/practice/[^"]+/items/[^"]+/answer)"',
        question.get_data(as_text=True),
    ).group(1)
    feedback = client.post(answer_url, data={"answer": "soir"})

    body = feedback.get_data(as_text=True)
    assert 'data-practice-play' in body
    assert 'data-practice-sentence="Nous sortons ce soir."' in body


def test_question_input_marks_answer_required_for_keyboard_and_touch(
    app, client, bypass_engine,
):
    user_id = provision_user(app, "practice-required@t.com", PW)
    with bypass_engine.begin() as connection:
        connection.execute(text(
            "UPDATE users SET current_language='fr', learning_languages='fr' "
            "WHERE id=:user_id"
        ), {"user_id": user_id})
    _seed_examples(
        bypass_engine,
        user_id,
        words=["écrire"],
        examples=["J'aime écrire en français."],
    )
    login(client, "practice-required@t.com", PW)

    started = client.post("/practice/start", data={"voice_available": "1"})
    body = client.get(started.headers["Location"]).get_data(as_text=True)

    assert 'name="answer"' in body
    assert 'name="answer"' in body and "required" in body


def test_start_page_reports_the_capped_session_question_count(
    app, client, bypass_engine,
):
    user_id = provision_user(app, "practice-count-cap@t.com", PW)
    with bypass_engine.begin() as connection:
        connection.execute(text(
            "UPDATE users SET current_language='fr', learning_languages='fr' "
            "WHERE id=:user_id"
        ), {"user_id": user_id})
    _seed_examples(bypass_engine, user_id, 6)
    login(client, "practice-count-cap@t.com", PW)

    body = client.get("/practice").get_data(as_text=True)

    assert "5 道题" in body
    assert "6 道题" not in body


def test_future_session_item_cannot_be_submitted_before_continue(
    app, client, bypass_engine,
):
    user_id = provision_user(app, "practice-order@t.com", PW)
    with bypass_engine.begin() as connection:
        connection.execute(text(
            "UPDATE users SET current_language='fr', learning_languages='fr' "
            "WHERE id=:user_id"
        ), {"user_id": user_id})
    _seed_examples(
        bypass_engine,
        user_id,
        words=["premier", "second"],
        examples=["Voici le premier exemple.", "Voici le second exemple."],
    )
    login(client, "practice-order@t.com", PW)

    started = client.post("/practice/start", data={"voice_available": "1"})
    session_url = started.headers["Location"]
    session_id = int(session_url.rstrip("/").split("/")[-1])
    with bypass_engine.connect() as connection:
        second_item_id = connection.execute(text(
            "SELECT id FROM practice_items "
            "WHERE session_id=:session_id AND position=1"
        ), {"session_id": session_id}).scalar_one()

    response = client.post(
        f"/practice/{session_id}/items/{second_item_id}/answer",
        data={"answer": "second"},
    )

    assert response.status_code == 409


def test_refreshing_completed_session_keeps_completion_summary(
    app, client, bypass_engine,
):
    user_id = provision_user(app, "practice-completed-refresh@t.com", PW)
    with bypass_engine.begin() as connection:
        connection.execute(text(
            "UPDATE users SET current_language='fr', learning_languages='fr' "
            "WHERE id=:user_id"
        ), {"user_id": user_id})
    _seed_examples(
        bypass_engine,
        user_id,
        words=["finir"],
        examples=["Je vais finir ce travail."],
    )
    login(client, "practice-completed-refresh@t.com", PW)

    started = client.post("/practice/start", data={"voice_available": "1"})
    session_url = started.headers["Location"]
    question = client.get(session_url)
    answer_url = re.search(
        r'<form[^>]+action="(/practice/[^"]+/items/[^"]+/answer)"',
        question.get_data(as_text=True),
    ).group(1)
    client.post(answer_url, data={"answer": "finir"})
    _post_continue(client, session_url)

    refreshed = client.get(session_url)

    assert refreshed.status_code == 200
    assert "练习完成" in refreshed.get_data(as_text=True)


def test_ui_language_switch_from_chinese_question_does_not_404(
    app, client, bypass_engine,
):
    user_id, session_url = _start_zh_practice(
        app, client, bypass_engine, "practice-zh-ui-question@t.com",
    )
    session_id = _session_id_from_url(session_url)
    question = client.get(session_url)
    assert question.status_code == 200
    locale, nxt = _ui_switch_fields(question.get_data(as_text=True))
    assert locale == "en"
    assert nxt == f"/practice/{session_id}"

    switched = client.post("/ui-language", data={"ui_locale": locale, "next": nxt})
    landed = _follow_redirect(client, switched)

    assert landed.status_code == 200
    assert b"Not Found" not in landed.data
    body = landed.get_data(as_text=True)
    assert '<html lang="en">' in body
    with bypass_engine.connect() as connection:
        state = connection.execute(text(
            "SELECT status, language_code FROM practice_sessions WHERE id=:id"
        ), {"id": session_id}).one()
        ui_locale = connection.execute(text(
            "SELECT ui_locale FROM user_settings WHERE user_id=:uid"
        ), {"uid": user_id}).scalar()
    assert tuple(state) == ("active", "zh")
    assert ui_locale == "en"


def test_ui_language_switch_from_feedback_does_not_404(
    app, client, bypass_engine,
):
    _, session_url = _start_zh_practice(
        app, client, bypass_engine, "practice-zh-ui-feedback@t.com",
    )
    question = client.get(session_url)
    answer_url = re.search(
        r'<form[^>]+action="(/practice/[^"]+/items/[^"]+/answer)"',
        question.get_data(as_text=True),
    ).group(1)
    feedback = client.post(answer_url, data={"answer": "学校"})
    assert feedback.status_code == 200
    locale, nxt = _ui_switch_fields(feedback.get_data(as_text=True))
    assert locale == "en"
    assert nxt == answer_url

    switched = client.post("/ui-language", data={"ui_locale": locale, "next": nxt})
    landed = _follow_redirect(client, switched)

    assert landed.status_code == 200
    assert b"Not Found" not in landed.data
    assert landed.status_code != 405
    body = landed.get_data(as_text=True)
    assert '<html lang="en">' in body
    assert 'data-practice-screen="feedback"' in body


def test_ui_language_switch_from_complete_does_not_404(
    app, client, bypass_engine,
):
    _, session_url = _start_zh_practice(
        app, client, bypass_engine, "practice-zh-ui-complete@t.com",
    )
    question = client.get(session_url)
    answer_url = re.search(
        r'<form[^>]+action="(/practice/[^"]+/items/[^"]+/answer)"',
        question.get_data(as_text=True),
    ).group(1)
    client.post(answer_url, data={"answer": "学校"})
    complete = _post_continue(client, session_url)
    assert complete.status_code == 200
    locale, nxt = _ui_switch_fields(complete.get_data(as_text=True))
    assert locale == "en"
    assert nxt == session_url or nxt.rstrip("/") == session_url.rstrip("/")

    switched = client.post("/ui-language", data={"ui_locale": locale, "next": nxt})
    landed = _follow_redirect(client, switched)

    assert landed.status_code == 200
    assert b"Not Found" not in landed.data
    assert "Session complete" in landed.get_data(as_text=True)


def test_learning_language_switch_to_en_keeps_frozen_zh_session(
    app, client, bypass_engine,
):
    user_id, session_url = _start_zh_practice(
        app, client, bypass_engine, "practice-zh-learn-en@t.com",
        learning="zh,en",
    )
    session_id = _session_id_from_url(session_url)
    question = client.get(session_url)
    assert question.status_code == 200

    switched = client.post(
        "/language/switch",
        data={"language_code": "en", "next": question.request.path},
    )
    landed = _follow_redirect(client, switched)

    assert landed.status_code == 200
    assert b"Not Found" not in landed.data
    with bypass_engine.connect() as connection:
        state = connection.execute(text(
            "SELECT status, language_code FROM practice_sessions WHERE id=:id"
        ), {"id": session_id}).one()
        current = connection.execute(text(
            "SELECT current_language FROM users WHERE id=:uid"
        ), {"uid": user_id}).scalar()
    assert tuple(state) == ("active", "zh")
    assert current == "en"
    original = client.get(session_url)
    assert original.status_code == 200
    start = client.get("/practice")
    assert start.status_code == 200
    assert "暂未开放" in start.get_data(as_text=True)
