"""造句闭环：不自动保存 / 显式保存 / 刷新不重存 / 额度 / 隔离 / NSFW 发布拦截。"""
import re

import pytest
from sqlalchemy import text

from tests.helpers import provision_user, login

PW = "pw12345678"


def _setup_user_with_word(app, client, bypass_engine, email="w@t.com"):
    provision_user(app, email, PW)
    login(client, email, PW)
    client.post("/words/add", json={"language_code": "fr", "word": "décollage",
                                    "definitions": [{"meaning": "起飞"}]})
    with bypass_engine.connect() as c:
        wid = c.execute(text("SELECT id FROM words WHERE word='décollage'")).scalar()
        uid = c.execute(text("SELECT id FROM users WHERE email=:e"), {"e": email}).scalar()
    return uid, wid


def _count_entries(bypass_engine, uid):
    with bypass_engine.connect() as c:
        return c.execute(text("SELECT count(*) FROM output_entries WHERE user_id=:u"),
                         {"u": uid}).scalar()


def _switch_lang(client, code):
    csrf = re.search(r'name="csrf_token"[^>]*value="([^"]+)"',
                     client.get("/").get_data(as_text=True)).group(1)
    client.post("/language/switch", data={"language_code": code, "csrf_token": csrf})


def _switch_ui_to_english(client, next_path="/write"):
    client.post("/ui-language", data={"ui_locale": "en", "next": next_path})


def test_write_workflow_renders_server_side_english(
    app, client, bypass_engine, fake_llm,
):
    _, wid = _setup_user_with_word(app, client, bypass_engine, "write-en@t.com")
    _switch_ui_to_english(client)

    page = client.get("/write").get_data(as_text=True)
    assert '<html lang="en">' in page
    assert "Write one sentence today" in page
    assert "Recommended word" in page
    assert "Target word" in page
    assert "Check sentence" in page
    assert "今天写一句" not in page

    result = client.post("/write/submit", data={
        "word_id": wid,
        "sentence": "Un essai.",
    }).get_data(as_text=True)
    assert "Correction:" in result
    assert "Translation:" in result
    assert "Feedback:" in result
    assert ">Save</button>" in result
    assert ">Rewrite</button>" in result

    saved = client.post("/write/save").get_data(as_text=True)
    assert "Saved to writing history" in saved
    assert "Publish to Square" in saved
    assert "Write another" in saved


def test_write_english_htmx_error_fragments(
    app, client, bypass_engine, fake_llm,
):
    _, wid = _setup_user_with_word(app, client, bypass_engine, "write-errors-en@t.com")
    _switch_ui_to_english(client)

    malformed_diary = client.post("/write/submit", data={
        "mode": "diary",
        "prompt": "What made you smile?",
        "diary": "Only one line",
    }).get_data(as_text=True)
    assert "must contain exactly 3 lines" in malformed_diary
    assert "Rewrite" in malformed_diary

    fake_llm["empty"] = True
    fake_llm["reinstall"]()
    degraded = client.post("/write/submit", data={
        "word_id": wid,
        "sentence": "Un essai.",
    }).get_data(as_text=True)
    assert "AI feedback is temporarily unavailable" in degraded
    assert ">Save</button>" not in degraded


def test_writing_history_renders_english_statuses(
    app, client, bypass_engine, fake_llm,
):
    _, wid = _setup_user_with_word(app, client, bypass_engine, "history-en@t.com")
    client.post("/write/submit", data={"word_id": wid, "sentence": "Un essai."})
    client.post("/write/save")
    _switch_ui_to_english(client, "/write/history")

    page = client.get("/write/history").get_data(as_text=True)
    assert "Writing history" in page
    assert 'aria-label="Writing timeline"' in page
    assert "Correction:" in page
    assert "Publish to Square" in page
    assert "造句历史" not in page


def test_submit_does_not_persist(app, client, bypass_engine, fake_llm):
    """核心：批改(submit)绝不入库——根治 MemoBuddy「自动保存」。"""
    uid, wid = _setup_user_with_word(app, client, bypass_engine)
    resp = client.post("/write/submit", data={"word_id": wid, "sentence": "Un essai."})
    assert resp.status_code == 200
    assert "修正" in resp.get_data(as_text=True)
    assert _count_entries(bypass_engine, uid) == 0      # 没入库


