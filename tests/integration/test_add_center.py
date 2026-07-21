"""ui-rescope step3：手动加词——手工 JSON 多词义 + AI 三端点 + 隐式建表闭环。"""
import json
from concurrent.futures import ThreadPoolExecutor
from threading import Barrier

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


def test_vocabulary_and_manual_add_render_english(app, client, bypass_engine):
    uid = _auth(client, app)
    client.post("/settings", data={"languages": ["fr"]})
    response = client.post("/words/add", json={
        "language_code": "fr",
        "word": "retrouver",
        "definitions": [{"part_of_speech": "v.", "meaning": "to find again"}],
    })
    word_id = response.get_json()["word_id"]
    client.post("/ui-language", data={"ui_locale": "en", "next": "/words"})

    vocabulary = client.get("/words").get_data(as_text=True)
    assert '<html lang="en">' in vocabulary
    assert "Vocabulary" in vocabulary
    assert "Current language: French" in vocabulary
    assert "Recently added" in vocabulary
    assert "Most forgotten" in vocabulary
    assert "Search words, definitions, examples, or notes" in vocabulary
    assert "Delete word" in vocabulary
    assert "生词本" not in vocabulary

    add_page = client.get("/words/add").get_data(as_text=True)
    assert "Add a word" in add_page
    assert "AI fill" in add_page
    assert "Add to vocabulary" in add_page
    assert "Generate example" in add_page
    assert '>French</option>' in add_page
    assert '>法语</option>' not in add_page

    edit_page = client.get(f"/words/{word_id}/edit").get_data(as_text=True)
    assert "Edit vocabulary entry" in edit_page
    assert "Part of speech" in edit_page
    assert "Save changes" in edit_page


def test_manual_add_json_errors_follow_interface_language(app, client):
    _auth(client, app)
    client.post("/ui-language", data={"ui_locale": "en", "next": "/words/add"})

    response = client.post("/words/add", json={
        "language_code": "",
        "word": "",
        "definitions": [],
    })
    assert response.status_code == 400
    assert response.get_json()["error"] == "Choose a language first"


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


def test_manual_add_is_idempotent_within_one_language(
        app, client, bypass_engine):
    uid = _auth(client, app)
    first = client.post("/words/add", json={
        "language_code": "fr",
        "word": "Maison",
        "definitions": [{"part_of_speech": "n.", "meaning": "房子"}],
    })
    first_id = first.get_json()["word_id"]
    with bypass_engine.begin() as conn:
        conn.execute(text("""
            UPDATE words SET reps = 7, lapses = 3 WHERE id = :word_id
        """), {"word_id": first_id})

    repeated = client.post("/words/add", json={
        "language_code": "fr",
        "word": " maison ",
        "definitions": [{"part_of_speech": "n.", "meaning": "覆盖释义"}],
    })

    assert repeated.status_code == 200
    assert repeated.get_json()["word_id"] == first_id
    with bypass_engine.connect() as conn:
        row = conn.execute(text("""
            SELECT w.word, w.reps, w.lapses, count(d.id), min(d.meaning)
            FROM words w
            LEFT JOIN definitions d ON d.word_id = w.id
            JOIN word_lists wl ON wl.id = w.list_id
            WHERE wl.user_id = :user_id AND wl.language_code = 'fr'
            GROUP BY w.id
        """), {"user_id": uid}).one()
    assert row.word == "Maison"
    assert (row.reps, row.lapses) == (7, 3)
    assert row.count == 1
    assert row.min == "房子"


def test_same_surface_remains_independent_across_languages(
        app, client):
    _auth(client, app)
    french = client.post("/words/add", json={
        "language_code": "fr", "word": "menu",
        "definitions": [{"meaning": "菜单"}],
    }).get_json()["word_id"]
    english = client.post("/words/add", json={
        "language_code": "en", "word": "MENU",
        "definitions": [{"meaning": "菜单"}],
    }).get_json()["word_id"]

    assert french != english


