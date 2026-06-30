"""ui-rescope step4c：设置页语言选择 + 首页语言切换器 + 未设语言空态。

修1后设置页改成「在学语言集合多选」（form field 名为 languages，多选），
不再用单选 language_code。首页语言切换器是 single 当前主攻，走 /language/switch。
"""
from sqlalchemy import text

from tests.helpers import provision_user, login

PW = "pw12345678"


def test_settings_page_shows_multi_checkboxes(app, client, bypass_engine):
    provision_user(app, "se1@t.com", PW)
    login(client, "se1@t.com", PW)
    page = client.get("/settings").get_data(as_text=True)
    assert "正在学的语言" in page
    # 多选 checkbox 表单字段名 languages（修1）
    assert 'name="languages"' in page
    assert 'type="checkbox"' in page


def test_settings_save_sets_learning_languages(app, client, bypass_engine):
    """修1：设置页保存多选 → learning_languages 集合 + 每语言建隐式词表 + current 收敛。"""
    uid = provision_user(app, "se2@t.com", PW)
    login(client, "se2@t.com", PW)
    client.post("/settings", data={"languages": ["fr", "en"],
                                   "csrf_token": _csrf(client, "/settings")})
    with bypass_engine.connect() as c:
        ll = c.execute(text("SELECT learning_languages FROM users WHERE id=:u"), {"u": uid}).scalar()
        cur = c.execute(text("SELECT current_language FROM users WHERE id=:u"), {"u": uid}).scalar()
        n = c.execute(text("SELECT count(*) FROM word_lists WHERE user_id=:u"), {"u": uid}).scalar()
    assert ll == "fr,en"
    assert cur == "fr"                      # 集合首个
    assert n == 2                            # fr + en 各一张隐式词表


def test_settings_narrow_to_single_retracts_current(app, client, bypass_engine):
    """修1用户原话场景：多选 fr/en/ja → 改单选 en → 集合剩 en，current 自动收成 en。"""
    uid = provision_user(app, "se2b@t.com", PW)
    login(client, "se2b@t.com", PW)
    csrf = _csrf(client, "/settings")
    client.post("/settings", data={"languages": ["fr", "en", "ja"], "csrf_token": csrf})
    client.post("/settings", data={"languages": ["en"], "csrf_token": csrf})
    with bypass_engine.connect() as c:
        ll = c.execute(text("SELECT learning_languages FROM users WHERE id=:u"), {"u": uid}).scalar()
        cur = c.execute(text("SELECT current_language FROM users WHERE id=:u"), {"u": uid}).scalar()
    assert ll == "en"
    assert cur == "en"                       # fr 删后 current 从 fr 收成 en（集合首个）


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
        ll = c.execute(text("SELECT learning_languages FROM users WHERE id=:u"), {"u": uid}).scalar()
    assert cur == "en"
    # 首切 en 即默认「在学」：en 进集合
    assert "en" in (ll or "")
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