def test_save_persists_then_cleared(app, client, bypass_engine, fake_llm):
    uid, wid = _setup_user_with_word(app, client, bypass_engine)
    client.post("/write/submit", data={"word_id": wid, "sentence": "Un essai."})
    resp = client.post("/write/save")
    assert resp.status_code == 200
    assert _count_entries(bypass_engine, uid) == 1      # 显式保存后入库

    # 再次 save（无 pending）→ 过期提示，不重复入库（刷新/重放安全）
    resp2 = client.post("/write/save")
    assert "过期" in resp2.get_data(as_text=True)
    assert _count_entries(bypass_engine, uid) == 1


def test_history_renders_timeline_navigation(app, client, bypass_engine, fake_llm):
    uid, wid = _setup_user_with_word(app, client, bypass_engine)
    client.post("/write/submit", data={"word_id": wid, "sentence": "Un essai."})
    client.post("/write/save")
    with bypass_engine.connect() as c:
        eid = c.execute(text(
            "SELECT id FROM output_entries WHERE user_id=:u"),
            {"u": uid}).scalar()

    page = client.get("/write/history").get_data(as_text=True)

    assert 'aria-label="造句时间轴"' in page
    assert 'class="timeline-select"' in page
    assert f'href="#entry-{eid}"' in page
    assert f'value="entry-{eid}"' in page
    assert f'id="entry-{eid}"' in page
    assert 'class="timeline-body"' in page
    assert "décollage" in page
    assert "phrase corrigée" in page


def test_history_can_publish_saved_non_nsfw_entry(app, client, bypass_engine, fake_llm):
    uid, wid = _setup_user_with_word(app, client, bypass_engine)
    client.post("/write/submit", data={"word_id": wid, "sentence": "Un essai."})
    client.post("/write/save")
    with bypass_engine.connect() as c:
        eid = c.execute(text("SELECT id FROM output_entries WHERE user_id=:u"),
                        {"u": uid}).scalar()

    page = client.get("/write/history").get_data(as_text=True)
    assert "公开到广场" in page
    resp = client.post(f"/write/{eid}/publish", follow_redirects=True)
    assert resp.status_code == 200
    page2 = resp.get_data(as_text=True)
    assert "已公开" in page2
    assert "去广场看看" in page2
    with bypass_engine.connect() as c:
        is_public = c.execute(text(
            "SELECT is_public FROM output_entries WHERE id=:e"),
            {"e": eid}).scalar()
    assert is_public is True


def test_owner_can_unpublish_entry_from_history(app, client, bypass_engine, fake_llm):
    uid, wid = _setup_user_with_word(app, client, bypass_engine)
    client.post("/write/submit", data={"word_id": wid, "sentence": "Un essai."})
    client.post("/write/save")
    with bypass_engine.connect() as c:
        eid = c.execute(text("SELECT id FROM output_entries WHERE user_id=:u"),
                        {"u": uid}).scalar()

    client.post(f"/write/{eid}/publish")
    assert "phrase corrigée" in client.get("/square?lang=fr").get_data(as_text=True)

    resp = client.post(f"/write/{eid}/unpublish", follow_redirects=True)
    page = resp.get_data(as_text=True)
    assert resp.status_code == 200
    assert "已取消公开" in page
    assert "公开到广场" in page
    assert f'action="/write/{eid}/unpublish"' not in page
    with bypass_engine.connect() as c:
        is_public = c.execute(text(
            "SELECT is_public FROM output_entries WHERE id=:e"),
            {"e": eid}).scalar()
    assert is_public is False
    assert "phrase corrigée" not in client.get("/square?lang=fr").get_data(as_text=True)


def test_history_hides_publish_for_nsfw_entry(app, client, bypass_engine, fake_llm):
    uid, wid = _setup_user_with_word(app, client, bypass_engine)
    fake_llm["nsfw_content"] = '{"is_nsfw":true}'
    fake_llm["reinstall"]()
    client.post("/write/submit", data={"word_id": wid, "sentence": "x"})
    client.post("/write/save")

    page = client.get("/write/history").get_data(as_text=True)
    assert "公开到广场" not in page
    assert "不可公开" in page