def test_concurrent_manual_add_returns_one_word(
        app, client, bypass_engine):
    email = "concurrent-add@t.com"
    uid = provision_user(app, email, PW)
    login(client, email, PW)
    barrier = Barrier(2)

    def submit(meaning):
        thread_client = app.test_client()
        login(thread_client, "concurrent-add@t.com", PW)
        barrier.wait(timeout=5)
        response = thread_client.post("/words/add", json={
            "language_code": "fr",
            "word": " Concombre ",
            "definitions": [{"meaning": meaning}],
        })
        return response.status_code, response.get_json()

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(submit, ["黄瓜", "青瓜"]))

    assert [status for status, _ in results] == [200, 200]
    assert len({body["word_id"] for _, body in results}) == 1
    with bypass_engine.connect() as conn:
        rows = conn.execute(text("""
            SELECT w.id, w.word, count(d.id)
            FROM words w
            JOIN word_lists wl ON wl.id = w.list_id
            LEFT JOIN definitions d ON d.word_id = w.id
            WHERE wl.user_id = :user_id
              AND lower(btrim(w.word)) = 'concombre'
            GROUP BY w.id
        """), {"user_id": uid}).all()
    assert len(rows) == 1
    assert rows[0].word == "Concombre"
    assert rows[0].count == 1


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


def test_add_center_ai_calls_use_feedback_language(app, client, bypass_engine, monkeypatch):
    """AI 填充、例句和笔记应使用用户设定的解释语言。"""
    _auth(client, app)
    client.post("/settings", data={"languages": ["zh"], "feedback_language": "fr"})
    calls = []

    def fake_fill(word, *, language, feedback_language):
        calls.append(("fill", language, feedback_language))
        return {"definitions": [{"part_of_speech": "n.", "meaning": "m"}]}

    def fake_example(word, part_of_speech, meaning, *, language, feedback_language):
        calls.append(("example", language, feedback_language))
        return "example"

    def fake_note(word, part_of_speech, meaning, *, language, feedback_language):
        calls.append(("note", language, feedback_language))
        return "note"

    monkeypatch.setattr("app.blueprints.words.routes.llm_svc.generate_full_word_info", fake_fill)
    monkeypatch.setattr("app.blueprints.words.routes.llm_svc.generate_example", fake_example)
    monkeypatch.setattr("app.blueprints.words.routes.llm_svc.generate_note", fake_note)
    csrf = _csrf(client)
    headers = {"X-CSRFToken": csrf}

    assert client.post("/words/ai-fill", json={"word": "学习", "language_code": "zh"}, headers=headers).status_code == 200
    assert client.post("/words/generate-example", json={
        "word": "学习", "part_of_speech": "n.", "meaning": "apprendre", "language_code": "zh"},
        headers=headers).status_code == 200
    assert client.post("/words/generate-note", json={
        "word": "学习", "part_of_speech": "n.", "meaning": "apprendre", "language_code": "zh"},
        headers=headers).status_code == 200

    assert calls == [
        ("fill", "中文", "法语"),
        ("example", "中文", "法语"),
        ("note", "中文", "法语"),
    ]


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


def test_nav_promotes_writing_and_partners_to_primary_domains(
    app, client, bypass_engine,
):
    _auth(client, app)
    page = client.get("/").get_data(as_text=True)

    assert 'data-nav-menu="writing"' in page
    assert 'aria-label="写一写菜单"' in page
    assert 'href="/write">造句</a>' in page
    assert 'href="/write/history">历史</a>' in page
    assert 'href="/square">广场</a>' in page
    assert 'data-nav-menu="partners"' in page
    assert 'aria-label="语言伙伴菜单"' in page
    assert 'href="/partners">伙伴列表</a>' in page
    assert 'href="/partner-packets">收到的反馈</a>' in page

    account_menu = page.split('aria-label="我的菜单"', 1)[1].split("</div>", 1)[0]
    assert 'href="/partners"' not in account_menu
    assert 'href="/partner-packets"' not in account_menu
    assert page.count("nav-mobile-icon") == 5


def test_writing_domain_pages_share_equal_section_navigation(
    app, client, bypass_engine,
):
    _auth(client, app)

    for path, active_label in [
        ("/write", "造句"),
        ("/write/history", "历史"),
        ("/square", "广场"),
    ]:
        page = client.get(path).get_data(as_text=True)
        assert 'class="write-section-nav"' in page
        assert page.count("write-section-link") == 3
        assert (
            f'class="write-section-link active"' in page
            and f'aria-current="page">{active_label}</a>' in page
        )
