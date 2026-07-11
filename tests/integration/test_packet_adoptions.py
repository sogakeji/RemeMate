"""SessionPad B7: recipient-private adoption into candidate review."""
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


def _provision_learning_user(app, email, language="zh"):
    from app.services.provisioning import create_user_with_defaults

    with app.app_context():
        user_id, _ = create_user_with_defaults(
            email, "Recipient", password=PW, learning_languages=[language],
        )
    return user_id


def _make_packet(
    bypass_engine, sender_id, recipient_id, *, language="zh",
    items=None,
):
    items = items or [
        ("expression", "值得记住的表达"),
        ("correction", "我很同意 → 我很赞同"),
        ("next_time", "下次练习语序"),
    ]
    with bypass_engine.begin() as conn:
        partner_id = conn.execute(text(
            "INSERT INTO language_partners("
            "user_id, linked_user_id, display_name, learning_language_code, "
            "created_at, updated_at) VALUES ("
            ":sender, :recipient, 'Pierre', :language, now(), now()) RETURNING id"
        ), {
            "sender": sender_id,
            "recipient": recipient_id,
            "language": language,
        }).scalar()
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
            "session_date, language_code, content_fingerprint, item_count, "
            "created_at) VALUES ("
            ":sender, :recipient, :partner, :recap, 'Alice', 'Pierre', "
            "'Exchange', '2026-07-11', :language, :fingerprint, :item_count, "
            "now()) RETURNING id"
        ), {
            "sender": sender_id,
            "recipient": recipient_id,
            "partner": partner_id,
            "recap": recap_id,
            "language": language,
            "fingerprint": f"{sender_id + recipient_id:064x}"[-64:],
            "item_count": len(items),
        }).scalar()
        item_ids = []
        for position, (kind, content) in enumerate(items):
            item_ids.append(conn.execute(text(
                "INSERT INTO partner_packet_items("
                "packet_id, kind, content, position) "
                "VALUES (:packet, :kind, :content, :position) RETURNING id"
            ), {
                "packet": packet_id,
                "kind": kind,
                "content": content,
                "position": position,
            }).scalar())
    return packet_id, item_ids, partner_id


def _adopt(client, packet_id, item_id, term):
    packet_url = f"/partner-packets/{packet_id}"
    return client.post(
        f"{packet_url}/items/{item_id}/add-candidate",
        data={"terms": term, "csrf_token": _csrf(client, packet_url)},
    )


def test_recipient_can_edit_received_expression_before_candidate_review(
    app, client, bypass_engine,
):
    sender_id = provision_user(app, "adopt-sender@t.com", PW, name="Alice")
    recipient_id = _provision_learning_user(app, "adopt-recipient@t.com")
    packet_id, item_ids, _ = _make_packet(
        bypass_engine, sender_id, recipient_id,
    )
    expression_id, correction_id, next_time_id = item_ids
    packet_url = f"/partner-packets/{packet_id}"
    login(client, "adopt-recipient@t.com", PW)

    body = client.get(packet_url).get_data(as_text=True)
    expression_card = re.search(
        rf'data-packet-item-id="{expression_id}".*?</article>', body, re.S,
    ).group()
    correction_card = re.search(
        rf'data-packet-item-id="{correction_id}".*?</article>', body, re.S,
    ).group()
    next_card = re.search(
        rf'data-packet-item-id="{next_time_id}".*?</article>', body, re.S,
    ).group()
    assert "拆分为候选词" in expression_card
    assert 'name="terms"' in expression_card
    assert "拆分为候选词" in correction_card
    assert "拆分为候选词" not in next_card

    response = _adopt(client, packet_id, correction_id, "我很赞同")
    assert response.status_code == 302
    assert re.search(r"/intake/\d+/candidates$", response.headers["Location"])
    with bypass_engine.connect() as conn:
        row = conn.execute(text(
            "SELECT c.word, c.source_example, c.user_id, s.language_code, "
            "s.source_type, a.recipient_user_id "
            "FROM partner_packet_item_adoptions a "
            "JOIN word_candidates c ON c.id = a.candidate_id "
            "JOIN intake_sources s ON s.id = c.source_id "
            "WHERE a.packet_item_id = :item"
        ), {"item": correction_id}).mappings().one()
    assert row["word"] == "我很赞同"
    assert row["source_example"] == "我很同意 → 我很赞同"
    assert row["user_id"] == row["recipient_user_id"] == recipient_id
    assert row["language_code"] == "zh"
    assert row["source_type"] == "sessionpad"

    client.get("/logout")
    login(client, "adopt-sender@t.com", PW)
    sender_body = client.get(packet_url).get_data(as_text=True)
    assert 'class="packet-adopt-form"' not in sender_body
    assert 'class="packet-adopted-link"' not in sender_body