def test_degraded_correction_cannot_be_saved(app, client, bypass_engine, fake_llm):
    uid, wid = _setup_user_with_word(app, client, bypass_engine)
    fake_llm["empty"] = True
    fake_llm["reinstall"]()

    resp = client.post("/write/submit", data={"word_id": wid, "sentence": "Un essai."})
    page = resp.get_data(as_text=True)
    assert resp.status_code == 200
    assert "AI 批改暂时不可用" in page
    assert "保存" not in page
    assert "过期" in client.post("/write/save").get_data(as_text=True)
    assert _count_entries(bypass_engine, uid) == 0


def test_moderation_outage_keeps_correction_saveable_but_private(
        app, client, bypass_engine, fake_llm):
    uid, wid = _setup_user_with_word(app, client, bypass_engine)
    fake_llm["nsfw_empty"] = True
    fake_llm["reinstall"]()

    result = client.post(
        "/write/submit", data={"word_id": wid, "sentence": "Un essai."},
    ).get_data(as_text=True)
    assert "phrase corrigée" in result
    assert "保存" in result

    client.post("/write/save")
    with bypass_engine.connect() as conn:
        entry = conn.execute(text("""
            SELECT id, is_nsfw FROM output_entries WHERE user_id = :user_id
        """), {"user_id": uid}).one()
        corrections = conn.execute(text("""
            SELECT corrections_today FROM user_quota WHERE user_id = :user_id
        """), {"user_id": uid}).scalar()
    assert entry.is_nsfw is True
    assert corrections == 1
    assert client.post(f"/write/{entry.id}/publish").status_code == 400


def test_moderation_usage_is_separate_from_correction_allowance(
        app, client, bypass_engine, fake_llm):
    uid, wid = _setup_user_with_word(app, client, bypass_engine)

    client.post(
        "/write/submit", data={"word_id": wid, "sentence": "Un essai."},
    )

    with bypass_engine.connect() as conn:
        corrections = conn.execute(text("""
            SELECT corrections_today FROM user_quota WHERE user_id = :user_id
        """), {"user_id": uid}).scalar()
        features = conn.execute(text("""
            SELECT feature FROM token_usage_log
            WHERE user_id = :user_id ORDER BY id
        """), {"user_id": uid}).scalars().all()
    assert corrections == 1
    assert sorted(features) == ["correction", "nsfw"]


def test_discard_drops_pending(app, client, bypass_engine, fake_llm):
    uid, wid = _setup_user_with_word(app, client, bypass_engine)
    client.post("/write/submit", data={"word_id": wid, "sentence": "Un essai."})
    client.post("/write/discard")
    assert client.post("/write/save").get_data(as_text=True).find("过期") >= 0
    assert _count_entries(bypass_engine, uid) == 0


def test_daily_quota_system_key_3(app, client, bypass_engine, fake_llm):
    uid, wid = _setup_user_with_word(app, client, bypass_engine)
    for _ in range(3):
        r = client.post("/write/submit", data={"word_id": wid, "sentence": "Un essai."})
        assert "额度" not in r.get_data(as_text=True)
    # 第 4 句被额度拦
    r4 = client.post("/write/submit", data={"word_id": wid, "sentence": "Un essai."})
    assert "额度" in r4.get_data(as_text=True)


def test_compose_requires_current_language(app, client, bypass_engine, fake_llm):
    provision_user(app, "nolanguage@t.com", PW)
    login(client, "nolanguage@t.com", PW)

    page = client.get("/write").get_data(as_text=True)
    assert "先选一个正在学的语言" in page
    assert client.post("/write/submit", data={
        "word_id": 1, "sentence": "x",
    }).status_code == 400


def test_diary_mode_available_without_words(app, client, bypass_engine, fake_llm):
    provision_user(app, "diaryempty@t.com", PW)
    login(client, "diaryempty@t.com", PW)
    _switch_lang(client, "fr")

    page = client.get("/write?mode=diary").get_data(as_text=True)

    assert "三行日记" in page
    assert "提示问题" in page
    assert "还没有词" not in page


