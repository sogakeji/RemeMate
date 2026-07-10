"""SessionPad B5: immutable feedback packet delivery."""
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
        "private_note": "private relationship note",
        "csrf_token": _csrf(client, "/partners/new"),
    })
    assert response.status_code == 302
    return int(response.headers["Location"].rstrip("/").rsplit("/", 1)[-1])


def _create_recap(client, partner_id):
    response = client.post(f"/partners/{partner_id}/recaps", data={
        "session_date": "2026-07-10",
        "title": "French exchange",
        "csrf_token": _csrf(client, f"/partners/{partner_id}/recaps/new"),
    })
    assert response.status_code == 302
    return int(response.headers["Location"].rstrip("/").rsplit("/", 1)[-1])


def _add_item(client, recap_url, *, side, kind, content):
    response = client.post(f"{recap_url}/items", data={
        "side": side,
        "kind": kind,
        "content": content,
        "csrf_token": _csrf(client, recap_url),
    }, follow_redirects=True)
    panel = re.search(
        rf'data-recap-column="{side}".*?</section>',
        response.get_data(as_text=True),
        re.S,
    ).group()
    return int(re.findall(r'data-recap-item-id="(\d+)"', panel)[-1])


def _link_partner(bypass_engine, partner_id, recipient_id):
    with bypass_engine.begin() as conn:
        conn.execute(text(
            "UPDATE language_partners SET linked_user_id = :recipient_id, "
            "invite_token_hash = NULL WHERE id = :partner_id"
        ), {"recipient_id": recipient_id, "partner_id": partner_id})


def _send_packet(client, recap_url, item_ids):
    return client.post(f"{recap_url}/packets", data={
        "item_ids": [str(item_id) for item_id in item_ids],
        "csrf_token": _csrf(client, recap_url),
    })


def test_selected_partner_items_arrive_as_immutable_snapshot(
    app, client, bypass_engine,
):
    sender_id = provision_user(
        app, "packet-sender@t.com", PW, name="Alice",
    )
    recipient_id = provision_user(
        app, "packet-recipient@t.com", PW, name="Pierre",
    )
    login(client, "packet-sender@t.com", PW)
    partner_id = _create_partner(client)
    _link_partner(bypass_engine, partner_id, recipient_id)
    recap_id = _create_recap(client, partner_id)
    recap_url = f"/partners/{partner_id}/recaps/{recap_id}"
    correction_id = _add_item(
        client, recap_url, side="for_partner", kind="correction",
        content="我很同意 → 我很赞同",
    )
    phrase_id = _add_item(
        client, recap_url, side="for_partner", kind="natural_phrase",
        content="下次试试：我完全赞同你的看法。",
    )
    _add_item(
        client, recap_url, side="for_me", kind="private_note",
        content="Pierre 下个月准备 HSK",
    )
    recap_body = client.get(recap_url).get_data(as_text=True)
    for_me_panel = re.search(
        r'data-recap-column="for_me".*?</section>', recap_body, re.S,
    ).group()
    for_partner_panel = re.search(
        r'data-recap-column="for_partner".*?</section>', recap_body, re.S,
    ).group()
    assert 'form="send-packet-form"' not in for_me_panel
    assert for_partner_panel.count('form="send-packet-form"') == 2
    assert "发送所选" in for_partner_panel

    sent = _send_packet(client, recap_url, [correction_id, phrase_id])
    assert sent.status_code == 302
    packet_url = sent.headers["Location"]
    assert re.fullmatch(r"/partner-packets/\d+", packet_url)
    assert client.get(packet_url).status_code == 200

    client.post(f"{recap_url}/items/{correction_id}", data={
        "kind": "correction",
        "content": "changed after sending",
        "csrf_token": _csrf(client, recap_url),
    })
    client.post(f"{recap_url}/items/{phrase_id}/delete", data={
        "csrf_token": _csrf(client, recap_url),
    })

    client.get("/logout")
    login(client, "packet-recipient@t.com", PW)
    inbox = client.get("/partner-packets")
    inbox_body = inbox.get_data(as_text=True)
    assert inbox.status_code == 200
    assert "Alice" in inbox_body
    assert "French exchange" in inbox_body

    detail = client.get(packet_url)
    body = detail.get_data(as_text=True)
    assert detail.status_code == 200
    assert "我很同意 → 我很赞同" in body
    assert "下次试试：我完全赞同你的看法。" in body
    assert "changed after sending" not in body
    assert "Pierre 下个月准备 HSK" not in body
    assert "private relationship note" not in body
    assert client.get(recap_url).status_code == 404

    with bypass_engine.connect() as conn:
        packet = conn.execute(text(
            "SELECT sender_user_id, recipient_user_id FROM partner_packets"
        )).one()
    assert packet == (sender_id, recipient_id)


