"""造句闭环：不自动保存 / 显式保存 / 刷新不重存 / 额度 / 隔离 / NSFW 发布拦截。"""
from sqlalchemy import text

from tests.helpers import provision_user, login

PW = "pw12345678"


def _setup_user_with_word(app, client, bypass_engine, email="w@t.com"):
    provision_user(app, email, PW)
    login(client, email, PW)
    client.post("/words", data={"name": "L", "language_code": "fr"})
    with bypass_engine.connect() as c:
        lid = c.execute(text("SELECT id FROM word_lists WHERE name='L'")).scalar()
    client.post(f"/words/{lid}", data={"word": "décollage", "meaning": "起飞"})
    with bypass_engine.connect() as c:
        wid = c.execute(text("SELECT id FROM words WHERE word='décollage'")).scalar()
        uid = c.execute(text("SELECT id FROM users WHERE email=:e"), {"e": email}).scalar()
    return uid, wid


def _count_entries(bypass_engine, uid):
    with bypass_engine.connect() as c:
        return c.execute(text("SELECT count(*) FROM output_entries WHERE user_id=:u"),
                         {"u": uid}).scalar()


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


def test_sentence_too_long_400(app, client, bypass_engine, fake_llm):
    uid, wid = _setup_user_with_word(app, client, bypass_engine)
    resp = client.post("/write/submit", data={"word_id": wid, "sentence": "x" * 141})
    assert resp.status_code == 400
