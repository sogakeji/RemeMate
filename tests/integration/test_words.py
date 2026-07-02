"""阶段三：词库 CRUD + RLS 隔离 + 复习递推 + stats（走 HTTP，真实 RLS 路径）。"""
import re

from sqlalchemy import text

from tests.helpers import provision_user, login, make_user, make_word

PW = "pw12345678"


def _switch_lang(client, code):
    """经首页切换器设当前语言（隐式词表闭环：自动建该语言词表 + 写 current_language）。"""
    csrf = re.search(r'name="csrf_token"[^>]*value="([^"]+)"',
                     client.get("/").get_data(as_text=True)).group(1)
    client.post("/language/switch", data={"language_code": code, "csrf_token": csrf})


def _add_word(client, language_code, word, meaning="m", example=None, note=None):
    return client.post("/words/add", json={
        "language_code": language_code,
        "word": word,
        "definitions": [{"meaning": meaning, "example": example, "note": note}],
    })


def test_language_list_and_add_word(app, client, bypass_engine):
    provision_user(app, "a@t.com", PW)
    login(client, "a@t.com", PW)

    _switch_lang(client, "fr")
    _add_word(client, "fr", "décollage", "起飞")
    with bypass_engine.connect() as c:
        list_id = c.execute(text("SELECT id FROM word_lists WHERE language_code='fr'")).scalar()
    detail = client.get(f"/words/{list_id}").get_data(as_text=True)
    assert "décollage" in detail and "起飞" in detail


def test_words_list_shows_example_note_actions(app, client, bypass_engine):
    provision_user(app, "rich@t.com", PW)
    login(client, "rich@t.com", PW)

    _switch_lang(client, "fr")
    _add_word(client, "fr", "conquis", "征服", "Ils ont conquis la France.", "漫画征服法国读者")

    page = client.get("/words").get_data(as_text=True)

    assert "Ils ont conquis la France." in page
    assert "漫画征服法国读者" in page
    assert "data-speak=\"conquis\"" in page
    assert "/toggle-marked" in page
    assert "/edit" in page


def test_toggle_marked_from_review_card(app, client, bypass_engine):
    provision_user(app, "mark@t.com", PW)
    login(client, "mark@t.com", PW)
    _switch_lang(client, "fr")
    _add_word(client, "fr", "etoile", "星星")
    with bypass_engine.connect() as c:
        wid = c.execute(text("SELECT id FROM words WHERE word='etoile'")).scalar()

    resp = client.post(
        f"/words/{wid}/toggle-marked",
        headers={"HX-Request": "true"},
    )

    assert resp.status_code == 200
    body = resp.get_data(as_text=True)
    assert "etoile" in body
    assert "取消标记" in body
    with bypass_engine.connect() as c:
        marked = c.execute(text("SELECT marked FROM words WHERE id=:i"), {"i": wid}).scalar()
    assert marked is True


def test_edit_word_updates_definitions(app, client, bypass_engine):
    provision_user(app, "edit@t.com", PW)
    login(client, "edit@t.com", PW)
    _switch_lang(client, "fr")
    _add_word(client, "fr", "ancien", "旧的")
    with bypass_engine.connect() as c:
        wid = c.execute(text("SELECT id FROM words WHERE word='ancien'")).scalar()

    page = client.get(f"/words/{wid}/edit").get_data(as_text=True)
    assert "修改词条" in page
    resp = client.post(f"/words/{wid}/edit", data={
        "word": "nouveau",
        "part_of_speech": ["adj."],
        "meaning": ["新的"],
        "example": ["Un nouveau livre."],
        "note": ["注意阴阳性配合"],
    }, follow_redirects=True)

    assert resp.status_code == 200
    body = resp.get_data(as_text=True)
    assert "nouveau" in body
    assert "Un nouveau livre." in body
    assert "注意阴阳性配合" in body
    with bypass_engine.connect() as c:
        old_count = c.execute(text("SELECT count(*) FROM words WHERE word='ancien'")).scalar()
        row = c.execute(text(
            "SELECT w.word, d.part_of_speech, d.meaning, d.example, d.note "
            "FROM words w JOIN definitions d ON d.word_id=w.id WHERE w.id=:i"
        ), {"i": wid}).one()
    assert old_count == 0
    assert row == ("nouveau", "adj.", "新的", "Un nouveau livre.", "注意阴阳性配合")


def test_cross_user_list_isolation(app, client, bypass_engine):
    # 用户 B 的词表（用 bypass 造），用户 A 登录后不可见、不可访问
    b = make_user(bypass_engine, "b@t.com")
    b_list, _ = make_word(bypass_engine, b)        # B 的词表 + 词

    provision_user(app, "a@t.com", PW)
    login(client, "a@t.com", PW)

    assert client.get(f"/words/{b_list}").status_code == 404   # 越权访问被拦
    assert client.get("/words").status_code == 200
    assert "b@t.com" not in client.get("/words").get_data(as_text=True)


