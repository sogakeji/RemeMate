"""SessionPad B1: private language-partner records."""
import re
from urllib.parse import urlsplit

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


def _create_invite(client, partner_id, recipient_email):
    response = client.post(
        f"/partners/{partner_id}/invite",
        data={
            "recipient_email": recipient_email,
            "csrf_token": _csrf(client, f"/partners/{partner_id}"),
        },
    )
    assert response.status_code == 200
    body = response.get_data(as_text=True)
    match = re.search(r'data-invite-url="([^"]+)"', body)
    assert match
    return urlsplit(match.group(1).replace("&amp;", "&")).path


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


def test_partner_invite_requires_login_and_recipient_acceptance(
    app, client, bypass_engine,
):
    owner_id = provision_user(
        app, "partner-invite-owner@t.com", PW, name="Alice",
    )
    recipient_id = provision_user(
        app, "partner-invite-recipient@t.com", PW, name="Pierre",
    )
    provision_user(app, "partner-invite-wrong@t.com", PW, name="Wrong")
    login(client, "partner-invite-owner@t.com", PW)
    partner_id = _create_partner(client)
    recap_response = client.post(f"/partners/{partner_id}/recaps", data={
        "session_date": "2026-07-10",
        "title": "Private history",
        "csrf_token": _csrf(client, f"/partners/{partner_id}/recaps/new"),
    })
    assert recap_response.status_code == 302
    recap_id = int(recap_response.headers["Location"].rstrip("/").rsplit("/", 1)[-1])
    invite_path = _create_invite(
        client, partner_id, "partner-invite-recipient@t.com",
    )

    client.get("/logout")
    login_redirect = client.get(invite_path)
    assert login_redirect.status_code == 302
    assert "/login?next=" in login_redirect.headers["Location"]

    login(client, "partner-invite-wrong@t.com", PW)
    assert client.get(invite_path).status_code == 410
    client.get("/logout")

    login_response = client.post(
        f"/login?next={invite_path}",
        data={"email": "partner-invite-recipient@t.com", "password": PW},
    )
    assert login_response.status_code == 302
    assert login_response.headers["Location"] == invite_path

    preview = client.get(invite_path)
    body = preview.get_data(as_text=True)
    assert preview.status_code == 200
    assert "Alice" in body
    assert "确认绑定" in body

    accepted = client.post(invite_path, data={
        "csrf_token": _csrf(client, invite_path),
    })
    assert accepted.status_code == 200
    assert "已建立语言伙伴关系" in accepted.get_data(as_text=True)
    assert client.get(f"/partners/{partner_id}").status_code == 404
    assert client.get(
        f"/partners/{partner_id}/recaps/{recap_id}"
    ).status_code == 404

    with bypass_engine.connect() as conn:
        linked_user_id = conn.execute(text(
            "SELECT linked_user_id FROM language_partners "
            "WHERE id = :partner_id AND user_id = :owner_id"
        ), {"partner_id": partner_id, "owner_id": owner_id}).scalar()
    assert linked_user_id == recipient_id

    client.get("/logout")
    login(client, "partner-invite-owner@t.com", PW)
    owner_page = client.get(f"/partners/{partner_id}").get_data(as_text=True)
    assert "已绑定账号" in owner_page
    assert "邀请绑定" not in owner_page


def test_claimed_partner_invite_cannot_be_taken_by_another_user(
    app, client,
):
    provision_user(app, "partner-claim-owner@t.com", PW, name="Owner")
    provision_user(app, "partner-claim-first@t.com", PW, name="First")
    provision_user(app, "partner-claim-second@t.com", PW, name="Second")
    login(client, "partner-claim-owner@t.com", PW)
    partner_id = _create_partner(client)
    invite_path = _create_invite(client, partner_id, "partner-claim-first@t.com")

    client.get("/logout")
    login(client, "partner-claim-first@t.com", PW)
    first = client.post(invite_path, data={
        "csrf_token": _csrf(client, invite_path),
    })
    assert first.status_code == 200

    client.get("/logout")
    login(client, "partner-claim-second@t.com", PW)
    assert client.get(invite_path).status_code == 410


def test_new_partner_invite_invalidates_previous_link(app, client):
    provision_user(app, "partner-reinvite-owner@t.com", PW, name="Owner")
    provision_user(app, "partner-reinvite-first@t.com", PW, name="First")
    provision_user(app, "partner-reinvite-second@t.com", PW, name="Second")
    login(client, "partner-reinvite-owner@t.com", PW)
    partner_id = _create_partner(client)
    first_path = _create_invite(
        client, partner_id, "partner-reinvite-first@t.com",
    )
    second_path = _create_invite(
        client, partner_id, "partner-reinvite-second@t.com",
    )

    client.get("/logout")
    login(client, "partner-reinvite-first@t.com", PW)
    assert client.get(first_path).status_code == 410
    client.get("/logout")
    login(client, "partner-reinvite-second@t.com", PW)
    assert client.get(second_path).status_code == 200


def test_owner_cannot_create_self_partner_invite(app, client):
    provision_user(app, "partner-self-invite@t.com", PW, name="Owner")
    login(client, "partner-self-invite@t.com", PW)
    partner_id = _create_partner(client)
    response = client.post(f"/partners/{partner_id}/invite", data={
        "recipient_email": "partner-self-invite@t.com",
        "csrf_token": _csrf(client, f"/partners/{partner_id}"),
    })
    assert response.status_code == 400
    assert "不能邀请自己的账号" in response.get_data(as_text=True)


def test_partner_link_constraints_reject_self_and_duplicate_links(
    bypass_engine,
):
    owner_id = make_user(bypass_engine, "partner-link-owner@t.com")
    recipient_id = make_user(bypass_engine, "partner-link-recipient@t.com")
    with bypass_engine.begin() as conn:
        first_id = conn.execute(text(
            "INSERT INTO language_partners("
            "user_id, display_name, linked_user_id, created_at, updated_at) "
            "VALUES (:owner, 'First', :recipient, now(), now()) RETURNING id"
        ), {"owner": owner_id, "recipient": recipient_id}).scalar()
        assert first_id

    with bypass_engine.connect() as conn:
        with pytest.raises(DBAPIError):
            conn.execute(text(
                "INSERT INTO language_partners("
                "user_id, display_name, linked_user_id, created_at, updated_at) "
                "VALUES (:owner, 'Duplicate', :recipient, now(), now())"
            ), {"owner": owner_id, "recipient": recipient_id})

    with bypass_engine.connect() as conn:
        with pytest.raises(DBAPIError):
            conn.execute(text(
                "INSERT INTO language_partners("
                "user_id, display_name, linked_user_id, created_at, updated_at) "
                "VALUES (:owner, 'Self', :owner, now(), now())"
            ), {"owner": owner_id})
