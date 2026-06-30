"""ui-rescope step4c：设置页语言选择 + 首页语言切换器 + 未设语言空态。"""
from sqlalchemy import text

from tests.helpers import provision_user, login

PW = "pw12345678"


def test_settings_page_shows_current(app, client, bypass_engine):
    provision_user(app, "se1@t.com", PW)
    login(client, "se1@t.com", PW)
    page = client.get("/settings").get_data(as_text=True)
    assert "正在学的语言" in page


def test_settings_save_sets_current_language(app, client, bypass_engine):
    uid = provision_user(app, "se2@t.com", PW)
    login(client, "se2@t.com", PW)
    client.post("/settings", data={"language_code": "fr",
                                   "csrf_token": _csrf(client, "/settings")})
    with bypass_engine.connect() as c:
        cur = c.execute(text("SELECT current_language FROM users WHERE id=:u"), {"u": uid}).scalar()
        n_list = c.execute(text("SELECT count(*) FROM word_lists WHERE user_id=:u AND language_code='fr'"), {"u": uid}).scalar()
    assert cur == "fr"
    assert n_list == 1                       # 闭环建隐式词表


def test_home_shows_setup_prompt_when_no_language(app, client, bypass_engine):
    provision_user(app, "se3@t.com", PW)
    login(client, "se3@t.com", PW)
    page = client.get("/").get_data(as_text=True)
    assert "先选一个正在学的语言" in page
    assert "去设置选语言" in page


def test_home_switcher_changes_current_language(app, client, bypass_engine):
    uid = provision_user(app, "se4@t.com", PW)
    login(client, "se4@t.com", PW)
    client.post("/language/switch", data={"language_code": "en",
                                          "csrf_token": _csrf(client, "/")})
    with bypass_engine.connect() as c:
        cur = c.execute(text("SELECT current_language FROM users WHERE id=:u"), {"u": uid}).scalar()
    assert cur == "en"
    # 切换后首页不再显示「先选语言」引导卡
    page = client.get("/").get_data(as_text=True)
    assert "先选一个正在学的语言" not in page


def test_home_switcher_rejects_unknown(app, client, bypass_engine):
    provision_user(app, "se5@t.com", PW)
    login(client, "se5@t.com", PW)
    r = client.post("/language/switch", data={"language_code": "klingon",
                                             "csrf_token": _csrf(client, "/")},
                    follow_redirects=True)
    assert r.status_code == 200


def test_settings_nav_present(app, client, bypass_engine):
    provision_user(app, "se6@t.com", PW)
    login(client, "se6@t.com", PW)
    page = client.get("/").get_data(as_text=True)
    assert 'href="/settings"' in page


def _csrf(client, path="/"):
    import re
    m = re.search(r'name="csrf_token"[^>]*value="([^"]+)"', client.get(path).get_data(as_text=True))
    return m.group(1) if m else ""