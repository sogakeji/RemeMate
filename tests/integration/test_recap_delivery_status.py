"""SessionPad B9: truthful send and thank status on partner recaps."""
import re

from sqlalchemy import event, text

from app.extensions import db
from tests.helpers import login, provision_user


PW = "pw12345678"


def _seed_recap(conn, sender_id, partner_id, title):
    return conn.execute(text(
        "INSERT INTO partner_recaps(user_id,partner_id,session_date,title,"
        "created_at,updated_at) VALUES (:sender,:partner,'2026-07-11',:title,"
        "now(),now()) RETURNING id"
    ), {
        "sender": sender_id, "partner": partner_id, "title": title,
    }).scalar()


def _seed_packet(conn, sender_id, recipient_id, partner_id, recap_id, suffix):
    packet_id = conn.execute(text(
        "INSERT INTO partner_packets(sender_user_id,recipient_user_id,partner_id,"
        "recap_id,sender_display_name,recipient_display_name,recap_title,"
        "session_date,content_fingerprint,item_count,created_at) VALUES "
        "(:sender,:recipient,:partner,:recap,'Alice','Pierre','Exchange',"
        "'2026-07-11',:fingerprint,1,now()) RETURNING id"
    ), {
        "sender": sender_id,
        "recipient": recipient_id,
        "partner": partner_id,
        "recap": recap_id,
        "fingerprint": f"{suffix:064x}"[-64:],
    }).scalar()
    conn.execute(text(
        "INSERT INTO partner_packet_items(packet_id,kind,content,position) "
        "VALUES (:packet,'expression','谢谢你的反馈',0)"
    ), {"packet": packet_id})
    return packet_id


def _recap_row(body, recap_id):
    match = re.search(
        rf'<div[^>]+data-recap-id="{recap_id}".*?</div>', body, re.S,
    )
    assert match
    return match.group()


def test_partner_page_shows_truthful_pending_sent_and_thanked_states(
    app, client, bypass_engine,
):
    sender_id = provision_user(app, "status-sender@t.com", PW, name="Alice")
    recipient_id = provision_user(
        app, "status-recipient@t.com", PW, name="Pierre",
    )
    with bypass_engine.begin() as conn:
        partner_id = conn.execute(text(
            "INSERT INTO language_partners(user_id,linked_user_id,display_name,"
            "native_language_code,learning_language_code,created_at,updated_at) "
            "VALUES (:sender,:recipient,'Pierre','fr','zh',now(),now()) RETURNING id"
        ), {"sender": sender_id, "recipient": recipient_id}).scalar()
        pending_id = _seed_recap(conn, sender_id, partner_id, "待发送复盘")
        private_id = _seed_recap(conn, sender_id, partner_id, "仅自己记录")
        sent_id = _seed_recap(conn, sender_id, partner_id, "已发送复盘")
        thanked_id = _seed_recap(conn, sender_id, partner_id, "已感谢复盘")
        conn.execute(text(
            "INSERT INTO partner_recap_items(user_id,recap_id,side,kind,content,"
            "created_at,updated_at) VALUES "
            "(:sender,:pending,'for_partner','correction','待发送',now(),now()),"
            "(:sender,:private,'for_me','expression','只给自己',now(),now())"
        ), {
            "sender": sender_id,
            "pending": pending_id,
            "private": private_id,
        })
        sent_packet = _seed_packet(
            conn, sender_id, recipient_id, partner_id, sent_id, 101,
        )
        thanked_packet = _seed_packet(
            conn, sender_id, recipient_id, partner_id, thanked_id, 102,
        )
        conn.execute(text(
            "INSERT INTO partner_packet_thanks(packet_id,recipient_user_id,thanked_at) "
            "VALUES (:packet,:recipient,now())"
        ), {"packet": thanked_packet, "recipient": recipient_id})

    login(client, "status-sender@t.com", PW)
    statements = []

    def capture(_conn, _cursor, statement, _params, _context, _many):
        statements.append(" ".join(statement.split()))

    with app.app_context():
        engine = db.engine
    event.listen(engine, "before_cursor_execute", capture)
    try:
        body = client.get(f"/partners/{partner_id}").get_data(as_text=True)
    finally:
        event.remove(engine, "before_cursor_execute", capture)

    pending = _recap_row(body, pending_id)
    assert "待发送" in pending
    assert f"/partners/{partner_id}/recaps/{pending_id}?side=for_partner" in pending

    private = _recap_row(body, private_id)
    assert "待发送" not in private
    assert "已发送" not in private
    assert "对方已感谢" not in private

    sent = _recap_row(body, sent_id)
    assert "已发送 1 份" in sent
    assert f'/partner-packets/{sent_packet}' in sent

    thanked = _recap_row(body, thanked_id)
    assert "对方已感谢" in thanked
    assert f'/partner-packets/{thanked_packet}' in thanked

    assert sum(
        "FROM partner_recap_items" in statement and "GROUP BY" in statement
        for statement in statements
    ) == 1
    assert sum(
        "FROM partner_packets" in statement and "GROUP BY" in statement
        for statement in statements
    ) == 1
