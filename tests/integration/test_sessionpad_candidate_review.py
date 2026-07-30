"""SessionPad uses a focused candidate review without changing other intake."""
from sqlalchemy import text

from tests.helpers import login, provision_user


PW = "pw12345678"


def _seed_source(
    app,
    bypass_engine,
    email,
    *,
    source_type="sessionpad",
    candidates=None,
):
    from app.services.provisioning import create_user_with_defaults

    with app.app_context():
        user_id, _ = create_user_with_defaults(
            email,
            "Review Tester",
            password=PW,
            learning_languages=["fr"],
        )
    candidates = candidates or [
        ("premier terme", "Le premier contexte.", "source_quote"),
        ("deuxieme terme", None, None),
    ]
    with bypass_engine.begin() as conn:
        list_id = conn.execute(text(
            "SELECT id FROM word_lists "
            "WHERE user_id=:user AND language_code='fr'"
        ), {"user": user_id}).scalar_one()
        source_id = conn.execute(text(
            "INSERT INTO intake_sources("
            "user_id,source_type,language_code,word_list_id,original_name,"
            "status,total_segments,total_candidates,created_at"
            ") VALUES (:user,:type,'fr',:list,'Conversation avec Alice',"
            "'done',0,:count,now()) RETURNING id"
        ), {
            "user": user_id,
            "type": source_type,
            "list": list_id,
            "count": len(candidates),
        }).scalar_one()
        candidate_ids = []
        for term, context, provenance in candidates:
            candidate_ids.append(conn.execute(text(
                "INSERT INTO word_candidates("
                "source_id,user_id,word,status,context_excerpt,"
                "context_provenance,created_at"
                ") VALUES (:source,:user,:term,'pending',:context,"
                ":provenance,now()) RETURNING id"
            ), {
                "source": source_id,
                "user": user_id,
                "term": term,
                "context": context,
                "provenance": provenance,
            }).scalar_one())
    return user_id, list_id, source_id, candidate_ids


def test_sessionpad_pending_review_focuses_one_candidate(
    app,
    client,
    bypass_engine,
):
    _, _, source_id, _ = _seed_source(
        app,
        bypass_engine,
        "sp3-focus@t.com",
    )
    login(client, "sp3-focus@t.com", PW)

    page = client.get(
        f"/intake/{source_id}/candidates"
    ).get_data(as_text=True)

    assert 'data-sessionpad-review="focused"' in page
    assert 'data-review-progress="1/2"' in page
    assert "premier terme" in page
    assert "deuxieme terme" not in page
    assert "一键入库" not in page


def test_sessionpad_candidates_reject_legacy_review_and_bulk_endpoints(
    app,
    client,
    bypass_engine,
):
    _, _, source_id, candidate_ids = _seed_source(
        app,
        bypass_engine,
        "sp3-no-legacy-bypass@t.com",
    )
    login(client, "sp3-no-legacy-bypass@t.com", PW)

    responses = [
        client.post(f"/intake/candidates/{candidate_ids[0]}/accept"),
        client.post(f"/intake/candidates/{candidate_ids[0]}/ignore"),
        client.post(f"/intake/{source_id}/bulk-accept"),
        client.post(f"/intake/{source_id}/commit-all"),
    ]

    assert [response.status_code for response in responses] == [404] * 4
    with bypass_engine.connect() as conn:
        statuses = conn.execute(text(
            "SELECT status FROM word_candidates "
            "WHERE source_id=:source ORDER BY id"
        ), {"source": source_id}).scalars().all()
        word_count = conn.execute(text(
            "SELECT count(*) FROM words w "
            "JOIN word_lists wl ON wl.id=w.list_id "
            "WHERE wl.user_id=("
            "SELECT user_id FROM intake_sources WHERE id=:source)"
        ), {"source": source_id}).scalar_one()
    assert statuses == ["pending", "pending"]
    assert word_count == 0

