"""ui-rescope step4c：设置页语言选择 + 首页语言切换器 + 未设语言空态。

修1后设置页改成「在学语言集合多选」（form field 名为 languages，多选），
不再用单选 language_code。首页语言切换器是 single 当前主攻，走 /language/switch。
"""
from sqlalchemy import text

from app.services import words as words_svc
from tests.helpers import provision_user, login

PW = "pw12345678"


def test_settings_page_shows_compact_language_preferences(app, client, bypass_engine):
    provision_user(app, "se1@t.com", PW)
    login(client, "se1@t.com", PW)
    page = client.get("/settings").get_data(as_text=True)
    assert "昵称" in page
    assert "登录密码" in page
    assert "正在学" in page
    assert "中文" in page
    assert "母语" in page
    assert "时区" in page
    assert "Bark 推送" in page
    assert 'data-settings-toggle="profile-panel"' in page
    assert 'data-settings-toggle="password-panel"' in page
    assert 'data-settings-toggle="learning-panel"' in page
    assert 'data-settings-toggle="feedback-panel"' in page
    assert 'data-settings-toggle="timezone-panel"' in page
    assert 'data-settings-toggle="bark-panel"' in page
    assert 'class="settings-panel" id="profile-panel"' in page
    assert 'class="settings-panel" id="password-panel"' in page
    assert 'class="settings-panel" id="learning-panel"' in page
    assert 'class="settings-panel" id="feedback-panel"' in page
    assert 'class="settings-panel" id="timezone-panel"' in page
    assert 'class="settings-panel" id="bark-panel"' in page
    assert 'formaction="/settings/account"' in page
    assert 'name="display_name"' in page
    assert 'name="current_password"' in page
    assert 'name="new_password"' in page
    assert 'name="confirm_password"' in page
    assert 'formaction="/settings/bark/test"' in page
    assert 'name="languages"' in page
    assert 'name="feedback_language"' in page
    assert 'name="timezone"' in page
    assert "Europe/Paris" in page
    assert 'name="bark_url"' in page
    assert 'name="notify_review_reminder"' in page
    assert 'name="notify_daily_summary"' in page
    assert 'name="notify_intake_done"' in page


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


def test_settings_save_supports_chinese_target_and_french_feedback(app, client, bypass_engine):
    uid = provision_user(app, "se2c@t.com", PW)
    login(client, "se2c@t.com", PW)
    client.post("/settings", data={"languages": ["zh"],
                                   "feedback_language": "fr",
                                   "csrf_token": _csrf(client, "/settings")})
    with bypass_engine.connect() as c:
        ll = c.execute(text("SELECT learning_languages FROM users WHERE id=:u"), {"u": uid}).scalar()
        cur = c.execute(text("SELECT current_language FROM users WHERE id=:u"), {"u": uid}).scalar()
        fb = c.execute(text("SELECT feedback_language FROM user_settings WHERE user_id=:u"), {"u": uid}).scalar()
        n = c.execute(text(
            "SELECT count(*) FROM word_lists WHERE user_id=:u AND language_code='zh'"),
            {"u": uid}).scalar()
    assert ll == "zh"
    assert cur == "zh"
    assert fb == "fr"
    assert n == 1


def test_settings_account_can_update_display_name(app, client, bypass_engine):
    uid = provision_user(app, "nickname@t.com", PW)
    login(client, "nickname@t.com", PW)
    r = client.post("/settings/account", data={
        "display_name": "New Nick",
        "csrf_token": _csrf(client, "/settings"),
    }, follow_redirects=True)
    assert "已保存账号设置" in r.get_data(as_text=True)
    with bypass_engine.connect() as c:
        name = c.execute(text(
            "SELECT display_name FROM users WHERE id=:u"),
            {"u": uid}).scalar()
    assert name == "New Nick"
    assert "New Nick" in client.get("/settings").get_data(as_text=True)


def test_settings_account_can_change_password(app, client, bypass_engine):
    provision_user(app, "changepw@t.com", PW)
    login(client, "changepw@t.com", PW)
    r = client.post("/settings/account", data={
        "display_name": "Tester",
        "current_password": PW,
        "new_password": "newpass123",
        "confirm_password": "newpass123",
        "csrf_token": _csrf(client, "/settings"),
    }, follow_redirects=True)
    assert "已保存账号设置" in r.get_data(as_text=True)

    client.get("/logout")
    old_login = client.post("/login", data={
        "email": "changepw@t.com",
        "password": PW,
    })
    assert old_login.status_code == 200
    assert "邮箱或密码错误" in old_login.get_data(as_text=True)
    new_login = client.post("/login", data={
        "email": "changepw@t.com",
        "password": "newpass123",
    })
    assert new_login.status_code == 302


def test_settings_account_rejects_wrong_current_password(app, client):
    provision_user(app, "badcurrent@t.com", PW)
    login(client, "badcurrent@t.com", PW)
    r = client.post("/settings/account", data={
        "display_name": "Tester",
        "current_password": "wrong-password",
        "new_password": "newpass123",
        "confirm_password": "newpass123",
        "csrf_token": _csrf(client, "/settings"),
    }, follow_redirects=True)
    assert "当前密码不正确" in r.get_data(as_text=True)

    client.get("/logout")
    assert client.post("/login", data={
        "email": "badcurrent@t.com",
        "password": PW,
    }).status_code == 302


