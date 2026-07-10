"""SessionPad B1: private language-partner records."""
import re

import pytest
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError

from tests.helpers import login, make_user, provision_user, set_uid


PW = "pw12345678"


def _csrf(client, path):
    page = client.get(path).get_data(as_text=True)
    match = re.search(r'name="csrf_token"[^>]*value="([^"]+)"', page)
    return match.group(1) if match else None


def _create_partner(client, name="Pierre"):
    response = client.post("/partners", data={
        "display_name": name,
        "native_language_code": "fr",
        "learning_language_code": "zh",
        "private_note": "下个月准备 HSK",
        "csrf_token": _csrf(client, "/partners/new"),
    })
    assert response.status_code == 302
    return int(response.headers["Location"].rstrip("/").rsplit("/", 1)[-1])


def test_user_can_create_and_view_private_partner(app, client):
    provision_user(app, "partner-owner@t.com", PW)
    login(client, "partner-owner@t.com", PW)

    page = client.get("/partners")
    assert page.status_code == 200
    assert "语言伙伴" in page.get_data(as_text=True)

    created = client.post("/partners", data={
        "display_name": "Pierre",
        "native_language_code": "fr",
        "learning_language_code": "zh",
        "private_note": "下个月准备 HSK",
        "csrf_token": _csrf(client, "/partners/new"),
    }, follow_redirects=True)

    body = created.get_data(as_text=True)
    assert created.status_code == 200
    assert "Pierre" in body
    assert "法语" in body
    assert "中文" in body
    assert "下个月准备 HSK" in body
    assert "未绑定账号" in body


def test_user_can_edit_partner(app, client):
    provision_user(app, "partner-edit@t.com", PW)
    login(client, "partner-edit@t.com", PW)
    partner_id = _create_partner(client)

    updated = client.post(f"/partners/{partner_id}", data={
        "display_name": "Pierre Dupont",
        "native_language_code": "fr",
        "learning_language_code": "en",
        "private_note": "下次聊法国电影",
        "csrf_token": _csrf(client, f"/partners/{partner_id}/edit"),
    }, follow_redirects=True)

    body = updated.get_data(as_text=True)
    assert updated.status_code == 200
    assert "Pierre Dupont" in body
    assert "英语" in body
    assert "下次聊法国电影" in body
    assert "下个月准备 HSK" not in body


def test_other_user_cannot_see_or_update_partner(app, client):
    provision_user(app, "partner-a@t.com", PW)
    provision_user(app, "partner-b@t.com", PW)
    login(client, "partner-a@t.com", PW)
    partner_id = _create_partner(client, "Only A Can See")
    client.get("/logout")
    login(client, "partner-b@t.com", PW)

    assert "Only A Can See" not in client.get("/partners").get_data(as_text=True)
    assert client.get(f"/partners/{partner_id}").status_code == 404
    assert client.get(f"/partners/{partner_id}/edit").status_code == 404
    changed = client.post(f"/partners/{partner_id}", data={
        "display_name": "Stolen",
        "csrf_token": _csrf(client, "/partners/new"),
    })
    assert changed.status_code == 404


def test_invalid_partner_form_preserves_edit_context(app, client):
    provision_user(app, "partner-invalid@t.com", PW)
    login(client, "partner-invalid@t.com", PW)
    partner_id = _create_partner(client)

    response = client.post(f"/partners/{partner_id}", data={
        "display_name": "",
        "native_language_code": "fr",
        "learning_language_code": "zh",
        "private_note": "draft",
        "csrf_token": _csrf(client, f"/partners/{partner_id}/edit"),
    })

    body = response.get_data(as_text=True)
    assert response.status_code == 400
    assert "编辑伙伴" in body
    assert f'action="/partners/{partner_id}"' in body
    assert "伙伴昵称需为 1-100 个字符" in body


def test_language_partner_rls_blocks_cross_user_rows(app_engine, bypass_engine):
    user_a = make_user(bypass_engine, "partner-rls-a@t.com")
    user_b = make_user(bypass_engine, "partner-rls-b@t.com")
    with bypass_engine.begin() as conn:
        conn.execute(text(
            "INSERT INTO language_partners(user_id, display_name, created_at, updated_at) "
            "VALUES (:user_id, 'Private Partner', now(), now())"
        ), {"user_id": user_a})

    with app_engine.connect() as conn:
        set_uid(conn, user_b)
        assert conn.execute(text(
            "SELECT count(*) FROM language_partners"
        )).scalar() == 0
        with pytest.raises(DBAPIError):
            conn.execute(text(
                "INSERT INTO language_partners(user_id, display_name, created_at, updated_at) "
                "VALUES (:user_id, 'Cross-owner', now(), now())"
            ), {"user_id": user_a})


def test_language_partner_rejects_unknown_language(bypass_engine):
    user_id = make_user(bypass_engine, "partner-language@t.com")
    with bypass_engine.connect() as conn:
        with pytest.raises(DBAPIError):
            conn.execute(text(
                "INSERT INTO language_partners("
                "user_id, display_name, native_language_code, created_at, updated_at) "
                "VALUES (:user_id, 'Invalid', 'xx', now(), now())"
            ), {"user_id": user_id})