def test_accept_advances_queue_without_copying_context_to_example(
    app,
    client,
    bypass_engine,
):
    _, _, source_id, candidate_ids = _seed_source(
        app,
        bypass_engine,
        "sp3-accept@t.com",
    )
    login(client, "sp3-accept@t.com", PW)

    first_page = client.get(
        f"/intake/{source_id}/candidates"
    ).get_data(as_text=True)
    assert "data-use-context-as-example" in first_page
    assert 'name="example"' in first_page
    assert 'name="example" value=""' in first_page

    response = client.post(
        f"/intake/sessionpad/candidates/{candidate_ids[0]}/accept",
        data={
            "word": "premier terme",
            "context_excerpt": "Le premier contexte.",
            "part_of_speech": "",
            "meaning": "",
            "example": "",
            "note": "",
        },
        headers={"HX-Request": "true"},
    )

    assert response.status_code == 200
    body = response.get_data(as_text=True)
    assert 'data-review-progress="2/2"' in body
    assert "deuxieme terme" in body
    assert "premier terme" not in body
    with bypass_engine.connect() as conn:
        row = conn.execute(text(
            "SELECT status,context_excerpt,context_provenance,example "
            "FROM word_candidates WHERE id=:candidate"
        ), {"candidate": candidate_ids[0]}).mappings().one()
    assert row == {
        "status": "accepted",
        "context_excerpt": "Le premier contexte.",
        "context_provenance": "source_quote",
        "example": "",
    }

def test_ignore_advances_queue_and_other_user_cannot_process_candidate(
    app,
    client,
    bypass_engine,
):
    _, _, source_id, candidate_ids = _seed_source(
        app,
        bypass_engine,
        "sp3-ignore-owner@t.com",
    )
    _seed_source(
        app,
        bypass_engine,
        "sp3-ignore-other@t.com",
        candidates=[("autre", None, None)],
    )
    login(client, "sp3-ignore-other@t.com", PW)
    forbidden = client.post(
        f"/intake/sessionpad/candidates/{candidate_ids[0]}/ignore",
        headers={"HX-Request": "true"},
    )
    assert forbidden.status_code == 404

    client.get("/logout")
    login(client, "sp3-ignore-owner@t.com", PW)
    response = client.post(
        f"/intake/sessionpad/candidates/{candidate_ids[0]}/ignore",
        headers={"HX-Request": "true"},
    )

    assert response.status_code == 200
    body = response.get_data(as_text=True)
    assert 'data-review-progress="2/2"' in body
    assert "deuxieme terme" in body
    with bypass_engine.connect() as conn:
        status = conn.execute(text(
            "SELECT status FROM word_candidates WHERE id=:candidate"
        ), {"candidate": candidate_ids[0]}).scalar_one()
    assert status == "ignored"

def _attach_received_packet_source(
    bypass_engine,
    *,
    sender_id,
    recipient_id,
    source_id,
):
    with bypass_engine.begin() as conn:
        partner_id = conn.execute(text(
            "INSERT INTO language_partners("
            "user_id,linked_user_id,display_name,learning_language_code,"
            "created_at,updated_at) VALUES ("
            ":sender,:recipient,'Recipient','fr',now(),now()) RETURNING id"
        ), {"sender": sender_id, "recipient": recipient_id}).scalar_one()
        recap_id = conn.execute(text(
            "INSERT INTO partner_recaps("
            "user_id,partner_id,session_date,title,created_at,updated_at"
            ") VALUES (:sender,:partner,'2026-07-11','Exchange',now(),now()) "
            "RETURNING id"
        ), {"sender": sender_id, "partner": partner_id}).scalar_one()
        packet_id = conn.execute(text(
            "INSERT INTO partner_packets("
            "sender_user_id,recipient_user_id,partner_id,recap_id,"
            "sender_display_name,recipient_display_name,recap_title,"
            "session_date,language_code,content_fingerprint,item_count,created_at"
            ") VALUES (:sender,:recipient,:partner,:recap,'Alice','Review Tester',"
            "'Exchange','2026-07-11','fr',:fingerprint,1,now()) RETURNING id"
        ), {
            "sender": sender_id,
            "recipient": recipient_id,
            "partner": partner_id,
            "recap": recap_id,
            "fingerprint": f"{source_id:064x}"[-64:],
        }).scalar_one()
        conn.execute(text(
            "INSERT INTO partner_packet_intakes("
            "packet_id,recipient_user_id,source_id,created_at"
            ") VALUES (:packet,:recipient,:source,now())"
        ), {
            "packet": packet_id,
            "recipient": recipient_id,
            "source": source_id,
        })
    return packet_id


