"""ui-rescope step3：手动加词——手工 JSON 多词义 + AI 三端点 + 隐式建表闭环。"""
import json

from sqlalchemy import text
from tests.helpers import provision_user, login

PW = "pw12345678"


def _install_llm(holder=None):
    """注入假 provider 给 general/extract 链，返回 holder 便于改返回内容。"""
    from app.services import llm

    holder = holder or {"content": '{"definitions":[{"part_of_speech":"n.","meaning":"起飞","example":"le décollage","note":"巧记"}]}'}

    class FP:
        name = "fake"

        def call(self, messages, *, timeout, json_mode=False):
            return llm.LLMResult(holder["content"], 10, 20, "fake", "fake-model")

    llm.set_registry({"general": [FP()], "extract": [FP()]})
    llm.reset_breaker()
    return holder


def _auth(client, app):
    uid = provision_user(app, "add1@t.com", PW)
    login(client, "add1@t.com", PW)
    return uid


def _csrf(client):
    import re
    m = re.search(r'name="csrf_token"[^>]*value="([^"]+)"', client.get("/words/add").get_data(as_text=True))
    return m.group(1) if m else ""


def test_add_center_handcrafts_multidef(app, client, bypass_engine):
    """GET /words/add 200；POST 多词义 JSON 入库到该语言隐式词表。"""
    uid = _auth(client, app)
    page = client.get("/words/add").get_data(as_text=True)
    assert "手动加词" in page and "AI 填充" in page

    resp = client.post("/words/add",
                       json={"language_code": "fr", "word": "décollage",
                             "definitions": [
                                 {"part_of_speech": "n.", "meaning": "起飞", "example": "e1", "note": "n1"},
                                 {"part_of_speech": "v.", "meaning": "取下"}]})
    assert resp.status_code == 200
    data = resp.get_json()
    assert data["ok"] and data["word"] == "décollage"
    # 隐式建了 fr 词表，词 + 2 条释义
    with bypass_engine.connect() as c:
        lid = c.execute(text("SELECT id FROM word_lists WHERE user_id=:u AND language_code='fr'"), {"u": uid}).scalar()
        wdef = c.execute(text("SELECT id,word FROM words WHERE list_id=:l"), {"l": lid}).first()
        defs = c.execute(text("SELECT part_of_speech FROM definitions WHERE word_id=:w ORDER BY id"), {"w": wdef[0]}).all()
    assert lid is not None
    assert wdef[1] == "décollage"
    assert [d[0] for d in defs] == ["n.", "v."]


def test_manual_add_supports_chinese_current_language(app, client, bypass_engine):
    _auth(client, app)
    client.post("/language/switch", data={
        "language_code": "zh",
        "csrf_token": _csrf(client),
    })

    page = client.get("/words/add").get_data(as_text=True)

    assert "中文" in page
    assert ('selected value="zh"' in page) or ('value="zh" selected' in page)


def test_manual_add_page_does_not_duplicate_collection_entry_points(app, client, bypass_engine):
    _auth(client, app)

    page = client.get("/words/add").get_data(as_text=True)

    assert "其它收词方式" not in page
    assert "随手加一个" not in page


def test_add_center_rejects_bad_payload(app, client, bypass_engine):
    """缺词/缺释义/非法语言 → 400。"""
    _auth(client, app)
    csrf = _csrf(client)
    headers = {"X-CSRFToken": csrf}
    for body in [{"language_code": "fr", "word": "", "definitions": [{"meaning": "m"}]},
                 {"language_code": "fr", "word": "x", "definitions": []},
                 {"language_code": "qq", "word": "x", "definitions": [{"meaning": "m"}]}]:
        r = client.post("/words/add", json=body, headers=headers)
        assert r.status_code == 400, body


def test_add_center_ai_fill(app, client, bypass_engine):
    """POST /words/ai-fill 返回 definitions。"""
    _auth(client, app)
    _install_llm()
    r = client.post("/words/ai-fill", json={"word": "décollage", "language_code": "fr"},
                    headers={"X-CSRFToken": _csrf(client)})
    assert r.status_code == 200
    data = r.get_json()
    assert "definitions" in data
    assert data["definitions"][0]["meaning"] == "起飞"


