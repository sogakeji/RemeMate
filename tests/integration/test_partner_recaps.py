"""SessionPad B2: private recap papers and their two columns."""
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
        "private_note": "这条私人备注不能进入复盘信纸",
        "csrf_token": _csrf(client, "/partners/new"),
    })
    assert response.status_code == 302
    return int(response.headers["Location"].rstrip("/").rsplit("/", 1)[-1])


def _create_recap(client, partner_id):
    response = client.post(f"/partners/{partner_id}/recaps", data={
        "session_date": "2026-07-10",
        "title": "第一次法中交换",
        "csrf_token": _csrf(client, f"/partners/{partner_id}/recaps/new"),
    })
    assert response.status_code == 302
    return int(response.headers["Location"].rstrip("/").rsplit("/", 1)[-1])


def test_user_can_create_recap_with_two_private_columns(app, client):
    provision_user(app, "recap-owner@t.com", PW)
    login(client, "recap-owner@t.com", PW)
    partner_id = _create_partner(client)

    detail = client.get(f"/partners/{partner_id}")
    assert f'/partners/{partner_id}/recaps/new' in detail.get_data(as_text=True)

    created = client.post(f"/partners/{partner_id}/recaps", data={
        "session_date": "2026-07-10",
        "title": "第一次法中交换",
        "csrf_token": _csrf(client, f"/partners/{partner_id}/recaps/new"),
    }, follow_redirects=True)

    body = created.get_data(as_text=True)
    assert created.status_code == 200
    assert "第一次法中交换" in body
    assert "2026-07-10" in body
    assert "帮自己记" in body
    assert "帮他记" in body
    assert "这条私人备注不能进入复盘信纸" not in body


def test_user_can_add_items_to_each_recap_column(app, client):
    provision_user(app, "recap-items@t.com", PW)
    login(client, "recap-items@t.com", PW)
    partner_id = _create_partner(client)
    recap_id = _create_recap(client, partner_id)
    recap_url = f"/partners/{partner_id}/recaps/{recap_id}"

    client.post(f"{recap_url}/items", data={
        "side": "for_me",
        "kind": "expression",
        "content": "avoir hâte de",
        "csrf_token": _csrf(client, recap_url),
    })
    response = client.post(f"{recap_url}/items", data={
        "side": "for_partner",
        "kind": "correction",
        "content": "我很同意 → 我很赞同",
        "csrf_token": _csrf(client, recap_url),
    }, follow_redirects=True)

    body = response.get_data(as_text=True)
    for_me = re.search(
        r'data-recap-column="for_me".*?</section>', body, re.S,
    ).group()
    for_partner = re.search(
        r'data-recap-column="for_partner".*?</section>', body, re.S,
    ).group()
    assert "avoir hâte de" in for_me
    assert "我很同意 → 我很赞同" not in for_me
    assert "我很同意 → 我很赞同" in for_partner
    assert "avoir hâte de" not in for_partner


def test_other_user_cannot_read_or_write_recap(app, client):
    provision_user(app, "recap-a@t.com", PW)
    provision_user(app, "recap-b@t.com", PW)
    login(client, "recap-a@t.com", PW)
    partner_id = _create_partner(client)
    recap_id = _create_recap(client, partner_id)
    recap_url = f"/partners/{partner_id}/recaps/{recap_id}"
    client.get("/logout")
    login(client, "recap-b@t.com", PW)

    assert client.get(recap_url).status_code == 404
    response = client.post(f"{recap_url}/items", data={
        "side": "for_partner",
        "kind": "expression",
        "content": "should stay private",
        "csrf_token": _csrf(client, "/partners/new"),
    })
    assert response.status_code == 404


def test_correction_cannot_be_saved_in_for_me_column(app, client):
    provision_user(app, "recap-kind@t.com", PW)
    login(client, "recap-kind@t.com", PW)
    partner_id = _create_partner(client)
    recap_id = _create_recap(client, partner_id)
    recap_url = f"/partners/{partner_id}/recaps/{recap_id}"

    response = client.post(f"{recap_url}/items", data={
        "side": "for_me",
        "kind": "correction",
        "content": "不应保存",
        "csrf_token": _csrf(client, recap_url),
    }, follow_redirects=True)

    body = response.get_data(as_text=True)
    assert "记录类型不正确" in body
    assert "不应保存" not in body


def test_private_partner_note_can_only_be_saved_for_me(app, client):
    provision_user(app, "recap-private-note@t.com", PW)
    login(client, "recap-private-note@t.com", PW)
    partner_id = _create_partner(client)
    recap_id = _create_recap(client, partner_id)
    recap_url = f"/partners/{partner_id}/recaps/{recap_id}"

    saved = client.post(f"{recap_url}/items", data={
        "side": "for_me",
        "kind": "private_note",
        "content": "Pierre 下个月准备 HSK",
        "csrf_token": _csrf(client, recap_url),
    }, follow_redirects=True)
    assert "Pierre 下个月准备 HSK" in saved.get_data(as_text=True)

    rejected = client.post(f"{recap_url}/items", data={
        "side": "for_partner",
        "kind": "private_note",
        "content": "不应出现在帮他记",
        "csrf_token": _csrf(client, recap_url),
    }, follow_redirects=True)
    body = rejected.get_data(as_text=True)
    assert "记录类型不正确" in body
    assert "不应出现在帮他记" not in body


