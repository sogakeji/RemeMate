"""Packet-facing SessionPad term + context integration."""
import re
from concurrent.futures import ThreadPoolExecutor
from threading import Barrier

from sqlalchemy import text

from app.services import llm
from tests.helpers import login, provision_user


PW = "pw12345678"


def _csrf(client, path):
    body = client.get(path).get_data(as_text=True)
    match = re.search(r'name="csrf_token"[^>]*value="([^"]+)"', body)
    return match.group(1) if match else None


def _provision_learning_user(app, email):
    from app.services.provisioning import create_user_with_defaults

    with app.app_context():
        user_id, _ = create_user_with_defaults(
            email,
            "Recipient",
            password=PW,
            learning_languages=["fr"],
        )
    return user_id


def _make_packet(bypass_engine, sender_id, recipient_id, content):
    with bypass_engine.begin() as conn:
        partner_id = conn.execute(text(
            "INSERT INTO language_partners("
            "user_id,linked_user_id,display_name,learning_language_code,"
            "created_at,updated_at) VALUES "
            "(:sender,:recipient,'Pierre','fr',now(),now()) RETURNING id"
        ), {"sender": sender_id, "recipient": recipient_id}).scalar_one()
        recap_id = conn.execute(text(
            "INSERT INTO partner_recaps("
            "user_id,partner_id,session_date,title,created_at,updated_at"
            ") VALUES (:sender,:partner,'2026-07-30','Exchange',now(),now()) "
            "RETURNING id"
        ), {"sender": sender_id, "partner": partner_id}).scalar_one()
        packet_id = conn.execute(text(
            "INSERT INTO partner_packets("
            "sender_user_id,recipient_user_id,partner_id,recap_id,"
            "sender_display_name,recipient_display_name,recap_title,"
            "session_date,language_code,content_fingerprint,item_count,"
            "created_at) VALUES ("
            ":sender,:recipient,:partner,:recap,'Alice','Pierre','Exchange',"
            "'2026-07-30','fr',:fingerprint,1,now()) RETURNING id"
        ), {
            "sender": sender_id,
            "recipient": recipient_id,
            "partner": partner_id,
            "recap": recap_id,
            "fingerprint": f"{sender_id + recipient_id:064x}"[-64:],
        }).scalar_one()
        item_id = conn.execute(text(
            "INSERT INTO partner_packet_items(packet_id,kind,content,position) "
            "VALUES (:packet,'expression',:content,0) RETURNING id"
        ), {"packet": packet_id, "content": content}).scalar_one()
    return packet_id, item_id


def _adopt_rows(client, packet_id, item_id, rows):
    packet_url = f"/partner-packets/{packet_id}"
    data = {"csrf_token": _csrf(client, packet_url)}
    data["candidate_term"] = [row["term"] for row in rows]
    data["candidate_context"] = [row.get("context", "") for row in rows]
    data["candidate_origin"] = [row.get("origin", "manual") for row in rows]
    data["candidate_original_context"] = [
        row.get("original_context", "") for row in rows
    ]
    return client.post(
        f"{packet_url}/items/{item_id}/add-candidate",
        data=data,
    )


def test_ai_suggestions_render_editable_term_and_context_rows(
    app, client, bypass_engine, monkeypatch,
):
    recipient_id = _provision_learning_user(app, "sp2-suggest-recipient@t.com")
    sender_id = provision_user(app, "sp2-suggest-sender@t.com", PW)
    feedback = "Elle prend des cours de danse puis elle se repose."
    packet_id, item_id = _make_packet(
        bypass_engine,
        sender_id,
        recipient_id,
        feedback,
    )
    monkeypatch.setattr(
        "app.services.packets.llm.chat",
        lambda *args, **kwargs: llm.LLMResult(
            '{"candidates":['
            '{"term":"prendre des cours",'
            '"context":"prend des cours de danse"},'
            '{"term":"se reposer","context":"elle se repose"}'
            ']}',
            17,
            9,
            "fake",
            "fake-extract",
        ),
    )
    login(client, "sp2-suggest-recipient@t.com", PW)
    packet_url = f"/partner-packets/{packet_id}"

    response = client.post(
        f"{packet_url}/items/{item_id}/suggest-terms",
        data={"csrf_token": _csrf(client, packet_url)},
        headers={"HX-Request": "true"},
    )
    body = response.get_data(as_text=True)

    assert response.status_code == 200
    assert body.count('name="candidate_term"') == 2
    assert 'value="prendre des cours"' in body
    assert "prend des cours de danse" in body
    assert 'name="candidate_original_context"' in body
    assert "AI 建议已填入，可继续修改" in body


