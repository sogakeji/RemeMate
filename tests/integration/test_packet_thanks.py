"""SessionPad B6: one-way, pressure-free packet thanks."""
import re

import pytest
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError

from tests.helpers import login, provision_user, set_uid


PW = "pw12345678"


def _csrf(client, path):
    page = client.get(path).get_data(as_text=True)
    match = re.search(r'name="csrf_token"[^>]*value="([^"]+)"', page)
    return match.group(1) if match else None


def _make_packet(bypass_engine, sender_id, recipient_id):
    with bypass_engine.begin() as conn:
        partner_id = conn.execute(text(
            "INSERT INTO language_partners("
            "user_id, linked_user_id, display_name, created_at, updated_at) "
            "VALUES (:sender, :recipient, 'Pierre', now(), now()) RETURNING id"
        ), {"sender": sender_id, "recipient": recipient_id}).scalar()
        recap_id = conn.execute(text(
            "INSERT INTO partner_recaps("
            "user_id, partner_id, session_date, title, created_at, updated_at) "
            "VALUES (:sender, :partner, '2026-07-11', 'Exchange', now(), now()) "
            "RETURNING id"
        ), {"sender": sender_id, "partner": partner_id}).scalar()
        packet_id = conn.execute(text(
            "INSERT INTO partner_packets("
            "sender_user_id, recipient_user_id, partner_id, recap_id, "
            "sender_display_name, recipient_display_name, recap_title, "
            "session_date, content_fingerprint, item_count, created_at) "
            "VALUES (:sender, :recipient, :partner, :recap, 'Alice', 'Pierre', "
            "'Exchange', '2026-07-11', :fingerprint, 1, now()) RETURNING id"
        ), {
            "sender": sender_id,
            "recipient": recipient_id,
            "partner": partner_id,
            "recap": recap_id,
            "fingerprint": f"{sender_id:064x}"[-64:],
        }).scalar()
        conn.execute(text(
            "INSERT INTO partner_packet_items(packet_id, kind, content, position) "
            "VALUES (:packet, 'expression', '谢谢你的反馈', 0)"
        ), {"packet": packet_id})
    return packet_id


def test_recipient_can_thank_once_and_sender_sees_it(
    app, client, bypass_engine,
):
    sender_id = provision_user(app, "thanks-sender@t.com", PW, name="Alice")
    recipient_id = provision_user(
        app, "thanks-recipient@t.com", PW, name="Pierre",
    )
    packet_id = _make_packet(bypass_engine, sender_id, recipient_id)
    packet_url = f"/partner-packets/{packet_id}"

    login(client, "thanks-recipient@t.com", PW)
    before = client.get(packet_url).get_data(as_text=True)
    assert "感谢" in before
    first = client.post(f"{packet_url}/thank", data={
        "csrf_token": _csrf(client, packet_url),
    })
    second = client.post(f"{packet_url}/thank", data={
        "csrf_token": _csrf(client, packet_url),
    })
    assert first.status_code == second.status_code == 302
    assert first.headers["Location"] == second.headers["Location"] == packet_url
    recipient_page = client.get(packet_url).get_data(as_text=True)
    assert "已感谢" in recipient_page
    assert "感谢对方" not in recipient_page

    with bypass_engine.connect() as conn:
        count = conn.execute(text(
            "SELECT count(*) FROM partner_packet_thanks WHERE packet_id = :packet"
        ), {"packet": packet_id}).scalar()
    assert count == 1

    client.get("/logout")
    login(client, "thanks-sender@t.com", PW)
    sender_page = client.get(packet_url).get_data(as_text=True)
    assert "对方已感谢" in sender_page
    assert "感谢对方" not in sender_page


def test_sender_and_stranger_cannot_thank_packet(
    app, client, bypass_engine,
):
    sender_id = provision_user(app, "thanks-owner@t.com", PW)
    recipient_id = provision_user(app, "thanks-target@t.com", PW)
    provision_user(app, "thanks-stranger@t.com", PW)
    packet_id = _make_packet(bypass_engine, sender_id, recipient_id)
    action = f"/partner-packets/{packet_id}/thank"

    login(client, "thanks-owner@t.com", PW)
    assert client.post(action, data={
        "csrf_token": _csrf(client, f"/partner-packets/{packet_id}"),
    }).status_code == 404
    client.get("/logout")
    login(client, "thanks-stranger@t.com", PW)
    assert client.post(action, data={
        "csrf_token": _csrf(client, "/partners"),
    }).status_code == 404

    with bypass_engine.connect() as conn:
        assert conn.execute(text(
            "SELECT count(*) FROM partner_packet_thanks"
        )).scalar() == 0


def test_packet_thank_rls_is_visible_to_pair_but_immutable(
    app, client, app_engine, bypass_engine,
):
    sender_id = provision_user(app, "thanks-rls-sender@t.com", PW)
    recipient_id = provision_user(app, "thanks-rls-recipient@t.com", PW)
    stranger_id = provision_user(app, "thanks-rls-stranger@t.com", PW)
    packet_id = _make_packet(bypass_engine, sender_id, recipient_id)
    login(client, "thanks-rls-recipient@t.com", PW)
    client.post(f"/partner-packets/{packet_id}/thank", data={
        "csrf_token": _csrf(client, f"/partner-packets/{packet_id}"),
    })

    for user_id, expected in (
        (sender_id, 1), (recipient_id, 1), (stranger_id, 0),
    ):
        with app_engine.connect() as conn:
            set_uid(conn, user_id)
            assert conn.execute(text(
                "SELECT count(*) FROM partner_packet_thanks"
            )).scalar() == expected

    with app_engine.connect() as conn:
        set_uid(conn, sender_id)
        assert conn.execute(text(
            "DELETE FROM partner_packet_thanks"
        )).rowcount == 0
    with app_engine.connect() as conn:
        set_uid(conn, recipient_id)
        assert conn.execute(text(
            "UPDATE partner_packet_thanks SET thanked_at = now()"
        )).rowcount == 0


def test_database_rejects_thank_from_non_recipient(bypass_engine, app):
    sender_id = provision_user(app, "thanks-fk-sender@t.com", PW)
    recipient_id = provision_user(app, "thanks-fk-recipient@t.com", PW)
    wrong_id = provision_user(app, "thanks-fk-wrong@t.com", PW)
    packet_id = _make_packet(bypass_engine, sender_id, recipient_id)

    with bypass_engine.connect() as conn:
        with pytest.raises(DBAPIError):
            conn.execute(text(
                "INSERT INTO partner_packet_thanks("
                "packet_id, recipient_user_id, thanked_at) "
                "VALUES (:packet, :wrong, now())"
            ), {"packet": packet_id, "wrong": wrong_id})

    with bypass_engine.begin() as conn:
        conn.execute(text(
            "INSERT INTO partner_packet_thanks("
            "packet_id, recipient_user_id, thanked_at) "
            "VALUES (:packet, :recipient, now())"
        ), {"packet": packet_id, "recipient": recipient_id})