@pytest.mark.parametrize(
    ("learning_language", "feedback_language", "prompt"),
    [
        ("zh", "fr", "French feedback prompt"),
        ("ja", "zh", "Chinese feedback prompt"),
    ],
)
def test_diary_prompt_uses_feedback_language(
    app, client, bypass_engine, fake_llm, monkeypatch,
    learning_language, feedback_language, prompt,
):
    email = f"diary-feedback-{learning_language}-{feedback_language}@t.com"
    provision_user(app, email, PW)
    login(client, email, PW)
    client.post("/settings", data={
        "languages": [learning_language],
        "feedback_language": feedback_language,
    })

    received_language = []

    def fake_diary_prompt(language_code):
        received_language.append(language_code)
        return prompt

    monkeypatch.setattr(
        "app.blueprints.write.routes.writing_svc.random_diary_prompt",
        fake_diary_prompt,
    )

    page = client.get("/write?mode=diary").get_data(as_text=True)

    assert received_language == [feedback_language]
    assert prompt in page


def test_diary_submit_save_publish_to_square(app, client, bypass_engine, fake_llm):
    provision_user(app, "diary@t.com", PW)
    login(client, "diary@t.com", PW)
    _switch_lang(client, "fr")
    fake_llm["content"] = (
        '{"corrected":"Bonjour.\\nJe préfère les chats.\\nIls sont calmes.",'
        '"translation":"你好。\\n我更喜欢猫。\\n它们很安静。",'
        '"target_word_used":true,"incomplete":false,"errors":[],'
        '"is_nsfw":false,"feedback":"三行结构清楚。"}'
    )
    fake_llm["reinstall"]()

    resp = client.post("/write/submit", data={
        "mode": "diary",
        "prompt": "你更喜欢猫还是狗，为什么？",
        "diary": "Bonjour.\nJe prefere les chats.\nIls sont calmes.",
    })
    assert resp.status_code == 200
    assert "三行结构清楚" in resp.get_data(as_text=True)
    client.post("/write/save")
    with bypass_engine.connect() as c:
        eid, word_id, word_text, lang = c.execute(text(
            "SELECT id, word_id, word_text, language_code "
            "FROM output_entries WHERE corrected LIKE 'Bonjour.%'"
        )).one()
    assert word_id is None
    assert word_text == "三行日记"
    assert lang == "fr"

    history = client.get("/write/history").get_data(as_text=True)
    assert "三行日记" in history
    client.post(f"/write/{eid}/publish")
    square = client.get("/square?lang=fr").get_data(as_text=True)
    assert "Bonjour." in square
    assert "三行日记" in square


def test_diary_requires_three_lines(app, client, bypass_engine, fake_llm):
    provision_user(app, "diarybad@t.com", PW)
    login(client, "diarybad@t.com", PW)
    _switch_lang(client, "fr")

    resp = client.post("/write/submit", data={
        "mode": "diary",
        "prompt": "今天有什么小事让你心情变好了？",
        "diary": "Bonjour.\nDeux lignes seulement.",
    })

    assert resp.status_code == 200
    assert "正好写满 3 行" in resp.get_data(as_text=True)


def test_chinese_write_uses_french_feedback_language(app, client, bypass_engine, fake_llm):
    uid = provision_user(app, "wr-zh-fr@t.com", PW)
    login(client, "wr-zh-fr@t.com", PW)
    client.post("/settings", data={"languages": ["zh"], "feedback_language": "fr"})
    client.post("/words/add", json={"language_code": "zh", "word": "学习",
                                    "definitions": [{"meaning": "apprendre"}]})
    with bypass_engine.connect() as c:
        wid = c.execute(text(
            "SELECT w.id FROM words w JOIN word_lists wl ON w.list_id=wl.id "
            "WHERE wl.user_id=:u AND wl.language_code='zh' AND w.word='学习'"),
            {"u": uid}).scalar()

    fake_llm["content"] = (
        '{"corrected":"我喜欢学习中文。","translation":"J’aime apprendre le chinois.",'
        '"target_word_used":true,"incomplete":false,"errors":[],'
        '"is_nsfw":false,"feedback":"Phrase correcte."}'
    )
    fake_llm["reinstall"]()

    page = client.get("/write").get_data(as_text=True)
    assert "学习" in page
    resp = client.post("/write/submit", data={
        "mode": "sentence",
        "word_id": wid,
        "sentence": "我喜欢学习中文。",
    })
    body = resp.get_data(as_text=True)
    assert resp.status_code == 200
    assert "J’aime apprendre le chinois." in body
    assert "Phrase correcte." in body


