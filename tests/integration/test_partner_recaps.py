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


def _provision_learning_user(app, email, language_code="fr"):
    from app.services.provisioning import create_user_with_defaults

    with app.app_context():
        user_id, _ = create_user_with_defaults(
            email, "Tester", password=PW,
            learning_languages=[language_code],
        )
    return user_id


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


def test_for_me_expression_can_be_added_to_candidate_review(
    app, client, bypass_engine,
):
    user_id = _provision_learning_user(app, "recap-candidate@t.com")
    login(client, "recap-candidate@t.com", PW)
    partner_id = _create_partner(client)
    recap_id = _create_recap(client, partner_id)
    recap_url = f"/partners/{partner_id}/recaps/{recap_id}"
    added = client.post(f"{recap_url}/items", data={
        "side": "for_me",
        "kind": "expression",
        "content": "avoir hâte de",
        "csrf_token": _csrf(client, recap_url),
    }, follow_redirects=True)
    item_id = int(re.search(
        r'data-recap-item-id="(\d+)"', added.get_data(as_text=True),
    ).group(1))

    response = client.post(
        f"{recap_url}/items/{item_id}/add-candidate",
        data={"csrf_token": _csrf(client, recap_url)},
    )

    assert response.status_code == 302
    assert re.search(r"/intake/\d+/candidates$", response.headers["Location"])
    with bypass_engine.connect() as conn:
        row = conn.execute(text(
            "SELECT i.candidate_id, c.word, c.status, s.id AS source_id, "
            "s.user_id, s.source_type, s.language_code "
            "FROM partner_recap_items i "
            "JOIN word_candidates c ON c.id = i.candidate_id "
            "JOIN intake_sources s ON s.id = c.source_id "
            "WHERE i.id = :item_id"
        ), {"item_id": item_id}).mappings().one()
    assert row["candidate_id"] is not None
    assert row["word"] == "avoir hâte de"
    assert row["status"] == "pending"
    assert row["user_id"] == user_id
    assert row["source_type"] == "sessionpad"
    assert row["language_code"] == "fr"
    assert response.headers["Location"].endswith(
        f'/intake/{row["source_id"]}/candidates'
    )


def test_adding_same_recap_item_to_candidates_is_idempotent(
    app, client, bypass_engine,
):
    _provision_learning_user(app, "recap-candidate-twice@t.com")
    login(client, "recap-candidate-twice@t.com", PW)
    partner_id = _create_partner(client)
    recap_id = _create_recap(client, partner_id)
    recap_url = f"/partners/{partner_id}/recaps/{recap_id}"
    added = client.post(f"{recap_url}/items", data={
        "side": "for_me",
        "kind": "natural_phrase",
        "content": "J'ai hâte de te revoir.",
        "csrf_token": _csrf(client, recap_url),
    }, follow_redirects=True)
    item_id = int(re.search(
        r'data-recap-item-id="(\d+)"', added.get_data(as_text=True),
    ).group(1))
    action = f"{recap_url}/items/{item_id}/add-candidate"

    first = client.post(
        action, data={"csrf_token": _csrf(client, recap_url)},
    )
    second = client.post(
        action, data={"csrf_token": _csrf(client, recap_url)},
    )

    assert first.status_code == second.status_code == 302
    assert first.headers["Location"] == second.headers["Location"]
    with bypass_engine.connect() as conn:
        count = conn.execute(text(
            "SELECT count(*) FROM word_candidates c "
            "JOIN partner_recap_items i ON i.candidate_id = c.id "
            "WHERE i.id = :item_id"
        ), {"item_id": item_id}).scalar()
    assert count == 1


