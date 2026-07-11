"""SessionPad B8: optional, fail-soft AI recap summaries."""
import re

from sqlalchemy import text

from app.services import llm
from tests.helpers import login, provision_user


PW = "pw12345678"


def _csrf(client, path):
    page = client.get(path).get_data(as_text=True)
    return re.search(
        r'name="csrf_token"[^>]*value="([^"]+)"', page,
    ).group(1)


def _recap_with_items(client):
    partner = client.post("/partners", data={
        "display_name": "Pierre",
        "native_language_code": "fr",
        "learning_language_code": "zh",
        "private_note": "伙伴档案私密内容",
        "csrf_token": _csrf(client, "/partners/new"),
    })
    partner_id = int(partner.headers["Location"].rstrip("/").rsplit("/", 1)[-1])
    recap = client.post(f"/partners/{partner_id}/recaps", data={
        "session_date": "2026-07-11",
        "title": "周五语言交换",
        "csrf_token": _csrf(client, f"/partners/{partner_id}/recaps/new"),
    })
    recap_id = int(recap.headers["Location"].rstrip("/").rsplit("/", 1)[-1])
    recap_url = f"/partners/{partner_id}/recaps/{recap_id}"
    for side, kind, content in [
        ("for_me", "expression", "avoir hâte de"),
        ("for_me", "private_note", "Pierre 下个月准备 HSK"),
        ("for_partner", "correction", "我很同意 → 我很赞同"),
    ]:
        client.post(f"{recap_url}/items", data={
            "side": side,
            "kind": kind,
            "content": content,
            "csrf_token": _csrf(client, recap_url),
        })
    return partner_id, recap_id, recap_url


def test_owner_generates_persisted_summary_without_sending_private_note(
    app, client, bypass_engine, monkeypatch,
):
    user_id = provision_user(app, "summary-owner@t.com", PW)
    login(client, "summary-owner@t.com", PW)
    partner_id, recap_id, recap_url = _recap_with_items(client)
    captured = {}

    def fake_chat(messages, **kwargs):
        captured["messages"] = messages
        captured["kwargs"] = kwargs
        return llm.LLMResult(
            '{"gains":["学会更自然地表达期待"],'
            '"depth":"讨论进入了真实使用语境。",'
            '"topics":["期待","自然表达"],'
            '"next_steps":["下次主动使用 avoir hâte de"]}',
            31, 19, "fake", "fake-summary",
        )

    monkeypatch.setattr("app.services.recap_summaries.llm.chat", fake_chat)
    response = client.post(f"{recap_url}/summary", data={
        "csrf_token": _csrf(client, recap_url),
    }, follow_redirects=True)

    body = response.get_data(as_text=True)
    assert response.status_code == 200
    assert "本次收获" in body
    assert "学会更自然地表达期待" in body
    assert "讨论进入了真实使用语境" in body
    assert "下次主动使用 avoir hâte de" in body
    prompt = str(captured["messages"])
    assert "avoir hâte de" in prompt
    assert "我很同意 → 我很赞同" in prompt
    assert "Pierre 下个月准备 HSK" not in prompt
    assert captured["kwargs"] == {"task": "general", "json_mode": True}

    with bypass_engine.connect() as conn:
        stored = conn.execute(text(
            "SELECT ai_summary, ai_summary_source_hash, "
            "ai_summary_generated_at FROM partner_recaps WHERE id=:id"
        ), {"id": recap_id}).mappings().one()
        usage = conn.execute(text(
            "SELECT feature, prompt_tokens, completion_tokens "
            "FROM token_usage_log WHERE user_id=:user_id"
        ), {"user_id": user_id}).mappings().one()
        corrections = conn.execute(text(
            "SELECT corrections_today FROM user_quota WHERE user_id=:user_id"
        ), {"user_id": user_id}).scalar()
    assert stored["ai_summary"]["topics"] == ["期待", "自然表达"]
    assert len(stored["ai_summary_source_hash"]) == 64
    assert stored["ai_summary_generated_at"] is not None
    assert usage == {
        "feature": "sessionpad_summary",
        "prompt_tokens": 31,
        "completion_tokens": 19,
    }
    assert corrections == 0

    def must_not_call(*args, **kwargs):
        raise AssertionError("current summary must not call the provider again")

    monkeypatch.setattr("app.services.recap_summaries.llm.chat", must_not_call)
    repeated = client.post(f"{recap_url}/summary", data={
        "csrf_token": _csrf(client, recap_url),
    }, follow_redirects=True)
    assert "当前总结已是最新" in repeated.get_data(as_text=True)
    with bypass_engine.connect() as conn:
        assert conn.execute(text(
            "SELECT count(*) FROM token_usage_log WHERE user_id=:user_id"
        ), {"user_id": user_id}).scalar() == 1

    client.post(f"{recap_url}/items", data={
        "side": "for_me",
        "kind": "natural_phrase",
        "content": "J'ai hâte de te revoir.",
        "csrf_token": _csrf(client, recap_url),
    })
    assert "内容已更新，可重新总结" in client.get(recap_url).get_data(as_text=True)


def test_summary_failure_preserves_recap_and_stores_no_fake_result(
    app, client, bypass_engine, monkeypatch,
):
    provision_user(app, "summary-down@t.com", PW)
    login(client, "summary-down@t.com", PW)
    _, recap_id, recap_url = _recap_with_items(client)

    def unavailable(*args, **kwargs):
        raise llm.AllProvidersDown("down")

    monkeypatch.setattr("app.services.recap_summaries.llm.chat", unavailable)
    response = client.post(f"{recap_url}/summary", data={
        "csrf_token": _csrf(client, recap_url),
    }, follow_redirects=True)

    body = response.get_data(as_text=True)
    assert response.status_code == 200
    assert "AI 总结暂时不可用，不影响已记录内容" in body
    assert "avoir hâte de" in body
    with bypass_engine.connect() as conn:
        row = conn.execute(text(
            "SELECT ai_summary FROM partner_recaps WHERE id=:id"
        ), {"id": recap_id}).scalar()
        usage_count = conn.execute(text(
            "SELECT count(*) FROM token_usage_log"
        )).scalar()
    assert row is None
    assert usage_count == 0


def test_other_user_cannot_generate_summary(app, client, monkeypatch):
    provision_user(app, "summary-a@t.com", PW)
    provision_user(app, "summary-b@t.com", PW)
    login(client, "summary-a@t.com", PW)
    partner_id, recap_id, recap_url = _recap_with_items(client)
    client.get("/logout")
    login(client, "summary-b@t.com", PW)
    called = False

    def fake_chat(*args, **kwargs):
        nonlocal called
        called = True

    monkeypatch.setattr("app.services.recap_summaries.llm.chat", fake_chat)
    response = client.post(
        f"/partners/{partner_id}/recaps/{recap_id}/summary",
        data={"csrf_token": _csrf(client, "/partners/new")},
    )

    assert response.status_code == 404
    assert called is False