def test_review_grade_updates_sm2(app, client, bypass_engine):
    provision_user(app, "r@t.com", PW)
    login(client, "r@t.com", PW)
    _switch_lang(client, "fr")
    _add_word(client, "fr", "w1", "m")
    with bypass_engine.connect() as c:
        word_id = c.execute(text("SELECT id FROM words WHERE word='w1'")).scalar()

    # 复习页应展示到期词
    assert "w1" in client.get("/review").get_data(as_text=True)

    # 评 easy → 通过：reps 0→1，due 推到未来，写一条 ReviewLog
    client.post(f"/review/{word_id}/grade", data={"button": "easy"})
    with bypass_engine.connect() as c:
        reps, due = c.execute(text(
            "SELECT reps, due_date FROM words WHERE id=:i"), {"i": word_id}).fetchone()
        logs = c.execute(text(
            "SELECT count(*) FROM review_logs WHERE word_id=:i"), {"i": word_id}).scalar()
    assert reps == 1
    assert logs == 1
    from app.services.timeutil import utc_now
    assert due > utc_now()      # 不再到期


def test_grade_invalid_button_400(app, client, bypass_engine):
    """M1：缺失/非法 button 返回 400 而非 500。"""
    provision_user(app, "g@t.com", PW)
    login(client, "g@t.com", PW)
    _switch_lang(client, "fr")
    _add_word(client, "fr", "w1", "m")
    with bypass_engine.connect() as c:
        wid = c.execute(text("SELECT id FROM words WHERE word='w1'")).scalar()

    assert client.post(f"/review/{wid}/grade", data={}).status_code == 400
    assert client.post(f"/review/{wid}/grade",
                       data={"button": "bogus"}).status_code == 400


def test_review_grade_other_users_word_404(app, client, bypass_engine):
    b = make_user(bypass_engine, "b@t.com")
    _, b_word = make_word(bypass_engine, b)
    provision_user(app, "a@t.com", PW)
    login(client, "a@t.com", PW)
    assert client.post(f"/review/{b_word}/grade", data={"button": "easy"}).status_code == 404
    assert client.get(f"/words/{b_word}/edit").status_code == 404
    assert client.post(f"/words/{b_word}/toggle-marked").status_code == 404


def test_stats_counts(app, client, bypass_engine):
    provision_user(app, "s@t.com", PW)
    login(client, "s@t.com", PW)
    # stats 按当前语言看板：先切 fr（隐式化后 stats 未设语言是引导卡）
    _switch_lang(client, "fr")
    _add_word(client, "fr", "w1", "m")
    _add_word(client, "fr", "w2", "m")

    page = client.get("/stats").get_data(as_text=True)
    # UI 套了卡片网格：数字与「总词数 / 待复习」标签分体；守语义即可。
    # 卡片里数字裸在 >N< 中，且本页 list_count=1 total=2 due=2 reviewed=0，
    # 出现两次「>2<」对应总词数与待复习两张卡的数字段。
    assert "总词数" in page
    assert "待复习" in page
    assert page.count(">2<") >= 2


def test_post_create_list_route_removed(app, client, bypass_engine):
    provision_user(app, "d@t.com", PW)
    login(client, "d@t.com", PW)
    assert client.post("/words", data={"name": "ToDelete", "language_code": "fr"}).status_code == 405


def test_post_add_word_to_list_route_removed(app, client, bypass_engine):
    provision_user(app, "pa@t.com", PW)
    login(client, "pa@t.com", PW)
    _switch_lang(client, "fr")
    with bypass_engine.connect() as c:
        list_id = c.execute(text("SELECT id FROM word_lists WHERE language_code='fr'")).scalar()
    assert client.post(f"/words/{list_id}", data={"word": "w1", "meaning": "m"}).status_code == 405


def test_delete_list_service_after_review_cascades(app, client, bypass_engine):
    """回归 review 2026-06-23：内部词表删除时 review_logs 仍由 DB 级联清理。"""
    uid = provision_user(app, "dr@t.com", PW)
    login(client, "dr@t.com", PW)
    _switch_lang(client, "fr")
    _add_word(client, "fr", "w1", "m")
    with bypass_engine.connect() as c:
        lid = c.execute(text("SELECT id FROM word_lists WHERE language_code='fr'")).scalar()
        wid = c.execute(text("SELECT id FROM words WHERE word='w1'")).scalar()
    client.post(f"/review/{wid}/grade", data={"button": "easy"})   # 产生 review_logs

    with bypass_engine.connect() as c:
        c.execute(text("DELETE FROM word_lists WHERE id=:i AND user_id=:u"),
                  {"i": lid, "u": uid})
        c.commit()
        assert c.execute(text("SELECT count(*) FROM word_lists WHERE id=:i"),
                         {"i": lid}).scalar() == 0
        # 子表也清干净
        assert c.execute(text("SELECT count(*) FROM review_logs WHERE word_id=:i"),
                         {"i": wid}).scalar() == 0
        assert c.execute(text("SELECT count(*) FROM words WHERE id=:i"),
                         {"i": wid}).scalar() == 0
