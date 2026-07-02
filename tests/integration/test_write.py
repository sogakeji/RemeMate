"""造句闭环：不自动保存 / 显式保存 / 刷新不重存 / 额度 / 隔离 / NSFW 发布拦截。"""
import re

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
    fake_llm["content"] = ('{"corrected":"x","translation":"t","target_word_used":true,'
                           '"incomplete":false,"errors":[],"is_nsfw":true,"feedback":""}')
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

    assert resp.status_code == 400


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
    assert page.index("fragile") < page.index("steady")


def test_target_word_not_used_flagged(app, client, bypass_engine, fake_llm):
    uid, wid = _setup_user_with_word(app, client, bypass_engine)
    fake_llm["content"] = ('{"corrected":"x","translation":"t","target_word_used":false,'
                           '"incomplete":false,"errors":[],"is_nsfw":false,"feedback":""}')
    fake_llm["reinstall"]()
    r = client.post("/write/submit", data={"word_id": wid, "sentence": "x"})
    assert "没用到目标词" in r.get_data(as_text=True)


def test_publish_blocked_for_nsfw(app, client, bypass_engine, fake_llm):
    uid, wid = _setup_user_with_word(app, client, bypass_engine)
    fake_llm["content"] = ('{"corrected":"x","translation":"t","target_word_used":true,'
                           '"incomplete":false,"errors":[],"is_nsfw":true,"feedback":""}')
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
