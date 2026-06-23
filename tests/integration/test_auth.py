"""登录安全：成功 / 无枚举 / 锁定 / 停用 / 登出 / @login_required / next 校验。"""
from tests.helpers import provision_user

PW = "pw12345678"


def test_login_success_redirects_to_index(app, client):
    provision_user(app, "ok@t.com", PW)
    resp = client.post("/login", data={"email": "ok@t.com", "password": PW})
    assert resp.status_code == 302
    assert resp.headers["Location"].endswith("/")


def test_wrong_password_and_unknown_user_same_message(app, client):
    provision_user(app, "real@t.com", PW)
    r_wrong = client.post("/login", data={"email": "real@t.com", "password": "bad"})
    r_unknown = client.post("/login", data={"email": "nobody@t.com", "password": "bad"})
    # 都是 200 重渲染登录页，且提示一致（防用户枚举）
    assert r_wrong.status_code == 200 and r_unknown.status_code == 200
    assert "邮箱或密码错误" in r_wrong.get_data(as_text=True)
    assert "邮箱或密码错误" in r_unknown.get_data(as_text=True)


def test_lockout_after_five_failures(app, client):
    provision_user(app, "lock@t.com", PW)
    for _ in range(5):
        client.post("/login", data={"email": "lock@t.com", "password": "bad"})
    # 第 6 次即便密码正确也被拒（锁定中），且回通用消息（不泄露锁定状态）
    resp = client.post("/login", data={"email": "lock@t.com", "password": PW})
    assert resp.status_code == 200                       # 未登录成功（非 302）
    assert "邮箱或密码错误" in resp.get_data(as_text=True)
    assert "账号已锁定" not in resp.get_data(as_text=True)


def test_inactive_user_cannot_login(app, client):
    provision_user(app, "off@t.com", PW)
    with app.app_context():
        from app.services import provisioning
        provisioning.deactivate_user("off@t.com")
    resp = client.post("/login", data={"email": "off@t.com", "password": PW})
    assert resp.status_code == 200
    assert "邮箱或密码错误" in resp.get_data(as_text=True)


def test_login_required_redirects_anonymous(client):
    resp = client.get("/")
    assert resp.status_code == 302
    assert "/login" in resp.headers["Location"]


def test_logout(app, client):
    provision_user(app, "lo@t.com", PW)
    client.post("/login", data={"email": "lo@t.com", "password": PW})
    assert client.get("/").status_code == 200      # 已登录
    client.get("/logout")
    assert client.get("/").status_code == 302      # 登出后被拦


def test_open_redirect_blocked(app, client):
    provision_user(app, "nx@t.com", PW)
    resp = client.post("/login?next=http://evil.com/x",
                       data={"email": "nx@t.com", "password": PW})
    assert resp.status_code == 302
    # 外部 next 被拒，回落到首页
    assert resp.headers["Location"].endswith("/")


def test_safe_next_honored(app, client):
    provision_user(app, "sn@t.com", PW)
    resp = client.post("/login?next=/stats",
                       data={"email": "sn@t.com", "password": PW})
    assert resp.status_code == 302
    assert resp.headers["Location"].endswith("/stats")


def test_backslash_open_redirect_blocked(app, client):
    """M4：/\\evil.com 这类反斜杠绕过被拦，回落首页。"""
    provision_user(app, "bs@t.com", PW)
    resp = client.post("/login?next=/\\evil.com",
                       data={"email": "bs@t.com", "password": PW})
    assert resp.status_code == 302
    loc = resp.headers["Location"]
    assert "evil.com" not in loc
    assert loc.endswith("/")


def test_garbage_session_user_id_no_500(client):
    """M3：被篡改/脏的 user_id 不致每请求 500，按匿名处理。"""
    with client.session_transaction() as sess:
        sess["_user_id"] = "not-an-int"
    resp = client.get("/")
    assert resp.status_code == 302          # 重定向到登录，而非 500
    assert "/login" in resp.headers["Location"]


def test_email_case_insensitive_login(app, client):
    """M5：大写邮箱注册，小写也能登录。"""
    provision_user(app, "Mixed@T.Com", PW)
    resp = client.post("/login", data={"email": "mixed@t.com", "password": PW})
    assert resp.status_code == 302
    assert resp.headers["Location"].endswith("/")


def test_email_case_insensitive_no_dup(app):
    """M5：大小写不同的同一邮箱不能建两个账号。"""
    from app.services import provisioning
    with app.app_context():
        provisioning.create_user_with_defaults("Dup@T.com", "A")
        with __import__("pytest").raises(provisioning.UserExistsError):
            provisioning.create_user_with_defaults("dup@t.com", "B")