def test_received_packet_review_shows_light_source_without_feedback_body(
    app,
    client,
    bypass_engine,
):
    recipient_id, _, source_id, _ = _seed_source(
        app,
        bypass_engine,
        "sp3-packet-source@t.com",
    )
    sender_id = provision_user(app, "sp3-packet-sender@t.com", PW, name="Alice")
    packet_id = _attach_received_packet_source(
        bypass_engine,
        sender_id=sender_id,
        recipient_id=recipient_id,
        source_id=source_id,
    )
    login(client, "sp3-packet-source@t.com", PW)

    page = client.get(
        f"/intake/{source_id}/candidates"
    ).get_data(as_text=True)

    assert 'data-sessionpad-source-kind="packet"' in page
    assert "Alice" in page
    assert "2026-07-11" in page
    assert "Exchange" in page
    assert f'href="/partner-packets/{packet_id}"' in page
    assert "完整反馈正文不应默认出现" not in page

def test_accepting_existing_word_links_without_overwriting_definition(
    app,
    client,
    bypass_engine,
):
    _, list_id, source_id, candidate_ids = _seed_source(
        app,
        bypass_engine,
        "sp3-existing@t.com",
        candidates=[("deja vu", "Un sentiment de deja vu.", "source_quote")],
    )
    with bypass_engine.begin() as conn:
        word_id = conn.execute(text(
            "INSERT INTO words("
            "list_id,word,marked,due_date,interval,ease,reps,lapses"
            ") VALUES (:list,'deja vu',false,now(),1,2.5,0,0) RETURNING id"
        ), {"list": list_id}).scalar_one()
        conn.execute(text(
            "INSERT INTO definitions(word_id,meaning,example) "
            "VALUES (:word,'original meaning','original example')"
        ), {"word": word_id})
    login(client, "sp3-existing@t.com", PW)

    page = client.get(
        f"/intake/{source_id}/candidates"
    ).get_data(as_text=True)
    assert 'data-existing-word="true"' in page
    assert "生词本已有" in page

    response = client.post(
        f"/intake/sessionpad/candidates/{candidate_ids[0]}/accept",
        data={
            "word": " deja vu ",
            "context_excerpt": "Un sentiment de deja vu.",
            "meaning": "replacement meaning",
            "example": "replacement example",
        },
        headers={"HX-Request": "true"},
    )
    assert response.status_code == 200

    with bypass_engine.connect() as conn:
        candidate = conn.execute(text(
            "SELECT status,word_id FROM word_candidates WHERE id=:candidate"
        ), {"candidate": candidate_ids[0]}).mappings().one()
        word_count = conn.execute(text(
            "SELECT count(*) FROM words WHERE list_id=:list "
            "AND lower(btrim(word))='deja vu'"
        ), {"list": list_id}).scalar_one()
        definition = conn.execute(text(
            "SELECT meaning,example FROM definitions WHERE word_id=:word"
        ), {"word": word_id}).mappings().one()
    assert candidate == {"status": "accepted", "word_id": word_id}
    assert word_count == 1
    assert definition == {
        "meaning": "original meaning",
        "example": "original example",
    }

def test_transient_ai_degraded_notice_does_not_block_manual_review(
    app,
    client,
    bypass_engine,
):
    _, _, source_id, candidate_ids = _seed_source(
        app,
        bypass_engine,
        "sp3-ai-degraded@t.com",
        candidates=[("se reposer", None, None)],
    )
    login(client, "sp3-ai-degraded@t.com", PW)

    page = client.get(
        f"/intake/{source_id}/candidates?ai=unavailable"
    ).get_data(as_text=True)

    assert 'data-ai-degraded="true"' in page
    assert "AI 建议暂时不可用" in page
    assert f'/intake/sessionpad/candidates/{candidate_ids[0]}/accept' in page
    assert 'name="context_excerpt"' in page