def test_one_received_sentence_can_create_multiple_word_level_candidates(
    app, client, bypass_engine,
):
    sender_id = provision_user(app, "adopt-many-sender@t.com", PW)
    recipient_id = _provision_learning_user(app, "adopt-many-recipient@t.com")
    context = "我很同意你的看法，更自然可以说我很赞同你的观点。"
    packet_id, item_ids, _ = _make_packet(
        bypass_engine, sender_id, recipient_id,
        items=[("correction", context)],
    )
    login(client, "adopt-many-recipient@t.com", PW)

    response = _adopt(
        client, packet_id, item_ids[0], "赞同\n观点\n赞同",
    )

    assert response.status_code == 302
    with bypass_engine.connect() as conn:
        rows = conn.execute(text(
            "SELECT c.word,c.source_example FROM partner_packet_item_adoptions a "
            "JOIN word_candidates c ON c.id=a.candidate_id "
            "WHERE a.packet_item_id=:item ORDER BY c.id"
        ), {"item": item_ids[0]}).mappings().all()
    assert [row["word"] for row in rows] == ["赞同", "观点"]
    assert {row["source_example"] for row in rows} == {context}


def test_received_item_adoption_is_idempotent_and_reuses_packet_source(
    app, client, bypass_engine,
):
    sender_id = provision_user(app, "adopt-twice-sender@t.com", PW)
    recipient_id = _provision_learning_user(app, "adopt-twice-recipient@t.com")
    packet_id, item_ids, _ = _make_packet(
        bypass_engine, sender_id, recipient_id,
        items=[
            ("expression", "第一个表达"),
            ("natural_phrase", "第二个自然说法"),
        ],
    )
    login(client, "adopt-twice-recipient@t.com", PW)

    first = _adopt(
        client, packet_id, item_ids[0], "第一个表达\n第一个补充",
    )
    repeated = _adopt(
        client, packet_id, item_ids[0], "第一个表达\n第一个补充",
    )
    second = _adopt(client, packet_id, item_ids[1], "第二个自然说法")

    assert first.headers["Location"] == repeated.headers["Location"]
    assert second.status_code == 302
    with bypass_engine.connect() as conn:
        sources = conn.execute(text(
            "SELECT count(*) FROM partner_packet_intakes WHERE packet_id = :packet"
        ), {"packet": packet_id}).scalar()
        candidates = conn.execute(text(
            "SELECT count(DISTINCT candidate_id) "
            "FROM partner_packet_item_adoptions WHERE packet_id = :packet"
        ), {"packet": packet_id}).scalar()
    assert sources == 1
    assert candidates == 3


def test_mixed_existing_word_and_new_term_reports_both_outcomes(
    app, client, bypass_engine,
):
    sender_id = provision_user(app, "adopt-mixed-sender@t.com", PW)
    recipient_id = _provision_learning_user(app, "adopt-mixed-recipient@t.com")
    packet_id, item_ids, _ = _make_packet(
        bypass_engine, sender_id, recipient_id,
        items=[("expression", "已会和新词")],
    )
    with bypass_engine.begin() as conn:
        list_id = conn.execute(text(
            "SELECT id FROM word_lists WHERE user_id=:user AND language_code='zh'"
        ), {"user": recipient_id}).scalar()
        conn.execute(text(
            "INSERT INTO words(list_id,word,marked,due_date,interval,ease,reps,lapses) "
            "VALUES (:list,'已会',false,now(),1,2.5,0,0)"
        ), {"list": list_id})
    login(client, "adopt-mixed-recipient@t.com", PW)

    response = _adopt(client, packet_id, item_ids[0], "已会\n新词")
    body = client.get(response.headers["Location"]).get_data(as_text=True)

    assert "已加入 1 个候选词" in body
    assert "另有 1 个已在生词本中" in body
    with bypass_engine.connect() as conn:
        words = conn.execute(text(
            "SELECT c.word FROM partner_packet_item_adoptions a "
            "JOIN word_candidates c ON c.id=a.candidate_id "
            "WHERE a.packet_item_id=:item"
        ), {"item": item_ids[0]}).scalars().all()
    assert words == ["新词"]