def test_structured_manual_submission_creates_context_bearing_candidates(
    app, client, bypass_engine,
):
    recipient_id = _provision_learning_user(app, "sp2-manual-recipient@t.com")
    sender_id = provision_user(app, "sp2-manual-sender@t.com", PW)
    feedback = "Elle prend des cours de danse puis elle se repose."
    packet_id, item_id = _make_packet(
        bypass_engine,
        sender_id,
        recipient_id,
        feedback,
    )
    login(client, "sp2-manual-recipient@t.com", PW)

    response = _adopt_rows(client, packet_id, item_id, [
        {
            "term": "prendre des cours",
            "context": "Elle prend des cours de danse.",
        },
        {"term": "se reposer", "context": ""},
    ])

    assert response.status_code == 302
    with bypass_engine.connect() as conn:
        rows = conn.execute(text(
            "SELECT c.word,c.context_excerpt,c.context_provenance,"
            "c.source_example FROM partner_packet_item_adoptions a "
            "JOIN word_candidates c ON c.id=a.candidate_id "
            "WHERE a.packet_item_id=:item ORDER BY c.id"
        ), {"item": item_id}).mappings().all()
    assert rows == [
        {
            "word": "prendre des cours",
            "context_excerpt": "Elle prend des cours de danse.",
            "context_provenance": "user_edited",
            "source_example": None,
        },
        {
            "word": "se reposer",
            "context_excerpt": None,
            "context_provenance": None,
            "source_example": None,
        },
    ]


def test_unchanged_ai_context_is_saved_as_source_quote(
    app, client, bypass_engine,
):
    recipient_id = _provision_learning_user(app, "sp2-ai-recipient@t.com")
    sender_id = provision_user(app, "sp2-ai-sender@t.com", PW)
    feedback = "Elle prend des cours de danse."
    packet_id, item_id = _make_packet(
        bypass_engine,
        sender_id,
        recipient_id,
        feedback,
    )
    login(client, "sp2-ai-recipient@t.com", PW)

    response = _adopt_rows(client, packet_id, item_id, [{
        "term": "prendre des cours",
        "context": feedback,
        "origin": "source_quote",
        "original_context": feedback,
    }])

    assert response.status_code == 302
    with bypass_engine.connect() as conn:
        row = conn.execute(text(
            "SELECT c.context_excerpt,c.context_provenance "
            "FROM partner_packet_item_adoptions a "
            "JOIN word_candidates c ON c.id=a.candidate_id "
            "WHERE a.packet_item_id=:item"
        ), {"item": item_id}).mappings().one()
    assert row == {
        "context_excerpt": feedback,
        "context_provenance": "source_quote",
    }


def test_concurrent_packet_adoption_reuses_one_candidate(
    app, bypass_engine,
):
    recipient_id = _provision_learning_user(app, "sp2-race-recipient@t.com")
    sender_id = provision_user(app, "sp2-race-sender@t.com", PW)
    feedback = "Elle prend des cours de danse."
    packet_id, item_id = _make_packet(
        bypass_engine,
        sender_id,
        recipient_id,
        feedback,
    )
    packet_url = f"/partner-packets/{packet_id}"
    action = f"{packet_url}/items/{item_id}/add-candidate"
    barrier = Barrier(2)

    def adopt():
        thread_client = app.test_client()
        login(thread_client, "sp2-race-recipient@t.com", PW)
        csrf_token = _csrf(thread_client, packet_url)
        barrier.wait()
        response = thread_client.post(action, data={
            "csrf_token": csrf_token,
            "candidate_term": "prendre des cours",
            "candidate_context": feedback,
            "candidate_origin": "source_quote",
            "candidate_original_context": feedback,
        })
        return response.status_code

    with ThreadPoolExecutor(max_workers=2) as pool:
        statuses = list(pool.map(lambda _: adopt(), range(2)))

    assert statuses == [302, 302]
    with bypass_engine.connect() as conn:
        row = conn.execute(text(
            "SELECT count(DISTINCT a.candidate_id) AS candidate_count,"
            "count(*) AS adoption_count "
            "FROM partner_packet_item_adoptions a "
            "WHERE a.packet_item_id=:item"
        ), {"item": item_id}).mappings().one()
    assert row == {"candidate_count": 1, "adoption_count": 1}