def test_edited_context_is_saved_as_example_only_after_explicit_submit_and_commit(
    app,
    client,
    bypass_engine,
):
    _, _, source_id, candidate_ids = _seed_source(
        app,
        bypass_engine,
        "sp3-explicit-example@t.com",
        candidates=[("prendre un cafe", "On prend un cafe.", "source_quote")],
    )
    login(client, "sp3-explicit-example@t.com", PW)
    edited_context = "On prend un cafe apres le cours."

    accepted = client.post(
        f"/intake/sessionpad/candidates/{candidate_ids[0]}/accept",
        data={
            "word": "prendre un cafe",
            "context_excerpt": edited_context,
            "part_of_speech": "expression",
            "meaning": "to have coffee",
            "example": edited_context,
            "note": "",
        },
        headers={"HX-Request": "true"},
    )

    assert accepted.status_code == 200
    body = accepted.get_data(as_text=True)
    assert f'action="/intake/{source_id}/commit"' in body
    assert "提交入库" in body

    committed = client.post(f"/intake/{source_id}/commit")
    assert committed.status_code == 302
    with bypass_engine.connect() as conn:
        row = conn.execute(text(
            "SELECT c.context_excerpt,c.context_provenance,d.example "
            "FROM word_candidates c "
            "JOIN definitions d ON d.word_id=c.word_id "
            "WHERE c.id=:candidate"
        ), {"candidate": candidate_ids[0]}).mappings().one()
    assert row == {
        "context_excerpt": edited_context,
        "context_provenance": "user_edited",
        "example": edited_context,
    }

def test_context_provenance_and_missing_context_have_distinct_states(
    app,
    client,
    bypass_engine,
):
    cases = [
        ("sp3-source-quote@t.com", "Contexte source.", "source_quote", "原文摘录"),
        ("sp3-user-edited@t.com", "Contexte整理.", "user_edited", "用户整理"),
        ("sp3-no-context@t.com", None, None, "暂时没有语境"),
    ]
    for index, (email, context, provenance, label) in enumerate(cases):
        _, _, source_id, _ = _seed_source(
            app,
            bypass_engine,
            email,
            candidates=[(f"terme-{index}", context, provenance)],
        )
        login(client, email, PW)
        page = client.get(
            f"/intake/{source_id}/candidates"
        ).get_data(as_text=True)
        assert label in page
        assert f'data-context-state="{provenance or "missing"}"' in page
        assert "将语境填入例句草稿" in page
        client.get("/logout")

def test_own_recap_review_links_back_to_the_partner_recap(
    app,
    client,
    bypass_engine,
):
    user_id, _, source_id, _ = _seed_source(
        app,
        bypass_engine,
        "sp3-recap-source@t.com",
    )
    with bypass_engine.begin() as conn:
        partner_id = conn.execute(text(
            "INSERT INTO language_partners("
            "user_id,display_name,native_language_code,created_at,updated_at"
            ") VALUES (:user,'Bob','fr',now(),now()) RETURNING id"
        ), {"user": user_id}).scalar_one()
        recap_id = conn.execute(text(
            "INSERT INTO partner_recaps("
            "user_id,partner_id,session_date,title,intake_source_id,"
            "created_at,updated_at) VALUES ("
            ":user,:partner,'2026-07-12','Cafe exchange',:source,now(),now()) "
            "RETURNING id"
        ), {
            "user": user_id,
            "partner": partner_id,
            "source": source_id,
        }).scalar_one()
    login(client, "sp3-recap-source@t.com", PW)

    page = client.get(
        f"/intake/{source_id}/candidates"
    ).get_data(as_text=True)

    assert 'data-sessionpad-source-kind="recap"' in page
    assert "Bob" in page
    assert "2026-07-12" in page
    assert "Cafe exchange" in page
    assert (
        f'href="/partners/{partner_id}/recaps/{recap_id}"'
        in page
    )