def test_ineligible_or_wrong_user_cannot_adopt_packet_item(
    app, client, bypass_engine,
):
    sender_id = provision_user(app, "adopt-denied-sender@t.com", PW)
    recipient_id = _provision_learning_user(app, "adopt-denied-recipient@t.com")
    provision_user(app, "adopt-denied-stranger@t.com", PW)
    packet_id, item_ids, _ = _make_packet(
        bypass_engine, sender_id, recipient_id,
    )
    expression_id, _, next_time_id = item_ids

    login(client, "adopt-denied-recipient@t.com", PW)
    denied = _adopt(client, packet_id, next_time_id, "不应加入")
    assert denied.status_code == 302
    assert "这类反馈不能加入候选词" in client.get(
        denied.headers["Location"]
    ).get_data(as_text=True)

    client.get("/logout")
    login(client, "adopt-denied-sender@t.com", PW)
    assert _adopt(client, packet_id, expression_id, "sender cannot").status_code == 404
    client.get("/logout")
    login(client, "adopt-denied-stranger@t.com", PW)
    assert _adopt(client, packet_id, expression_id, "stranger cannot").status_code == 404


def test_packet_language_snapshot_survives_partner_profile_change(
    app, client, bypass_engine,
):
    sender_id = provision_user(app, "adopt-language-sender@t.com", PW)
    recipient_id = _provision_learning_user(app, "adopt-language-recipient@t.com")
    packet_id, item_ids, partner_id = _make_packet(
        bypass_engine, sender_id, recipient_id, language="zh",
        items=[("expression", "赞同")],
    )
    with bypass_engine.begin() as conn:
        conn.execute(text(
            "UPDATE language_partners SET learning_language_code = 'fr' "
            "WHERE id = :partner"
        ), {"partner": partner_id})
    login(client, "adopt-language-recipient@t.com", PW)

    _adopt(client, packet_id, item_ids[0], "赞同")

    with bypass_engine.connect() as conn:
        language = conn.execute(text(
            "SELECT s.language_code FROM partner_packet_intakes pi "
            "JOIN intake_sources s ON s.id = pi.source_id "
            "WHERE pi.packet_id = :packet"
        ), {"packet": packet_id}).scalar()
    assert language == "zh"


def test_adoption_requires_recipient_learning_language(
    app, client, bypass_engine,
):
    sender_id = provision_user(app, "adopt-setting-sender@t.com", PW)
    recipient_id = provision_user(app, "adopt-setting-recipient@t.com", PW)
    packet_id, item_ids, _ = _make_packet(
        bypass_engine, sender_id, recipient_id, language="zh",
        items=[("expression", "赞同")],
    )
    login(client, "adopt-setting-recipient@t.com", PW)

    response = _adopt(client, packet_id, item_ids[0], "赞同")
    body = client.get(response.headers["Location"]).get_data(as_text=True)
    assert "请先在设置中把中文加入正在学" in body
    with bypass_engine.connect() as conn:
        assert conn.execute(text(
            "SELECT count(*) FROM partner_packet_intakes"
        )).scalar() == 0


def test_adoption_rls_is_recipient_private_and_rejects_cross_user_candidate(
    app, client, app_engine, bypass_engine,
):
    sender_id = provision_user(app, "adopt-rls-sender@t.com", PW)
    recipient_id = _provision_learning_user(app, "adopt-rls-recipient@t.com")
    stranger_id = make_user(bypass_engine, "adopt-rls-stranger@t.com")
    packet_id, item_ids, _ = _make_packet(
        bypass_engine, sender_id, recipient_id,
        items=[("expression", "私有采纳")],
    )
    login(client, "adopt-rls-recipient@t.com", PW)
    _adopt(client, packet_id, item_ids[0], "私有采纳")

    for user_id, expected in (
        (recipient_id, 1), (sender_id, 0), (stranger_id, 0),
    ):
        with app_engine.connect() as conn:
            set_uid(conn, user_id)
            assert conn.execute(text(
                "SELECT count(*) FROM partner_packet_item_adoptions"
            )).scalar() == expected

    with bypass_engine.begin() as conn:
        list_id = conn.execute(text(
            "INSERT INTO word_lists(user_id, name, language_code, created_at) "
            "VALUES (:user, 'ZH', 'zh', now()) RETURNING id"
        ), {"user": stranger_id}).scalar()
        source_id = conn.execute(text(
            "INSERT INTO intake_sources("
            "user_id, source_type, language_code, word_list_id, status, "
            "total_segments, total_candidates, created_at) VALUES ("
            ":user, 'sessionpad', 'zh', :list, 'done', 0, 1, now()) "
            "RETURNING id"
        ), {"user": stranger_id, "list": list_id}).scalar()
        candidate_id = conn.execute(text(
            "INSERT INTO word_candidates(source_id, user_id, word, status, created_at) "
            "VALUES (:source, :user, 'cross', 'pending', now()) RETURNING id"
        ), {"source": source_id, "user": stranger_id}).scalar()

    with pytest.raises(DBAPIError):
        with bypass_engine.begin() as conn:
            conn.execute(text(
                "UPDATE partner_packet_item_adoptions "
                "SET candidate_id = :candidate WHERE packet_item_id = :item"
            ), {"candidate": candidate_id, "item": item_ids[0]})
