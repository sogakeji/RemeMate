"""ui-rescope 地基层：隐式词表不变量、多词义加词、llm 高层封装、stats 补充。"""
import json

from sqlalchemy import text

from tests.helpers import provision_user


def _set_rls_uid(app, uid):
    """在 app 文件 session（受 RLS 的 rememate 角色）注入 GUC，等同真实请求里的钩子。

    裸 app_context 不带请求钩子，after_begin 不会触发（rls.py has_request_context 守卫），
    故 service 层写 word_lists 会被 RLS 拒（埋点全空）。这里手动设 GUC 让 service 层在
    裸上下文里也能验证 RLS 路径。真实 HTTP 请求由钩子自动设，无需此步。
    """
    from flask import g
    g.rls_uid = uid
    from app.extensions import db
    # is_local=false：GUC 跨该 session 连接的事务持久（service 层 commit 后仍有效）。
    # 裸 app_context 无请求钩子（rls.py has_request_context 守卫），必须手动设。
    db.session.execute(
        text("SELECT set_config('app.current_user_id', :u, false)"), {"u": str(uid)})
    db.session.commit()


# ---- 隐式词表不变量：每用户每语言零或一张 ----

def test_get_or_create_language_list_idempotent(app, bypass_engine):
    """同一用户同一语言反复调用只建一张词表（不变量守住）。"""
    from app.services import words
    uid = provision_user(app, "i@t.com")
    with app.app_context():
        _set_rls_uid(app, uid)
        wl1 = words.get_or_create_language_list(uid, "fr")
        wl2 = words.get_or_create_language_list(uid, "fr")
        assert wl1.id == wl2.id            # 复用，不另建
    with bypass_engine.connect() as c:
        n = c.execute(text(
            "SELECT count(*) FROM word_lists WHERE user_id=:u AND language_code='fr'"
        ), {"u": uid}).scalar()
    assert n == 1


def test_get_or_create_language_list_per_language(app, bypass_engine):
    """不同语言派生不同词表，互不影响。"""
    from app.services import words
    uid = provision_user(app, "m@t.com")
    with app.app_context():
        _set_rls_uid(app, uid)
        wl_fr = words.get_or_create_language_list(uid, "fr")
        wl_en = words.get_or_create_language_list(uid, "en")
        assert wl_fr.id != wl_en.id
        assert wl_fr.name == "法语"            # 内部语言名，用户不可见
    with bypass_engine.connect() as c:
        n = c.execute(text(
            "SELECT count(*) FROM word_lists WHERE user_id=:u"
        ), {"u": uid}).scalar()
    assert n == 2


# ---- 多词义加词 ----

def test_add_word_multiple_definitions(app, bypass_engine):
    """加词中心 JSON 多词义：一词挂多条 Definition。"""
    from app.services import words
    uid = provision_user(app, "d@t.com")
    with app.app_context():
        _set_rls_uid(app, uid)
        wl = words.get_or_create_language_list(uid, "fr")
        defs = [
            {"part_of_speech": "n.", "meaning": "起飞", "example": "e1", "note": "n1"},
            {"part_of_speech": "v.", "meaning": "取下", "example": "e2", "note": "n2"},
        ]
        w = words.add_word(uid, wl.id, "décollage", definitions=defs)
        wid = w.id
    with bypass_engine.connect() as c:
        rows = c.execute(text(
            "SELECT part_of_speech, meaning FROM definitions WHERE word_id=:w "
            "ORDER BY id"), {"w": wid}).fetchall()
    assert {r[0] for r in rows} == {"n.", "v."}
    assert len(rows) == 2


def test_add_word_single_definition_backward_compat(app, bypass_engine):
    """旧单释义调用（无 definitions）仍建一条。"""
    from app.services import words
    uid = provision_user(app, "s@t.com")
    with app.app_context():
        _set_rls_uid(app, uid)
        wl = words.get_or_create_language_list(uid, "fr")
        w = words.add_word(uid, wl.id, "x", meaning="m", part_of_speech="n.")
        wid = w.id
    with bypass_engine.connect() as c:
        n = c.execute(text(
            "SELECT count(*) FROM definitions WHERE word_id=:w"), {"w": wid}).scalar()
    assert n == 1


# ---- stats 补充：top_lapses + heatmap 结构 ----

def test_get_stats_has_top_lapses_and_heatmap(app, bypass_engine):
    """stats 带易忘词 Top + 热力图。复习日志写到「昨天本地」避免跨午夜时钟抖动。"""
    from app.services import words
    uid = provision_user(app, "h@t.com", tz="Asia/Shanghai")
    with app.app_context():
        _set_rls_uid(app, uid)
        wl = words.get_or_create_language_list(uid, "fr")
        w = words.add_word(uid, wl.id, "forgetme", meaning="m")
        with bypass_engine.begin() as c:
            c.execute(text("UPDATE words SET lapses=3 WHERE id=:i"), {"i": w.id})
            # ts 设「2 天前 UTC」：无论当下是否撞上本地午夜，昨天一定已过且在网格内
            c.execute(text(
                "INSERT INTO review_logs(word_id,user_id,ts,grade,source,interval_after) "
                "VALUES (:w,:u,now()-interval '2 days',5,'review',1)"),
                {"w": w.id, "u": uid})
        stats = words.get_stats(uid)
        top_words = [item.word for item in stats["top_lapses"]]
        heatmap = stats["heatmap"]
    assert "top_lapses" in stats and "heatmap" in stats
    assert "forgetme" in top_words
    assert "weeks" in heatmap and "total" in heatmap
    assert len(heatmap["weeks"]) == 12
    assert all(len(col) == 7 for col in heatmap["weeks"])
    assert heatmap["total"] >= 1                   # 两天前的复习一定计入网格


# ---- llm 高层封装：fail-closed，注入假 provider ----

def _install_llm(monkeypatch_content, *, task="general", mode="ok"):
    """注入假 registry：ok 模式返回给定 content，down 模式空链。"""
    from app.services import llm

    class FP:
        name = "fake"

        def call(self, messages, *, timeout, json_mode=False):
            return llm.LLMResult(monkeypatch_content, 10, 20, "fake", "fake-model")

    if mode == "down":
        llm.set_registry({task: [], "general": []})
    else:
        llm.set_registry({task: [FP()], "general": [FP()]})
    llm.reset_breaker()
    return llm


def test_generate_example_returns_text(app):
    from app.services import llm
    with app.app_context():
        _install_llm("这是一条例句。")
        out = llm.generate_example("décollage", "n.", "起飞", language="法语")
    assert out == "这是一条例句。"


def test_generate_example_down_returns_none(app):
    from app.services import llm
    with app.app_context():
        _install_llm("x", mode="down")
        out = llm.generate_example("x", "n.", "x", language="法语")
    assert out is None                                # fail-closed


def test_generate_full_word_info_parses_definitions(app):
    from app.services import llm
    payload = json.dumps({"definitions": [
        {"part_of_speech": "n.", "meaning": "起飞", "example": "e", "note": "n"}]})
    with app.app_context():
        _install_llm(payload, task="extract")
        out = llm.generate_full_word_info("décollage", language="法语")
    assert "definitions" in out
    assert out["definitions"][0]["meaning"] == "起飞"


def test_generate_full_word_info_down_returns_error(app):
    from app.services import llm
    with app.app_context():
        _install_llm("x", task="extract", mode="down")
        out = llm.generate_full_word_info("décollage", language="法语")
    assert "error" in out