def test_packet_contains_only_explicitly_selected_items(
    app, client, bypass_engine,
):
    provision_user(app, "packet-select-sender@t.com", PW, name="Alice")
    recipient_id = provision_user(app, "packet-select-recipient@t.com", PW)
    login(client, "packet-select-sender@t.com", PW)
    partner_id = _create_partner(client)
    _link_partner(bypass_engine, partner_id, recipient_id)
    recap_id = _create_recap(client, partner_id)
    recap_url = f"/partners/{partner_id}/recaps/{recap_id}"
    selected_id = _add_item(
        client, recap_url, side="for_partner", kind="expression",
        content="selected expression",
    )
    _add_item(
        client, recap_url, side="for_partner", kind="next_time",
        content="not selected advice",
    )

    response = _send_packet(client, recap_url, [selected_id])
    body = client.get(response.headers["Location"]).get_data(as_text=True)
    assert "selected expression" in body
    assert "not selected advice" not in body


def test_unbound_partner_cannot_receive_packet(app, client, bypass_engine):
    sender_id = provision_user(app, "packet-unbound@t.com", PW)
    login(client, "packet-unbound@t.com", PW)
    partner_id = _create_partner(client)
    recap_id = _create_recap(client, partner_id)
    recap_url = f"/partners/{partner_id}/recaps/{recap_id}"
    item_id = _add_item(
        client, recap_url, side="for_partner", kind="expression",
        content="cannot send yet",
    )

    response = _send_packet(client, recap_url, [item_id])
    assert response.status_code == 302
    follow = client.get(response.headers["Location"])
    assert "请先邀请伙伴绑定账号" in follow.get_data(as_text=True)
    with bypass_engine.connect() as conn:
        count = conn.execute(text(
            "SELECT count(*) FROM partner_packets WHERE sender_user_id = :sender"
        ), {"sender": sender_id}).scalar()
    assert count == 0


def test_for_me_or_foreign_recap_item_cannot_enter_packet(
    app, client, bypass_engine,
):
    sender_id = provision_user(app, "packet-invalid-sender@t.com", PW)
    recipient_id = provision_user(app, "packet-invalid-recipient@t.com", PW)
    login(client, "packet-invalid-sender@t.com", PW)
    partner_id = _create_partner(client)
    _link_partner(bypass_engine, partner_id, recipient_id)
    first_recap_id = _create_recap(client, partner_id)
    first_url = f"/partners/{partner_id}/recaps/{first_recap_id}"
    private_id = _add_item(
        client, first_url, side="for_me", kind="private_note",
        content="never share me",
    )
    second_recap_id = _create_recap(client, partner_id)
    second_url = f"/partners/{partner_id}/recaps/{second_recap_id}"
    other_id = _add_item(
        client, second_url, side="for_partner", kind="expression",
        content="belongs to another recap",
    )

    for item_id in (private_id, other_id):
        response = _send_packet(client, first_url, [item_id])
        assert response.status_code == 302
        body = client.get(response.headers["Location"]).get_data(as_text=True)
        assert "只能发送当前复盘中帮他记的内容" in body

    with bypass_engine.connect() as conn:
        count = conn.execute(text(
            "SELECT count(*) FROM partner_packets WHERE sender_user_id = :sender"
        ), {"sender": sender_id}).scalar()
    assert count == 0


def test_exact_packet_resubmission_is_idempotent(
    app, client, bypass_engine,
):
    sender_id = provision_user(app, "packet-twice-sender@t.com", PW)
    recipient_id = provision_user(app, "packet-twice-recipient@t.com", PW)
    login(client, "packet-twice-sender@t.com", PW)
    partner_id = _create_partner(client)
    _link_partner(bypass_engine, partner_id, recipient_id)
    recap_id = _create_recap(client, partner_id)
    recap_url = f"/partners/{partner_id}/recaps/{recap_id}"
    item_id = _add_item(
        client, recap_url, side="for_partner", kind="expression",
        content="send once",
    )

    first = _send_packet(client, recap_url, [item_id])
    second = _send_packet(client, recap_url, [item_id])

    assert first.headers["Location"] == second.headers["Location"]
    with bypass_engine.connect() as conn:
        count = conn.execute(text(
            "SELECT count(*) FROM partner_packets WHERE sender_user_id = :sender"
        ), {"sender": sender_id}).scalar()
    assert count == 1