def test_compose_uses_current_language_and_rejects_other_language_word(
        app, client, bypass_engine, fake_llm):
    uid, _ = _setup_user_with_word(app, client, bypass_engine)
    client.post("/words/add", json={"language_code": "en", "word": "apple",
                                    "definitions": [{"meaning": "苹果"}]})
    with bypass_engine.connect() as c:
        en_wid = c.execute(text("SELECT id FROM words WHERE word='apple'")).scalar()

    _switch_lang(client, "fr")
    page = client.get("/write").get_data(as_text=True)
    assert "décollage" in page
    assert "apple" not in page
    assert 'type="hidden" name="word_id"' in page
    assert '<select name="word_id"' not in page

    resp = client.post("/write/submit", data={"word_id": en_wid, "sentence": "Apple."})
    assert resp.status_code == 404
    with bypass_engine.connect() as c:
        used = c.execute(text(
            "SELECT corrections_today FROM user_quota WHERE user_id=:u"),
            {"u": uid}).scalar()
    assert used == 0


def test_rejects_obvious_non_target_script_before_correction(
        app, client, bypass_engine, fake_llm):
    uid, wid = _setup_user_with_word(app, client, bypass_engine)

    resp = client.post("/write/submit", data={"word_id": wid, "sentence": "我今天很开心。"})
    page = resp.get_data(as_text=True)
    assert resp.status_code == 200
    assert "不是当前目标语言" in page
    assert _count_entries(bypass_engine, uid) == 0
    with bypass_engine.connect() as c:
        used = c.execute(text(
            "SELECT corrections_today FROM user_quota WHERE user_id=:u"),
            {"u": uid}).scalar()
    assert used == 0


def test_japanese_rejects_latin_only_sentence_before_correction(
        app, client, bypass_engine, fake_llm):
    uid = provision_user(app, "ja-guard@t.com", PW)
    login(client, "ja-guard@t.com", PW)
    client.post("/settings", data={"languages": ["ja"]})
    client.post("/words/add", json={"language_code": "ja", "word": "猫",
                                    "definitions": [{"meaning": "chat"}]})
    with bypass_engine.connect() as c:
        wid = c.execute(text(
            "SELECT w.id FROM words w JOIN word_lists wl ON w.list_id=wl.id "
            "WHERE wl.user_id=:u AND wl.language_code='ja' AND w.word='猫'"
        ), {"u": uid}).scalar()

    resp = client.post("/write/submit", data={
        "word_id": wid,
        "sentence": "watashi wa neko desu",
    })

    assert resp.status_code == 200
    assert "不是当前目标语言" in resp.get_data(as_text=True)
    with bypass_engine.connect() as c:
        used = c.execute(text(
            "SELECT corrections_today FROM user_quota WHERE user_id=:u"),
            {"u": uid}).scalar()
    assert used == 0


def test_compose_prioritizes_due_lapses(app, client, bypass_engine, fake_llm):
    _setup_user_with_word(app, client, bypass_engine)
    client.post("/words/add", json={"language_code": "fr", "word": "fragile",
                                    "definitions": [{"meaning": "易碎"}]})
    client.post("/words/add", json={"language_code": "fr", "word": "steady",
                                    "definitions": [{"meaning": "稳定"}]})
    with bypass_engine.connect() as c:
        c.execute(text(
            "UPDATE words SET due_date='2020-01-01', lapses=3 "
            "WHERE word='fragile'"))
        c.execute(text(
            "UPDATE words SET due_date='2020-01-01', lapses=0 "
            "WHERE word='steady'"))
        c.commit()

    page = client.get("/write").get_data(as_text=True)
    assert "今日推荐" in page
    assert "fragile" in page
    assert "steady" not in page
    assert '<select name="word_id"' not in page