def test_recap_candidate_source_keeps_its_original_language(
    app, client, bypass_engine,
):
    from app.services.provisioning import create_user_with_defaults

    with app.app_context():
        user_id, _ = create_user_with_defaults(
            "recap-language-snapshot@t.com",
            "Tester",
            password=PW,
            learning_languages=["fr", "ja"],
        )
    login(client, "recap-language-snapshot@t.com", PW)
    partner_id = _create_partner(client)
    recap_id = _create_recap(client, partner_id)
    recap_url = f"/partners/{partner_id}/recaps/{recap_id}"

    first = client.post(f"{recap_url}/items", data={
        "side": "for_me",
        "kind": "expression",
        "content": "avoir hâte de",
        "csrf_token": _csrf(client, recap_url),
    }, follow_redirects=True)
    first_id = int(re.search(
        r'data-recap-item-id="(\d+)"', first.get_data(as_text=True),
    ).group(1))
    first_result = client.post(
        f"{recap_url}/items/{first_id}/add-candidate",
        data={"csrf_token": _csrf(client, recap_url)},
    )
    source_id = int(re.search(
        r"/intake/(\d+)/candidates$", first_result.headers["Location"],
    ).group(1))

    with bypass_engine.begin() as conn:
        conn.execute(text(
            "UPDATE language_partners SET native_language_code = 'ja' "
            "WHERE id = :partner_id AND user_id = :user_id"
        ), {"partner_id": partner_id, "user_id": user_id})

    second = client.post(f"{recap_url}/items", data={
        "side": "for_me",
        "kind": "expression",
        "content": "prendre son temps",
        "csrf_token": _csrf(client, recap_url),
    }, follow_redirects=True)
    item_ids = re.findall(
        r'data-recap-item-id="(\d+)"', second.get_data(as_text=True),
    )
    second_id = int(item_ids[-1])
    second_result = client.post(
        f"{recap_url}/items/{second_id}/add-candidate",
        data={"csrf_token": _csrf(client, recap_url)},
    )

    assert second_result.headers["Location"].endswith(
        f"/intake/{source_id}/candidates"
    )
    with bypass_engine.connect() as conn:
        source = conn.execute(text(
            "SELECT language_code, word_list_id FROM intake_sources "
            "WHERE id = :source_id"
        ), {"source_id": source_id}).fetchone()
        words = conn.execute(text(
            "SELECT word FROM word_candidates WHERE source_id = :source_id "
            "ORDER BY id"
        ), {"source_id": source_id}).scalars().all()
        list_language = conn.execute(text(
            "SELECT language_code FROM word_lists WHERE id = :list_id"
        ), {"list_id": source.word_list_id}).scalar()
    assert source.language_code == "fr"
    assert list_language == "fr"
    assert words == ["avoir hâte de", "prendre son temps"]


@pytest.mark.parametrize("side,kind", [
    ("for_me", "private_note"),
    ("for_me", "next_time"),
    ("for_partner", "expression"),
])
def test_non_learning_recap_items_cannot_be_added_to_candidates(
    app, client, bypass_engine, side, kind,
):
    user_id = _provision_learning_user(
        app, f"recap-ineligible-{side}-{kind}@t.com",
    )
    login(client, f"recap-ineligible-{side}-{kind}@t.com", PW)
    partner_id = _create_partner(client)
    recap_id = _create_recap(client, partner_id)
    recap_url = f"/partners/{partner_id}/recaps/{recap_id}"
    added = client.post(f"{recap_url}/items", data={
        "side": side,
        "kind": kind,
        "content": "不应进入候选词",
        "csrf_token": _csrf(client, recap_url),
    }, follow_redirects=True)
    panel = re.search(
        rf'data-recap-column="{side}".*?</section>',
        added.get_data(as_text=True), re.S,
    ).group()
    item_id = int(re.search(
        r'data-recap-item-id="(\d+)"', panel,
    ).group(1))

    response = client.post(
        f"{recap_url}/items/{item_id}/add-candidate",
        data={"csrf_token": _csrf(client, recap_url)},
        follow_redirects=True,
    )

    assert "这类记录不能加入候选词" in response.get_data(as_text=True)
    with bypass_engine.connect() as conn:
        count = conn.execute(text(
            "SELECT count(*) FROM intake_sources "
            "WHERE user_id = :user_id AND source_type = 'sessionpad'"
        ), {"user_id": user_id}).scalar()
    assert count == 0


def test_candidate_action_requires_partner_language_in_learning_settings(
    app, client, bypass_engine,
):
    user_id = provision_user(app, "recap-language-required@t.com", PW)
    login(client, "recap-language-required@t.com", PW)
    partner_id = _create_partner(client)
    recap_id = _create_recap(client, partner_id)
    recap_url = f"/partners/{partner_id}/recaps/{recap_id}"
    added = client.post(f"{recap_url}/items", data={
        "side": "for_me",
        "kind": "expression",
        "content": "avoir hâte de",
        "csrf_token": _csrf(client, recap_url),
    }, follow_redirects=True)
    item_id = int(re.search(
        r'data-recap-item-id="(\d+)"', added.get_data(as_text=True),
    ).group(1))

    response = client.post(
        f"{recap_url}/items/{item_id}/add-candidate",
        data={"csrf_token": _csrf(client, recap_url)},
        follow_redirects=True,
    )

    assert "请先在设置中把法语加入正在学" in response.get_data(as_text=True)


