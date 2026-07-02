"""管理员闭测运营页：仅管理员可访问，可创建邀请账号。"""
from sqlalchemy import text

from tests.helpers import login, provision_user

PW = "pw12345678"


def test_admin_nav_only_visible_to_admin(app, client):
    provision_user(app, "user@t.com", PW)
    login(client, "user@t.com", PW)
    assert 'href="/admin/"' not in client.get("/").get_data(as_text=True)

    client.get("/logout")
    provision_user(app, "admin@t.com", PW, admin=True)
    login(client, "admin@t.com", PW)
    assert 'href="/admin/"' in client.get("/").get_data(as_text=True)


def test_admin_page_requires_admin(app, client):
    assert client.get("/admin/").status_code == 302
    provision_user(app, "plain@t.com", PW)
    login(client, "plain@t.com", PW)
    assert client.get("/admin/").status_code == 403


def test_admin_can_create_invited_user(app, client, bypass_engine):
    provision_user(app, "owner@t.com", PW, admin=True)
    login(client, "owner@t.com", PW)

    resp = client.post("/admin/", data={
        "email": "friend@t.com",
        "name": "Friend",
        "password": "Friend123456",
    })
    page = resp.get_data(as_text=True)
    assert resp.status_code == 200
    assert "账号已创建" in page
    assert "friend@t.com" in page
    assert "Friend123456" in page

    with bypass_engine.connect() as c:
        row = c.execute(text(
            "SELECT u.current_language, u.learning_languages, s.feedback_language "
            "FROM users u JOIN user_settings s ON s.user_id=u.id "
            "WHERE u.email='friend@t.com'"
        )).one()
        word_list_count = c.execute(text(
            "SELECT count(*) FROM word_lists wl JOIN users u ON u.id=wl.user_id "
            "WHERE u.email='friend@t.com'"
        )).scalar()
    assert row == (None, None, "zh")
    assert word_list_count == 0

    client.get("/logout")
    assert login(client, "friend@t.com", "Friend123456").status_code == 302


def test_admin_create_duplicate_shows_error(app, client):
    provision_user(app, "owner2@t.com", PW, admin=True)
    provision_user(app, "dup@t.com", PW)
    login(client, "owner2@t.com", PW)

    resp = client.post("/admin/", data={
        "email": "dup@t.com",
        "name": "Dup",
    }, follow_redirects=True)
    assert resp.status_code == 200
    assert "邮箱已存在" in resp.get_data(as_text=True)


def test_admin_create_invalid_email_shows_error(app, client, bypass_engine):
    provision_user(app, "owner3@t.com", PW, admin=True)
    login(client, "owner3@t.com", PW)

    resp = client.post("/admin/", data={
        "email": "not-an-email",
        "name": "Bad",
    }, follow_redirects=True)
    page = resp.get_data(as_text=True)
    assert resp.status_code == 200
    assert "邮箱格式不正确" in page
    with bypass_engine.connect() as c:
        count = c.execute(text(
            "SELECT count(*) FROM users WHERE email='not-an-email'"
        )).scalar()
    assert count == 0