def test_saving_sentence_refreshes_recommended_word(
        app, client, bypass_engine, fake_llm):
    _, first_wid = _setup_user_with_word(app, client, bypass_engine)
    client.post("/words/add", json={"language_code": "fr", "word": "steady",
                                    "definitions": [{"meaning": "稳定"}]})
    with bypass_engine.connect() as c:
        second_wid = c.execute(text(
            "SELECT id FROM words WHERE word='steady'"
        )).scalar_one()
        c.execute(text(
            "UPDATE words SET due_date='2020-01-01' WHERE id=:wid"
        ), {"wid": first_wid})
        c.execute(text(
            "UPDATE words SET due_date='2020-01-02' WHERE id=:wid"
        ), {"wid": second_wid})
        c.commit()

    first_page = client.get("/write").get_data(as_text=True)
    assert f'name="word_id" value="{first_wid}"' in first_page

    client.post("/write/submit", data={
        "word_id": first_wid,
        "sentence": "Un essai.",
    })
    client.post("/write/save")

    refreshed_page = client.get("/write").get_data(as_text=True)
    assert f'name="word_id" value="{second_wid}"' in refreshed_page
    assert f'name="word_id" value="{first_wid}"' not in refreshed_page


def test_target_word_not_used_flagged(app, client, bypass_engine, fake_llm):
    uid, wid = _setup_user_with_word(app, client, bypass_engine)
    fake_llm["content"] = ('{"corrected":"x","translation":"t","target_word_used":false,'
                           '"incomplete":false,"errors":[],"is_nsfw":false,"feedback":""}')
    fake_llm["reinstall"]()
    r = client.post("/write/submit", data={"word_id": wid, "sentence": "x"})
    assert "没用到目标词" in r.get_data(as_text=True)


def test_publish_blocked_for_nsfw(app, client, bypass_engine, fake_llm):
    uid, wid = _setup_user_with_word(app, client, bypass_engine)
    fake_llm["nsfw_content"] = '{"is_nsfw":true}'
    fake_llm["reinstall"]()
    client.post("/write/submit", data={"word_id": wid, "sentence": "x"})
    client.post("/write/save")
    with bypass_engine.connect() as c:
        eid = c.execute(text("SELECT id FROM output_entries WHERE user_id=:u"),
                        {"u": uid}).scalar()
    assert client.post(f"/write/{eid}/publish").status_code == 400   # NSFW 不可公开


def test_cross_user_history_isolation(app, client, bypass_engine, fake_llm):
    # B 造句保存
    ub, wb = _setup_user_with_word(app, client, bypass_engine, email="b@t.com")
    client.post("/write/submit", data={"word_id": wb, "sentence": "B phrase."})
    client.post("/write/save")
    with bypass_engine.connect() as c:
        b_entry = c.execute(text("SELECT id FROM output_entries WHERE user_id=:u"),
                            {"u": ub}).scalar()
    # A 登录前先登出 B（已登录时 /login 会直接重定向、不换人）
    client.get("/logout")
    provision_user(app, "a@t.com", PW)
    login(client, "a@t.com", PW)
    assert "B phrase." not in client.get("/write/history").get_data(as_text=True)
    assert client.post(f"/write/{b_entry}/publish").status_code == 400
    assert client.post(f"/write/{b_entry}/unpublish").status_code == 400


def test_sentence_too_long_400(app, client, bypass_engine, fake_llm):
    uid, wid = _setup_user_with_word(app, client, bypass_engine)
    resp = client.post("/write/submit", data={"word_id": wid, "sentence": "x" * 141})
    assert resp.status_code == 400


def test_completed_sentence_word_still_recommended_small_library(
        app, client, bypass_engine, fake_llm):
    """复现（用户症状）：词库很小（单个词）时，完成造句并保存后，
    /write 不再把同一个词推荐为今日目标词（保存后词被重调度到未来）。"""
    _, wid = _setup_user_with_word(app, client, bypass_engine)

    page = client.get("/write").get_data(as_text=True)
    assert f'name="word_id" value="{wid}"' in page

    client.post("/write/submit", data={
        "word_id": wid,
        "sentence": "Un essai.",
    })
    client.post("/write/save")

    refreshed = client.get("/write").get_data(as_text=True)
    # 已完成的词已不因到期被推荐；且空状态是"没有到期词"，不是"还没有词"
    assert f'name="word_id" value="{wid}"' not in refreshed
    assert "没有到期的目标词" in refreshed
    assert "还没有词" not in refreshed
    assert "去加词" not in refreshed


