"""SessionPad B7: recipient-private adoption into candidate review."""
import re

import pytest
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError

from app.services import llm
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


def _suggest(client, packet_id, item_id):
    packet_url = f"/partner-packets/{packet_id}"
    return client.post(
        f"{packet_url}/items/{item_id}/suggest-terms",
        data={"csrf_token": _csrf(client, packet_url)},
        headers={"HX-Request": "true"},
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
    assert 'name="candidate_term"' in expression_card
    assert 'name="candidate_context"' in expression_card
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
    assert row["source_example"] is None
    assert row["user_id"] == row["recipient_user_id"] == recipient_id
    assert row["language_code"] == "zh"
    assert row["source_type"] == "sessionpad"

    client.get("/logout")
    login(client, "adopt-sender@t.com", PW)
    sender_body = client.get(packet_url).get_data(as_text=True)
    assert 'class="packet-adopt-form"' not in sender_body
    assert 'class="packet-adopted-link"' not in sender_body


def test_sessionpad_source_feedback_is_not_committed_as_example(
    app, client, bypass_engine,
):
    sender_id = provision_user(app, "context-source-sender@t.com", PW)
    recipient_id = _provision_learning_user(app, "context-source-recipient@t.com")
    feedback = "完整伙伴反馈只用于追溯，不应自动成为最终例句。"
    packet_id, item_ids, _ = _make_packet(
        bypass_engine,
        sender_id,
        recipient_id,
        items=[("expression", feedback)],
    )
    login(client, "context-source-recipient@t.com", PW)

    adoption = _adopt(client, packet_id, item_ids[0], "追溯")
    source_id = int(re.search(r"/intake/(\d+)/candidates", adoption.location).group(1))
    with bypass_engine.connect() as conn:
        candidate_id = conn.execute(text(
            "SELECT candidate_id FROM partner_packet_item_adoptions "
            "WHERE packet_item_id=:item"
        ), {"item": item_ids[0]}).scalar_one()

    candidate_page = f"/intake/{source_id}/candidates"
    accepted = client.post(
        f"/intake/sessionpad/candidates/{candidate_id}/accept",
        data={
            "word": "追溯",
            "meaning": "trace back",
            "example": "",
            "csrf_token": _csrf(client, candidate_page),
        },
        headers={"HX-Request": "true"},
    )
    assert accepted.status_code == 200
    committed = client.post(
        f"/intake/{source_id}/commit",
        data={"csrf_token": _csrf(client, candidate_page)},
    )
    assert committed.status_code == 302

    with bypass_engine.connect() as conn:
        row = conn.execute(text(
            "SELECT c.source_example,d.example FROM word_candidates c "
            "JOIN definitions d ON d.word_id=c.word_id WHERE c.id=:candidate"
        ), {"candidate": candidate_id}).mappings().one()
    assert row["source_example"] is None
    assert row["example"] is None

def test_sessionpad_explicit_example_is_committed(
    app, client, bypass_engine,
):
    sender_id = provision_user(app, "explicit-example-sender@t.com", PW)
    recipient_id = _provision_learning_user(
        app,
        "explicit-example-recipient@t.com",
    )
    feedback = "Long partner feedback remains source evidence."
    packet_id, item_ids, _ = _make_packet(
        bypass_engine,
        sender_id,
        recipient_id,
        items=[("expression", feedback)],
    )
    login(client, "explicit-example-recipient@t.com", PW)

    adoption = _adopt(client, packet_id, item_ids[0], "prendre des cours")
    source_id = int(
        re.search(r"/intake/(\d+)/candidates", adoption.location).group(1)
    )
    with bypass_engine.connect() as conn:
        candidate_id = conn.execute(text(
            "SELECT candidate_id FROM partner_packet_item_adoptions "
            "WHERE packet_item_id=:item"
        ), {"item": item_ids[0]}).scalar_one()

    candidate_page = f"/intake/{source_id}/candidates"
    accepted = client.post(
        f"/intake/sessionpad/candidates/{candidate_id}/accept",
        data={
            "word": "prendre des cours",
            "meaning": "to take lessons",
            "example": "Elle prend des cours de danse.",
            "csrf_token": _csrf(client, candidate_page),
        },
        headers={"HX-Request": "true"},
    )
    assert accepted.status_code == 200
    committed = client.post(
        f"/intake/{source_id}/commit",
        data={"csrf_token": _csrf(client, candidate_page)},
    )
    assert committed.status_code == 302

    with bypass_engine.connect() as conn:
        row = conn.execute(text(
            "SELECT c.source_example,d.example FROM word_candidates c "
            "JOIN definitions d ON d.word_id=c.word_id WHERE c.id=:candidate"
        ), {"candidate": candidate_id}).mappings().one()
    assert row["source_example"] is None
    assert row["example"] == "Elle prend des cours de danse."


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
    assert {row["source_example"] for row in rows} == {None}


def test_recipient_can_request_editable_ai_term_suggestions(
    app, client, bypass_engine, monkeypatch,
):
    recipient_id = _provision_learning_user(app, "suggest-recipient@t.com")
    sender_id = provision_user(app, "suggest-sender@t.com", PW)
    context = "我很同意你的看法，更自然可以说我很赞同你的观点。"
    packet_id, item_ids, _ = _make_packet(
        bypass_engine, sender_id, recipient_id,
        items=[("correction", context)],
    )
    captured = {}

    def fake_chat(messages, **kwargs):
        captured["messages"] = messages
        captured["kwargs"] = kwargs
        return llm.LLMResult(
            '{"candidates":['
            '{"term":"赞同","context":"我很赞同你的观点"},'
            '{"term":"观点","context":"你的观点"},'
            '{"term":"赞同","context":null}]}',
            17, 9, "fake", "fake-extract",
        )

    monkeypatch.setattr("app.services.packets.llm.chat", fake_chat)
    login(client, "suggest-recipient@t.com", PW)

    response = _suggest(client, packet_id, item_ids[0])
    body = response.get_data(as_text=True)

    assert response.status_code == 200
    assert body.count('name="candidate_term"') == 2
    assert 'value="赞同"' in body
    assert 'value="观点"' in body
    assert "我很赞同你的观点" in body
    assert context not in body
    assert "AI 建议已填入，可继续修改" in body
    assert captured["kwargs"] == {"task": "extract", "json_mode": True}
    prompt = str(captured["messages"])
    assert context in prompt
    assert "Alice" not in prompt
    with bypass_engine.connect() as conn:
        usage = conn.execute(text(
            "SELECT feature,prompt_tokens,completion_tokens FROM token_usage_log "
            "WHERE user_id=:user"
        ), {"user": recipient_id}).mappings().one()
        candidate_count = conn.execute(text(
            "SELECT count(*) FROM word_candidates WHERE user_id=:user"
        ), {"user": recipient_id}).scalar()
    assert usage == {
        "feature": "sessionpad_term_suggestions",
        "prompt_tokens": 17,
        "completion_tokens": 9,
    }
    assert candidate_count == 0


def test_ai_suggestion_failure_keeps_manual_split_available(
    app, client, bypass_engine, monkeypatch,
):
    sender_id = provision_user(app, "suggest-down-sender@t.com", PW)
    recipient_id = _provision_learning_user(app, "suggest-down-recipient@t.com")
    context = "完整反馈仍需保留"
    packet_id, item_ids, _ = _make_packet(
        bypass_engine, sender_id, recipient_id,
        items=[("expression", context)],
    )

    def unavailable(*args, **kwargs):
        raise llm.AllProvidersDown("down")

    monkeypatch.setattr("app.services.packets.llm.chat", unavailable)
    login(client, "suggest-down-recipient@t.com", PW)

    response = _suggest(client, packet_id, item_ids[0])
    body = response.get_data(as_text=True)

    assert response.status_code == 200
    assert context in body
    assert "AI 暂时不可用，可继续手动拆分" in body
    assert 'name="candidate_term"' in body
    assert 'name="candidate_context"' in body
    assert 'name="ai_unavailable" value="1"' in body
    adopted = client.post(
        f"/partner-packets/{packet_id}/items/{item_ids[0]}/add-candidate",
        data={
            "candidate_term": "保留",
            "candidate_context": context,
            "candidate_origin": "source_quote",
            "candidate_original_context": context,
            "ai_unavailable": "1",
            "csrf_token": _csrf(client, f"/partner-packets/{packet_id}"),
        },
    )
    assert adopted.status_code == 302
    assert adopted.location.endswith("?ai=unavailable")
    review = client.get(adopted.location).get_data(as_text=True)
    assert 'data-ai-degraded="true"' in review
    with bypass_engine.connect() as conn:
        assert conn.execute(text(
            "SELECT count(*) FROM token_usage_log WHERE user_id=:user"
        ), {"user": recipient_id}).scalar() == 0


def test_invalid_ai_output_falls_back_but_still_records_consumed_tokens(
    app, client, bypass_engine, monkeypatch,
):
    sender_id = provision_user(app, "suggest-invalid-sender@t.com", PW)
    recipient_id = _provision_learning_user(app, "suggest-invalid-recipient@t.com")
    context = "完整反馈"
    packet_id, item_ids, _ = _make_packet(
        bypass_engine, sender_id, recipient_id,
        items=[("expression", context)],
    )

    monkeypatch.setattr(
        "app.services.packets.llm.chat",
        lambda *args, **kwargs: llm.LLMResult(
            '{"candidates":[]}', 7, 3, "fake", "bad-output",
        ),
    )
    login(client, "suggest-invalid-recipient@t.com", PW)

    response = _suggest(client, packet_id, item_ids[0])
    body = response.get_data(as_text=True)

    assert context in body
    assert "AI 暂时不可用，可继续手动拆分" in body
    with bypass_engine.connect() as conn:
        usage = conn.execute(text(
            "SELECT feature,prompt_tokens,completion_tokens FROM token_usage_log "
            "WHERE user_id=:user"
        ), {"user": recipient_id}).mappings().one()
    assert usage == {
        "feature": "sessionpad_term_suggestions",
        "prompt_tokens": 7,
        "completion_tokens": 3,
    }


def test_non_recipient_cannot_request_ai_suggestions(
    app, client, bypass_engine, monkeypatch,
):
    sender_id = provision_user(app, "suggest-denied-sender@t.com", PW)
    recipient_id = _provision_learning_user(app, "suggest-denied-recipient@t.com")
    provision_user(app, "suggest-denied-stranger@t.com", PW)
    packet_id, item_ids, _ = _make_packet(
        bypass_engine, sender_id, recipient_id,
        items=[("expression", "不应发送给模型")],
    )
    called = False

    def fake_chat(*args, **kwargs):
        nonlocal called
        called = True

    monkeypatch.setattr("app.services.packets.llm.chat", fake_chat)
    login(client, "suggest-denied-stranger@t.com", PW)

    response = _suggest(client, packet_id, item_ids[0])

    assert response.status_code == 404
    assert called is False


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