def test_recap_rls_hides_papers_and_items(app_engine, bypass_engine):
    user_a = make_user(bypass_engine, "recap-rls-a@t.com")
    user_b = make_user(bypass_engine, "recap-rls-b@t.com")
    with bypass_engine.begin() as conn:
        partner_id = conn.execute(text(
            "INSERT INTO language_partners("
            "user_id, display_name, created_at, updated_at) "
            "VALUES (:user_id, 'Private', now(), now()) RETURNING id"
        ), {"user_id": user_a}).scalar()
        recap_id = conn.execute(text(
            "INSERT INTO partner_recaps("
            "user_id, partner_id, session_date, created_at, updated_at) "
            "VALUES (:user_id, :partner_id, '2026-07-10', now(), now()) "
            "RETURNING id"
        ), {"user_id": user_a, "partner_id": partner_id}).scalar()
        conn.execute(text(
            "INSERT INTO partner_recap_items("
            "user_id, recap_id, side, kind, content, created_at, updated_at) "
            "VALUES (:user_id, :recap_id, 'for_me', 'expression', "
            "'private', now(), now())"
        ), {"user_id": user_a, "recap_id": recap_id})

    with app_engine.connect() as conn:
        set_uid(conn, user_b)
        assert conn.execute(text(
            "SELECT count(*) FROM partner_recaps"
        )).scalar() == 0
        assert conn.execute(text(
            "SELECT count(*) FROM partner_recap_items"
        )).scalar() == 0


def test_recap_item_database_rejects_correction_for_me(bypass_engine):
    user_id = make_user(bypass_engine, "recap-check@t.com")
    with bypass_engine.begin() as conn:
        partner_id = conn.execute(text(
            "INSERT INTO language_partners("
            "user_id, display_name, created_at, updated_at) "
            "VALUES (:user_id, 'Check', now(), now()) RETURNING id"
        ), {"user_id": user_id}).scalar()
        recap_id = conn.execute(text(
            "INSERT INTO partner_recaps("
            "user_id, partner_id, session_date, created_at, updated_at) "
            "VALUES (:user_id, :partner_id, '2026-07-10', now(), now()) "
            "RETURNING id"
        ), {"user_id": user_id, "partner_id": partner_id}).scalar()

    with bypass_engine.connect() as conn:
        with pytest.raises(DBAPIError):
            conn.execute(text(
                "INSERT INTO partner_recap_items("
                "user_id, recap_id, side, kind, content, created_at, updated_at) "
                "VALUES (:user_id, :recap_id, 'for_me', 'correction', "
                "'invalid', now(), now())"
            ), {"user_id": user_id, "recap_id": recap_id})


def test_user_can_edit_and_delete_own_recap_item(app, client):
    provision_user(app, "recap-revise@t.com", PW)
    login(client, "recap-revise@t.com", PW)
    partner_id = _create_partner(client)
    recap_id = _create_recap(client, partner_id)
    recap_url = f"/partners/{partner_id}/recaps/{recap_id}"
    added = client.post(f"{recap_url}/items", data={
        "side": "for_me",
        "kind": "expression",
        "content": "avoir hate de",
        "csrf_token": _csrf(client, recap_url),
    }, follow_redirects=True)
    match = re.search(r'data-recap-item-id="(\d+)"', added.get_data(as_text=True))
    item_id = int(match.group(1))

    edited = client.post(f"{recap_url}/items/{item_id}", data={
        "kind": "natural_phrase",
        "content": "avoir hâte de",
        "csrf_token": _csrf(client, recap_url),
    }, follow_redirects=True)
    edited_body = edited.get_data(as_text=True)
    assert "avoir hâte de" in edited_body
    assert "avoir hate de" not in edited_body

    deleted = client.post(f"{recap_url}/items/{item_id}/delete", data={
        "csrf_token": _csrf(client, recap_url),
    }, follow_redirects=True)
    assert "avoir hâte de" not in deleted.get_data(as_text=True)


def test_recap_editor_uses_side_and_kind_buttons_without_dropdown(app, client):
    provision_user(app, "recap-editor-ui@t.com", PW)
    login(client, "recap-editor-ui@t.com", PW)
    partner_id = _create_partner(client)
    recap_id = _create_recap(client, partner_id)

    body = client.get(
        f"/partners/{partner_id}/recaps/{recap_id}"
    ).get_data(as_text=True)

    assert 'data-recap-side-tab="for_me"' in body
    assert 'data-recap-side-tab="for_partner"' in body
    assert 'data-recap-kind-tab="expression"' in body
    assert 'data-recap-kind-tab="private_note"' in body
    assert 'data-recap-kind-tab="correction"' in body
    assert 'rows="8"' in body
    assert "<select" not in body