def test_non_sessionpad_candidate_review_keeps_the_existing_multi_card_page(
    app,
    client,
    bypass_engine,
):
    _, _, source_id, _ = _seed_source(
        app,
        bypass_engine,
        "sp3-generic@t.com",
        source_type="text",
    )
    login(client, "sp3-generic@t.com", PW)

    page = client.get(
        f"/intake/{source_id}/candidates"
    ).get_data(as_text=True)

    assert 'data-sessionpad-review="focused"' not in page
    assert "premier terme" in page
    assert "deuxieme terme" in page
    assert "一键入库" in page


def test_sessionpad_focused_review_renders_in_english(
    app,
    client,
    bypass_engine,
):
    _, _, source_id, _ = _seed_source(
        app,
        bypass_engine,
        "sp3-review-en@t.com",
        candidates=[("se reposer", None, None)],
    )
    login(client, "sp3-review-en@t.com", PW)
    client.post(
        "/ui-language",
        data={
            "ui_locale": "en",
            "next": f"/intake/{source_id}/candidates",
        },
    )

    page = client.get(
        f"/intake/{source_id}/candidates"
    ).get_data(as_text=True)

    assert "Review candidate words" in page
    assert "No context yet" in page
    assert "Use context as example draft" in page
    assert "Accept and finish" in page
    assert "暂时没有语境" not in page
    assert "candidate.sessionpad_" not in page
    assert "word.word" not in page

def test_editing_term_into_same_source_duplicate_keeps_queue_unchanged(
    app,
    client,
    bypass_engine,
):
    _, _, source_id, candidate_ids = _seed_source(
        app,
        bypass_engine,
        "sp3-edit-duplicate@t.com",
        candidates=[("alpha", None, None), ("beta", None, None)],
    )
    login(client, "sp3-edit-duplicate@t.com", PW)

    response = client.post(
        f"/intake/sessionpad/candidates/{candidate_ids[0]}/accept",
        data={"word": " BETA ", "context_excerpt": ""},
        headers={"HX-Request": "true"},
    )

    assert response.status_code == 200
    body = response.get_data(as_text=True)
    assert 'data-review-error="duplicate"' in body
    assert "同一次交换中已有这个候选" in body
    assert "alpha" in body
    with bypass_engine.connect() as conn:
        rows = conn.execute(text(
            "SELECT word,status FROM word_candidates "
            "WHERE source_id=:source ORDER BY id"
        ), {"source": source_id}).mappings().all()
    assert rows == [
        {"word": "alpha", "status": "pending"},
        {"word": "beta", "status": "pending"},
    ]

def test_commit_links_existing_word_created_after_candidate_acceptance(
    app,
    client,
    bypass_engine,
):
    _, list_id, source_id, candidate_ids = _seed_source(
        app,
        bypass_engine,
        "sp3-late-existing@t.com",
        candidates=[("nouveau", None, None)],
    )
    with bypass_engine.begin() as conn:
        conn.execute(text(
            "UPDATE word_candidates SET status='accepted' WHERE id=:candidate"
        ), {"candidate": candidate_ids[0]})
        word_id = conn.execute(text(
            "INSERT INTO words("
            "list_id,word,marked,due_date,interval,ease,reps,lapses"
            ") VALUES (:list,' NOUVEAU ',false,now(),1,2.5,0,0) RETURNING id"
        ), {"list": list_id}).scalar_one()
        conn.execute(text(
            "INSERT INTO definitions(word_id,meaning) "
            "VALUES (:word,'keep this meaning')"
        ), {"word": word_id})
    login(client, "sp3-late-existing@t.com", PW)

    response = client.post(f"/intake/{source_id}/commit")

    assert response.status_code == 302
    with bypass_engine.connect() as conn:
        linked_word_id = conn.execute(text(
            "SELECT word_id FROM word_candidates WHERE id=:candidate"
        ), {"candidate": candidate_ids[0]}).scalar_one()
        definition = conn.execute(text(
            "SELECT meaning FROM definitions WHERE word_id=:word"
        ), {"word": word_id}).scalar_one()
    assert linked_word_id == word_id
    assert definition == "keep this meaning"