def test_packet_rls_allows_only_sender_and_recipient(
    app, client, app_engine, bypass_engine,
):
    sender_id = provision_user(app, "packet-rls-sender@t.com", PW)
    recipient_id = provision_user(app, "packet-rls-recipient@t.com", PW)
    stranger_id = provision_user(app, "packet-rls-stranger@t.com", PW)
    login(client, "packet-rls-sender@t.com", PW)
    partner_id = _create_partner(client)
    _link_partner(bypass_engine, partner_id, recipient_id)
    recap_id = _create_recap(client, partner_id)
    recap_url = f"/partners/{partner_id}/recaps/{recap_id}"
    item_id = _add_item(
        client, recap_url, side="for_partner", kind="expression",
        content="rls protected",
    )
    _send_packet(client, recap_url, [item_id])

    with app_engine.connect() as conn:
        set_uid(conn, sender_id)
        assert conn.execute(text("SELECT count(*) FROM partner_packets")).scalar() == 1
        assert conn.execute(text("SELECT count(*) FROM partner_packet_items")).scalar() == 1
        set_uid(conn, recipient_id)
        assert conn.execute(text("SELECT count(*) FROM partner_packets")).scalar() == 1
        assert conn.execute(text("SELECT count(*) FROM partner_packet_items")).scalar() == 1
        set_uid(conn, stranger_id)
        assert conn.execute(text("SELECT count(*) FROM partner_packets")).scalar() == 0
        assert conn.execute(text("SELECT count(*) FROM partner_packet_items")).scalar() == 0

    with app_engine.connect() as conn:
        set_uid(conn, sender_id)
        changed = conn.execute(text(
            "UPDATE partner_packets SET recap_title = 'tampered'"
        ))
        assert changed.rowcount == 0
    with app_engine.connect() as conn:
        set_uid(conn, recipient_id)
        deleted = conn.execute(text("DELETE FROM partner_packets"))
        assert deleted.rowcount == 0
        changed = conn.execute(text(
            "UPDATE partner_packet_items SET content = 'tampered'"
        ))
        assert changed.rowcount == 0
    with bypass_engine.connect() as conn:
        assert conn.execute(text(
            "SELECT recap_title FROM partner_packets"
        )).scalar() == "French exchange"


def test_database_rejects_packet_for_non_linked_recipient(bypass_engine):
    sender_id = make_user(bypass_engine, "packet-fk-sender@t.com")
    recipient_id = make_user(bypass_engine, "packet-fk-recipient@t.com")
    wrong_id = make_user(bypass_engine, "packet-fk-wrong@t.com")
    with bypass_engine.begin() as conn:
        partner_id = conn.execute(text(
            "INSERT INTO language_partners("
            "user_id, linked_user_id, display_name, created_at, updated_at) "
            "VALUES (:sender, :recipient, 'Partner', now(), now()) RETURNING id"
        ), {"sender": sender_id, "recipient": recipient_id}).scalar()
        recap_id = conn.execute(text(
            "INSERT INTO partner_recaps("
            "user_id, partner_id, session_date, created_at, updated_at) "
            "VALUES (:sender, :partner, '2026-07-10', now(), now()) RETURNING id"
        ), {"sender": sender_id, "partner": partner_id}).scalar()

    with bypass_engine.connect() as conn:
        with pytest.raises(DBAPIError):
            conn.execute(text(
                "INSERT INTO partner_packets("
                "sender_user_id, recipient_user_id, partner_id, recap_id, "
                "sender_display_name, recipient_display_name, session_date, "
                "content_fingerprint, item_count, created_at) VALUES ("
                ":sender, :wrong, :partner, :recap, 'Sender', 'Wrong', "
                "'2026-07-10', :fingerprint, 1, now())"
            ), {
                "sender": sender_id,
                "wrong": wrong_id,
                "partner": partner_id,
                "recap": recap_id,
                "fingerprint": "a" * 64,
            })

    with bypass_engine.begin() as conn:
        packet_id = conn.execute(text(
            "INSERT INTO partner_packets("
            "sender_user_id, recipient_user_id, partner_id, recap_id, "
            "sender_display_name, recipient_display_name, session_date, "
            "content_fingerprint, item_count, created_at) VALUES ("
            ":sender, :recipient, :partner, :recap, 'Sender', 'Recipient', "
            "'2026-07-10', :fingerprint, 1, now()) RETURNING id"
        ), {
            "sender": sender_id,
            "recipient": recipient_id,
            "partner": partner_id,
            "recap": recap_id,
            "fingerprint": "b" * 64,
        }).scalar()
    assert packet_id