def test_due_word_written_recently_falls_back_as_target_single_word(
        app, client, bypass_engine, fake_llm):
    """回退语义：唯一到期词是近 7 天写的，/write 仍推荐它（不把页面写空），
    与 due_count（首页"待复习 N"）保持一致。"""
    _, wid = _setup_user_with_word(app, client, bypass_engine)
    client.post("/write/submit", data={"word_id": wid, "sentence": "Un essai."})
    client.post("/write/save")
    # 模拟保存后仍到期（例如写过的词第二天又到期、或遗留未重调度数据）
    with bypass_engine.connect() as c:
        c.execute(text(
            "UPDATE words SET due_date='2026-07-19' WHERE id=:wid"
        ), {"wid": wid})
        c.commit()

    page = client.get("/write").get_data(as_text=True)
    assert f'name="word_id" value="{wid}"' in page


def test_word_with_sentence_eight_days_ago_is_recommended_when_due(
        app, client, bypass_engine, fake_llm):
    """窗口语义：entry 超过 7 天（此处 8 天）不再算"最近写过"，
    词到期时回到优先目标池（锁定 7 天窗口不是永久排除）。"""
    _, wid = _setup_user_with_word(app, client, bypass_engine)
    with bypass_engine.connect() as c:
        uid = c.execute(text(
            "SELECT wl.user_id FROM words w JOIN word_lists wl ON wl.id=w.list_id "
            "WHERE w.id=:w"), {"w": wid}).scalar_one()
        c.execute(text(
            "UPDATE words SET due_date='2026-07-19', last_review=NULL WHERE id=:w"
        ), {"w": wid})
        c.execute(text(
            "INSERT INTO output_entries(user_id, word_id, original, corrected, "
            "feedback, translation, word_text, language_code, is_public, is_nsfw, "
            "upvote_count, created_at) "
            "VALUES(:u, :w, 'x', 'x', '', '', 'décollage', 'fr', false, false, "
            "0, now() - interval '8 days')"
        ), {"u": uid, "w": wid})
        c.commit()

    page = client.get("/write").get_data(as_text=True)
    assert f'name="word_id" value="{wid}"' in page


def test_rotation_prefers_unwritten_due_word_over_recently_written(
        app, client, bypass_engine, fake_llm):
    """轮换：两个到期词，A 近 7 天写过、B 从未写过 → 目标词是 B 而不是 A。"""
    _, first_wid = _setup_user_with_word(app, client, bypass_engine)
    client.post("/words/add", json={"language_code": "fr", "word": "steady",
                                    "definitions": [{"meaning": "稳定"}]})
    with bypass_engine.connect() as c:
        second_wid = c.execute(text(
            "SELECT id FROM words WHERE word='steady'"
        )).scalar_one()
        uid = c.execute(text(
            "SELECT wl.user_id FROM words w JOIN word_lists wl ON wl.id=w.list_id "
            "WHERE w.id=:w"), {"w": first_wid}).scalar_one()
        c.execute(text(
            "UPDATE words SET due_date='2026-07-19' WHERE id=:w"), {"w": second_wid})
        c.execute(text(
            "INSERT INTO output_entries(user_id, word_id, original, corrected, "
            "feedback, translation, word_text, language_code, is_public, is_nsfw, "
            "upvote_count, created_at) "
            "VALUES(:u, :w, 'x', 'x', '', '', 'décollage', 'fr', false, false, "
            "0, now())"
        ), {"u": uid, "w": first_wid})
        c.execute(text(
            "UPDATE words SET due_date='2026-07-19' WHERE id=:w"), {"w": first_wid})
        c.commit()

    page = client.get("/write").get_data(as_text=True)
    assert f'name="word_id" value="{second_wid}"' in page
    assert f'name="word_id" value="{first_wid}"' not in page