def test_other_user_cannot_add_recap_item_to_candidates(app, client):
    _provision_learning_user(app, "recap-candidate-owner@t.com")
    _provision_learning_user(app, "recap-candidate-other@t.com")
    login(client, "recap-candidate-owner@t.com", PW)
    partner_id = _create_partner(client)
    recap_id = _create_recap(client, partner_id)
    recap_url = f"/partners/{partner_id}/recaps/{recap_id}"
    added = client.post(f"{recap_url}/items", data={
        "side": "for_me",
        "kind": "expression",
        "content": "private phrase",
        "csrf_token": _csrf(client, recap_url),
    }, follow_redirects=True)
    item_id = int(re.search(
        r'data-recap-item-id="(\d+)"', added.get_data(as_text=True),
    ).group(1))
    client.get("/logout")
    login(client, "recap-candidate-other@t.com", PW)

    response = client.post(
        f"{recap_url}/items/{item_id}/add-candidate",
        data={"csrf_token": _csrf(client, "/partners/new")},
    )
    assert response.status_code == 404


def test_database_rejects_cross_user_sessionpad_candidate_links(
    bypass_engine,
):
    user_a = make_user(bypass_engine, "recap-link-owner@t.com")
    user_b = make_user(bypass_engine, "recap-link-other@t.com")
    with bypass_engine.begin() as conn:
        partner_id = conn.execute(text(
            "INSERT INTO language_partners("
            "user_id, display_name, created_at, updated_at) "
            "VALUES (:user_id, 'Owner partner', now(), now()) RETURNING id"
        ), {"user_id": user_a}).scalar()
        recap_id = conn.execute(text(
            "INSERT INTO partner_recaps("
            "user_id, partner_id, session_date, created_at, updated_at) "
            "VALUES (:user_id, :partner_id, '2026-07-10', now(), now()) "
            "RETURNING id"
        ), {"user_id": user_a, "partner_id": partner_id}).scalar()
        item_id = conn.execute(text(
            "INSERT INTO partner_recap_items("
            "user_id, recap_id, side, kind, content, created_at, updated_at) "
            "VALUES (:user_id, :recap_id, 'for_me', 'expression', "
            "'private', now(), now()) RETURNING id"
        ), {"user_id": user_a, "recap_id": recap_id}).scalar()
        list_id = conn.execute(text(
            "INSERT INTO word_lists(user_id, name, language_code, created_at) "
            "VALUES (:user_id, 'FR', 'fr', now()) RETURNING id"
        ), {"user_id": user_b}).scalar()
        source_id = conn.execute(text(
            "INSERT INTO intake_sources("
            "user_id, source_type, language_code, word_list_id, status, "
            "total_segments, total_candidates, created_at) "
            "VALUES (:user_id, 'sessionpad', 'fr', :list_id, 'done', "
            "0, 1, now()) RETURNING id"
        ), {"user_id": user_b, "list_id": list_id}).scalar()
        candidate_id = conn.execute(text(
            "INSERT INTO word_candidates("
            "source_id, user_id, word, status, created_at) "
            "VALUES (:source_id, :user_id, 'cross-user', 'pending', now()) "
            "RETURNING id"
        ), {
            "source_id": source_id,
            "user_id": user_b,
        }).scalar()

    with pytest.raises(DBAPIError):
        with bypass_engine.begin() as conn:
            conn.execute(text(
                "UPDATE partner_recaps SET intake_source_id = :source_id "
                "WHERE id = :recap_id"
            ), {"source_id": source_id, "recap_id": recap_id})

    with pytest.raises(DBAPIError):
        with bypass_engine.begin() as conn:
            conn.execute(text(
                "UPDATE partner_recap_items SET candidate_id = :candidate_id "
                "WHERE id = :item_id"
            ), {"candidate_id": candidate_id, "item_id": item_id})