def test_settings_save_timezone_and_recomputes_quota_reset(app, client, bypass_engine):
    uid = provision_user(app, "timezone@t.com", PW)
    login(client, "timezone@t.com", PW)
    with bypass_engine.connect() as c:
        before = c.execute(text(
            "SELECT quota_reset_at FROM user_quota WHERE user_id=:u"),
            {"u": uid}).scalar()
    client.post("/settings", data={
        "languages": ["fr"],
        "feedback_language": "zh",
        "timezone": "Europe/Paris",
        "csrf_token": _csrf(client, "/settings"),
    })
    with bypass_engine.connect() as c:
        row = c.execute(text(
            "SELECT timezone FROM users WHERE id=:u"),
            {"u": uid}).fetchone()
        after = c.execute(text(
            "SELECT quota_reset_at FROM user_quota WHERE user_id=:u"),
            {"u": uid}).scalar()
    assert row == ("Europe/Paris",)
    assert after is not None
    assert after != before


def test_settings_rejects_unknown_timezone(app, client, bypass_engine):
    uid = provision_user(app, "badtimezone@t.com", PW)
    login(client, "badtimezone@t.com", PW)
    r = client.post("/settings", data={
        "languages": ["fr"],
        "feedback_language": "zh",
        "timezone": "Mars/Olympus",
        "csrf_token": _csrf(client, "/settings"),
    }, follow_redirects=True)
    assert "设置内容不正确" in r.get_data(as_text=True)
    with bypass_engine.connect() as c:
        timezone = c.execute(text(
            "SELECT timezone FROM users WHERE id=:u"),
            {"u": uid}).scalar()
    assert timezone == "Asia/Shanghai"


def test_settings_save_bark_notification_preferences(app, client, bypass_engine):
    uid = provision_user(app, "bark@t.com", PW)
    login(client, "bark@t.com", PW)
    client.post("/settings", data={
        "languages": ["fr"],
        "feedback_language": "zh",
        "bark_url": "https://api.day.app/test-key",
        "notify_review_reminder": "on",
        "notify_intake_done": "on",
        "csrf_token": _csrf(client, "/settings"),
    })
    with bypass_engine.connect() as c:
        row = c.execute(text(
            "SELECT bark_url, notify_review_reminder, notify_daily_summary, "
            "notify_intake_done FROM user_settings WHERE user_id=:u"),
            {"u": uid}).fetchone()
    assert row == ("https://api.day.app/test-key", True, False, True)


def test_settings_rejects_private_bark_url(app, client, bypass_engine):
    uid = provision_user(app, "bad-bark@t.com", PW)
    login(client, "bad-bark@t.com", PW)
    r = client.post("/settings", data={
        "languages": ["fr"],
        "feedback_language": "zh",
        "bark_url": "https://127.0.0.1/test-key",
        "notify_review_reminder": "on",
        "csrf_token": _csrf(client, "/settings"),
    }, follow_redirects=True)
    assert r.status_code == 200
    assert "设置内容不正确" in r.get_data(as_text=True)
    with bypass_engine.connect() as c:
        bark_url = c.execute(text(
            "SELECT bark_url FROM user_settings WHERE user_id=:u"),
            {"u": uid}).scalar()
    assert bark_url is None


def test_settings_bark_test_saves_and_sends(app, client, bypass_engine, monkeypatch):
    uid = provision_user(app, "bark-test@t.com", PW)
    login(client, "bark-test@t.com", PW)
    calls = []

    class Resp:
        status_code = 200

    monkeypatch.setattr(
        words_svc.socket,
        "getaddrinfo",
        lambda *args, **kwargs: [(None, None, None, None, ("43.155.109.24", 443))],
    )

    def fake_post(url, *, json, timeout, allow_redirects):
        calls.append({
            "url": url,
            "json": json,
            "timeout": timeout,
            "allow_redirects": allow_redirects,
        })
        return Resp()

    monkeypatch.setattr(words_svc.requests, "post", fake_post)
    r = client.post("/settings/bark/test", data={
        "languages": ["fr"],
        "feedback_language": "zh",
        "bark_url": "https://api.day.app/test-key",
        "notify_review_reminder": "on",
        "notify_daily_summary": "on",
        "csrf_token": _csrf(client, "/settings"),
    }, follow_redirects=True)
    assert "Bark 测试推送已发送" in r.get_data(as_text=True)
    assert calls == [{
        "url": "https://api.day.app/test-key",
        "json": {
            "title": "记搭 RemeMate",
            "body": "测试推送发送成功。",
            "group": "RemeMate",
        },
        "timeout": 5,
        "allow_redirects": False,
    }]
    with bypass_engine.connect() as c:
        row = c.execute(text(
            "SELECT bark_url, notify_review_reminder, notify_daily_summary, "
            "notify_intake_done FROM user_settings WHERE user_id=:u"),
            {"u": uid}).fetchone()
    assert row == ("https://api.day.app/test-key", True, True, False)


def test_settings_bark_test_rejects_private_url(app, client, bypass_engine, monkeypatch):
    uid = provision_user(app, "bark-private@t.com", PW)
    login(client, "bark-private@t.com", PW)

    def fail_post(*args, **kwargs):
        raise AssertionError("Bark request should not be sent")

    monkeypatch.setattr(words_svc.requests, "post", fail_post)
    r = client.post("/settings/bark/test", data={
        "languages": ["fr"],
        "feedback_language": "zh",
        "bark_url": "https://127.0.0.1/test-key",
        "notify_review_reminder": "on",
        "csrf_token": _csrf(client, "/settings"),
    }, follow_redirects=True)
    assert "Bark 地址不能指向本机或内网" in r.get_data(as_text=True)
    with bypass_engine.connect() as c:
        bark_url = c.execute(text(
            "SELECT bark_url FROM user_settings WHERE user_id=:u"),
            {"u": uid}).scalar()
    assert bark_url is None


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