def test_story_handoff_target_shown_when_practice_pool_empty(
        app, client, bypass_engine, fake_llm):
    """review-story handoff：practice 池为空（故事词未到期）时，
    /write?source=review-story 仍显示故事指定词。"""
    uid, wid = _setup_user_with_word(app, client, bypass_engine)
    with bypass_engine.connect() as c:
        # 把故事词推到未来，使其不在 practice 池
        c.execute(text(
            "UPDATE words SET due_date=now() + interval '10 days' WHERE id=:w"
        ), {"w": wid})
        c.execute(text(
            "INSERT INTO review_story_runs(user_id, local_date, target_language, "
            "feedback_language, contract_version, input_hash, term_word_ids, "
            "status, attempt_count, attempt_version, content_expires_at, "
            "created_at, updated_at) "
            "VALUES(:u, CURRENT_DATE, 'fr', 'zh', 'test', :h, :terms, 'ready', "
            "0, 0, now() + interval '1 hour', now(), now())"
        ), {
            "u": uid,
            "h": "a" * 64,
            "terms": f'{{"k1": {wid}}}',
        })
        c.commit()
        run_id = c.execute(text(
            "SELECT id FROM review_story_runs WHERE user_id=:u"), {"u": uid}
        ).scalar_one()

    handoff = client.post("/write/from-story", data={
        "story_run_id": run_id,
        "term_key": "k1",
    })
    assert handoff.status_code in (200, 302)
    page = client.get("/write?source=review-story").get_data(as_text=True)
    assert f'name="word_id" value="{wid}"' in page


def test_backfill_write_scheduling_grades_legacy_words(
        app, bypass_engine):
    """backfill：有 output_entry 但从未被重调度的词（last_review 早于记录），
    dry-run 统计、apply 推 due_date 到未来且幂等。"""
    from app.services import writing as writing_svc
    from app.services.timeutil import utc_now
    from datetime import timedelta

    uid = provision_user(app, "backfill@t.com", PW)
    with bypass_engine.connect() as c:
        c.execute(text(
            "INSERT INTO word_lists(user_id, name, language_code, created_at) "
            "VALUES(:u, 'fr', 'fr', now()) RETURNING id"), {"u": uid})
        c.commit()
    with bypass_engine.connect() as c:
        list_id = c.execute(text(
            "SELECT id FROM word_lists WHERE user_id=:u"), {"u": uid}
        ).scalar_one()
        c.execute(text(
            "INSERT INTO words(list_id, word, marked, due_date, reps, interval, ease, lapses) "
            "VALUES(:l, 'legacy', false, '2026-07-19', 0, 1, 2.5, 0) RETURNING id"), {"l": list_id})
        c.commit()
    with bypass_engine.connect() as c:
        wid = c.execute(text(
            "SELECT id FROM words WHERE word='legacy'")).scalar_one()
        c.execute(text(
            "INSERT INTO output_entries(user_id, word_id, original, corrected, "
            "feedback, translation, word_text, language_code, is_public, is_nsfw, "
            "upvote_count, created_at) "
            "VALUES(:u, :w, 'x', 'x', '', '', 'legacy', 'fr', false, false, "
            "0, now() - interval '4 days')"
        ), {"u": uid, "w": wid})
        c.commit()

    with bypass_engine.begin() as conn:
        stats = writing_svc.backfill_write_scheduling(conn, dry_run=True)
        assert stats.candidates == 1
        assert stats.applied == 0
        stats2 = writing_svc.backfill_write_scheduling(conn)
        assert stats2.candidates == 1
        assert stats2.applied == 1
        # 幂等：再跑一次无候选
        stats3 = writing_svc.backfill_write_scheduling(conn)
        assert stats3.candidates == 0

    with bypass_engine.connect() as c:
        row = c.execute(text(
            "SELECT reps, interval, due_date, last_review FROM words WHERE id=:w"
        ), {"w": wid}).fetchone()
        assert row.reps == 1
        assert row.interval == 1
        assert row.due_date > utc_now() - timedelta(minutes=1)
        assert row.last_review is not None
