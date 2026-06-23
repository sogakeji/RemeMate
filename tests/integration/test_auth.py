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
    # 第 6 次即便密码正确也被锁定
    resp = client.post("/login", data={"email": "lock@t.com", "password": PW})
    assert resp.status_code == 200
    assert "账号已锁定" in resp.get_data(as_text=True)


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