def test_add_center_generate_example_and_note(app, client, bypass_engine):
    """生成例句 / 生成笔记端点各跑通一次。"""
    _auth(client, app)
    holder = {"content": "例句结果"}
    _install_llm(holder)
    csrf = _csrf(client)
    r1 = client.post("/words/generate-example",
                     json={"word": "x", "part_of_speech": "n.", "meaning": "m", "language_code": "fr"},
                     headers={"X-CSRFToken": csrf})
    assert r1.status_code == 200 and r1.get_json()["example"] == "例句结果"
    holder["content"] = "笔记结果"
    r2 = client.post("/words/generate-note",
                     json={"word": "x", "part_of_speech": "n.", "meaning": "m", "language_code": "fr"},
                     headers={"X-CSRFToken": csrf})
    assert r2.status_code == 200 and r2.get_json()["note"] == "笔记结果"


def test_add_center_ai_fail_closed(app, client, bypass_engine):
    """AI 全挂：ai-fill 返回 error，generate-example/note 返回 503。"""
    from app.services import llm
    _auth(client, app)
    llm.set_registry({"general": [], "extract": []})     # 空链 = 全挂
    llm.reset_breaker()
    csrf = _csrf(client)
    h = {"X-CSRFToken": csrf}

    assert "error" in client.post("/words/ai-fill", json={"word": "x", "language_code": "fr"}, headers=h).get_json()
    assert client.post("/words/generate-example",
                       json={"word": "x", "meaning": "m", "language_code": "fr"}, headers=h).status_code == 503
    assert client.post("/words/generate-note",
                       json={"word": "x", "meaning": "m", "language_code": "fr"}, headers=h).status_code == 503
    llm.set_registry(None)


def test_add_center_implicit_list_reuses_existing(app, client, bypass_engine):
    """同语言加两个词复用同一隐式词表，并把该语言收敛进在学集合。"""
    uid = _auth(client, app)
    for w in ["w1", "w2"]:
        client.post("/words/add", json={"language_code": "en", "word": w,
                                        "definitions": [{"meaning": "m"}]},
                    headers={"X-CSRFToken": _csrf(client)})
    client.get("/logout")
    with bypass_engine.connect() as c:
        n_list = c.execute(text("SELECT count(*) FROM word_lists WHERE user_id=:u AND language_code='en'"), {"u": uid}).scalar()
        n_word = c.execute(text("SELECT count(*) FROM words w JOIN word_lists wl ON w.list_id=wl.id WHERE wl.user_id=:u AND wl.language_code='en'"), {"u": uid}).scalar()
        ll, cur = c.execute(text(
            "SELECT learning_languages, current_language FROM users WHERE id=:u"),
            {"u": uid}).one()
    assert n_list == 1
    assert n_word == 2
    assert "en" in (ll or "")
    assert cur == "en"


def test_nav_groups_word_tools_under_library_menu(app, client, bypass_engine):
    """顶栏收敛：加词/导入归入词库菜单，不再作为普通用户顶层按钮。"""
    _auth(client, app)
    page = client.get("/").get_data(as_text=True)
    assert 'data-nav-menu="library"' in page
    assert 'class="nav-menu-link" role="menuitem" href="/words/add"' in page
    assert 'class="nav-menu-link" role="menuitem" href="/intake/import"' in page
    assert 'class="nav-menu-link" role="menuitem" href="/intake/extract"' in page
    assert '<a class="nav-link" href="/words/add"' not in page
    assert '<a class="nav-link" href="/intake/quick-add"' not in page


def test_nav_groups_account_tools_under_my_menu(app, client, bypass_engine):
    """统计/设置/退出属于「我的」，避免普通用户顶栏变成后台工具条。"""
    _auth(client, app)
    page = client.get("/").get_data(as_text=True)
    assert 'data-nav-menu="account"' in page
    assert 'class="nav-menu-link" role="menuitem" href="/stats"' in page
    assert 'class="nav-menu-link" role="menuitem" href="/settings"' in page
    assert 'class="nav-menu-link" role="menuitem" href="/logout"' in page
    assert '<a class="nav-link" href="/stats"' not in page
    assert '<a class="nav-link" href="/settings"' not in page
    assert '<a class="nav-link" href="/logout"' not in page
