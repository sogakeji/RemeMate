"""Write/correction quota: incomplete AI results must not consume completion slots."""
from concurrent.futures import ThreadPoolExecutor
from threading import Barrier

import pytest
from sqlalchemy import text

from tests.helpers import login, provision_user
from tests.integration.test_write import _setup_user_with_word

PW = "pw12345678"
SECRET_SENTENCE = "Un essai secret-quota-xyz."


def _quota_row(bypass_engine, uid):
    with bypass_engine.connect() as conn:
        corrections = conn.execute(text(
            "SELECT corrections_today FROM user_quota WHERE user_id=:u"
        ), {"u": uid}).scalar()
        tokens = conn.execute(text(
            "SELECT COALESCE(tokens_used_today, 0) FROM user_quota WHERE user_id=:u"
        ), {"u": uid}).scalar()
        usage = conn.execute(text(
            "SELECT feature, prompt_tokens, completion_tokens "
            "FROM token_usage_log WHERE user_id=:u ORDER BY id"
        ), {"u": uid}).mappings().all()
    return corrections or 0, tokens or 0, list(usage)


@pytest.mark.parametrize(
    ("llm_setup", "error_code"),
    [
        ({"timeout": True}, "timeout"),
        ({"content": '{"title":"nope"}'}, "invalid_schema"),
        ({"content": "完全不是 JSON"}, "parse_error"),
        ({"content": ""}, "empty_result"),
        ({"content": '{"corrected":"   ","errors":[]}'}, "empty_result"),
    ],
)
def test_incomplete_correction_does_not_consume_completion_quota(
        app, client, bypass_engine, fake_llm, llm_setup, error_code):
    uid, wid = _setup_user_with_word(
        app, client, bypass_engine, f"quota-{error_code}@t.com",
    )
    fake_llm.update(llm_setup)
    fake_llm["reinstall"]()

    resp = client.post("/write/submit", data={
        "word_id": wid,
        "sentence": SECRET_SENTENCE,
    })
    page = resp.get_data(as_text=True)
    corrections, tokens_used, usage = _quota_row(bypass_engine, uid)

    assert resp.status_code == 200
    assert "保存" not in page
    assert "AI 批改暂时不可用" in page
    assert corrections == 0
    if error_code == "timeout":
        assert usage == []
        assert tokens_used == 0
    else:
        cost_rows = [row for row in usage if row["feature"] == "correction"]
        assert cost_rows
        assert cost_rows[0]["prompt_tokens"] == 10
        assert cost_rows[0]["completion_tokens"] == 20
        assert tokens_used == 30
        assert all(row["feature"] != "nsfw" for row in usage)


def test_successful_correction_consumes_completion_quota_once(
        app, client, bypass_engine, fake_llm):
    uid, wid = _setup_user_with_word(
        app, client, bypass_engine, "quota-success-once@t.com",
    )

    resp = client.post("/write/submit", data={
        "word_id": wid,
        "sentence": "Un essai.",
    })
    corrections, _, usage = _quota_row(bypass_engine, uid)
    features = [row["feature"] for row in usage]

    assert resp.status_code == 200
    assert "phrase corrigée" in resp.get_data(as_text=True)
    assert corrections == 1
    assert features.count("correction") == 1
    assert "nsfw" in features


def test_invalid_schema_then_retry_success_consumes_quota_once(
        app, client, bypass_engine, fake_llm):
    from app.services import llm

    uid, wid = _setup_user_with_word(
        app, client, bypass_engine, "quota-retry-once@t.com",
    )

    class P:
        def __init__(self, name, content):
            self.name = name
            self.content = content
            self.calls = 0

        def call(self, messages, *, timeout, json_mode=False):
            self.calls += 1
            return llm.LLMResult(self.content, 10, 20, self.name, "fake-model")

    primary = P("primary", '{"oops":true}')
    backup = P("backup", fake_llm["content"])
    nsfw_chain = llm.get_chain("nsfw")
    llm.set_registry({
        "correction": [primary, backup],
        "nsfw": nsfw_chain,
        "general": [primary, backup],
    })

    resp = client.post("/write/submit", data={
        "word_id": wid,
        "sentence": "Un essai.",
    })
    corrections, tokens_used, usage = _quota_row(bypass_engine, uid)
    correction_rows = [row for row in usage if row["feature"] == "correction"]

    assert resp.status_code == 200
    assert "phrase corrigée" in resp.get_data(as_text=True)
    assert primary.calls == 1 and backup.calls == 1
    assert corrections == 1
    assert len(correction_rows) == 1
    assert correction_rows[0]["prompt_tokens"] == 20
    assert correction_rows[0]["completion_tokens"] == 40
    assert tokens_used >= 60


def test_duplicate_submit_after_success_is_second_completion(
        app, client, bypass_engine, fake_llm):
    """A new user submit is a new completion; internal retries must not double-count."""
    uid, wid = _setup_user_with_word(
        app, client, bypass_engine, "quota-dup-submit@t.com",
    )
    client.post("/write/submit", data={"word_id": wid, "sentence": "Un essai."})
    client.post("/write/submit", data={"word_id": wid, "sentence": "Un essai."})
    corrections, _, usage = _quota_row(bypass_engine, uid)
    assert corrections == 2
    assert [row["feature"] for row in usage].count("correction") == 2


def test_concurrent_successful_submits_never_exceed_daily_limit(
        app, client, bypass_engine, fake_llm):
    email = "quota-concurrent@t.com"
    uid, wid = _setup_user_with_word(app, client, bypass_engine, email)
    barrier = Barrier(6)

    def submit():
        with app.test_client() as thread_client:
            login(thread_client, email, PW)
            barrier.wait(timeout=10)
            return thread_client.post("/write/submit", data={
                "word_id": wid,
                "sentence": "Un essai.",
            })

    with ThreadPoolExecutor(max_workers=6) as pool:
        futures = [pool.submit(submit) for _ in range(6)]
        responses = [future.result(timeout=30) for future in futures]

    corrections, _, _ = _quota_row(bypass_engine, uid)
    bodies = [resp.get_data(as_text=True) for resp in responses]
    accepted = sum("phrase corrigée" in body for body in bodies)
    blocked = sum("额度" in body for body in bodies)

    assert all(resp.status_code == 200 for resp in responses)
    assert corrections == 3
    assert accepted == 3
    assert blocked == 3


def test_incomplete_correction_logs_are_redacted(app, client, bypass_engine, fake_llm, caplog):
    uid, wid = _setup_user_with_word(
        app, client, bypass_engine, "quota-log-redact@t.com",
    )
    fake_llm["content"] = '{"title":"nope"}'
    fake_llm["reinstall"]()

    with caplog.at_level("INFO", logger="app.services.writing"):
        client.post("/write/submit", data={
            "word_id": wid,
            "sentence": SECRET_SENTENCE,
        })

    text = caplog.text
    assert "write_correction_failed" in text
    assert "invalid_schema" in text
    assert "prompt_tokens=" in text
    assert SECRET_SENTENCE not in text
    assert '{"title":"nope"}' not in text
    assert "sk-" not in text
