"""CLI create-user 后用户能登录（端到端）。"""
import re

import pytest
from cryptography.fernet import Fernet
from sqlalchemy import text


def test_create_user_cli_then_login(app, client, runner):
    result = runner.invoke(args=["create-user", "--email", "cli@t.com", "--name", "Cli"])
    assert result.exit_code == 0
    m = re.search(r"初始密码：(\S+)", result.output)
    assert m, f"未在输出解析到密码：{result.output!r}"
    password = m.group(1)

    resp = client.post("/login", data={"email": "cli@t.com", "password": password})
    assert resp.status_code == 302
    assert resp.headers["Location"].endswith("/")


def test_create_user_cli_duplicate_fails(runner):
    runner.invoke(args=["create-user", "--email", "dup@t.com", "--name", "A"])
    result = runner.invoke(args=["create-user", "--email", "dup@t.com", "--name", "B"])
    assert result.exit_code != 0
    assert "已存在" in result.output


def test_create_user_cli_can_preset_chinese_and_french_feedback(
        runner, bypass_engine):
    result = runner.invoke(args=[
        "create-user", "--email", "friend@t.com", "--name", "Friend",
        "--language", "zh", "--feedback-language", "fr",
        "--password", "pw12345678",
    ])
    assert result.exit_code == 0
    assert "正在学：中文" in result.output
    assert "母语：法语" in result.output
    with bypass_engine.connect() as c:
        row = c.execute(text(
            "SELECT u.current_language, u.learning_languages, s.feedback_language "
            "FROM users u JOIN user_settings s ON s.user_id=u.id "
            "WHERE u.email='friend@t.com'"
        )).one()
        lists = c.execute(text(
            "SELECT language_code FROM word_lists wl JOIN users u ON u.id=wl.user_id "
            "WHERE u.email='friend@t.com'"
        )).scalars().all()
    assert row == ("zh", "zh", "fr")
    assert lists == ["zh"]


def test_create_user_cli_rejects_unknown_language(runner):
    result = runner.invoke(args=[
        "create-user", "--email", "badlang@t.com", "--name", "Bad",
        "--language", "klingon",
    ])
    assert result.exit_code != 0
    assert "未知语言" in result.output


def test_doctor_reports_core_checks(runner):
    result = runner.invoke(args=["doctor"])
    assert result.exit_code == 0
    assert "[OK] app database" in result.output
    assert "[OK] dispatch database" in result.output
    assert "[OK] migrate database" in result.output
    assert "[OK] migrations" in result.output
    assert "admin account" in result.output
    assert "LLM correction" in result.output


def test_doctor_reports_active_admin(runner):
    runner.invoke(args=[
        "create-user", "--email", "admin@t.com", "--name", "Admin", "--admin",
    ])

    result = runner.invoke(args=["doctor"])

    assert result.exit_code == 0
    assert "[OK] admin account: 1 active" in result.output


def test_doctor_warns_invalid_data_encryption_key(app, runner):
    app.config["DATA_ENCRYPTION_KEY"] = "not-a-fernet-key"

    result = runner.invoke(args=["doctor"])

    assert result.exit_code == 0
    assert "[WARN] DATA_ENCRYPTION_KEY" in result.output
    assert "invalid Fernet key" in result.output


def test_doctor_warns_missing_dictionary_dir(app, runner):
    app.config["DICTIONARY_DATA_DIR"] = None
    result = runner.invoke(args=["doctor"])
    assert result.exit_code == 0
    assert "[WARN] reading dictionaries" in result.output
    assert "DICTIONARY_DATA_DIR not set" in result.output


def test_doctor_reports_dictionary_dir_ok(app, runner, tmp_path):
    import json
    for lc in ("zh", "en", "ja", "fr"):
        d = tmp_path / lc
        d.mkdir(parents=True)
        (d / "entries.json").write_text(json.dumps({}), encoding="utf-8")
    app.config["DICTIONARY_DATA_DIR"] = str(tmp_path)
    result = runner.invoke(args=["doctor"])
    assert "[OK] reading dictionaries" in result.output


def test_doctor_strict_fails_on_warn(app, runner):
    app.config["DICTIONARY_DATA_DIR"] = None
    result = runner.invoke(args=["doctor", "--strict"])
    assert result.exit_code != 0


def test_doctor_registration_email_disabled_is_not_a_warning(app, runner):
    app.config.update(
        OPEN_REGISTRATION_ENABLED=False,
        RESEND_API_KEY=None,
        AUTH_EMAIL_FROM=None,
        PUBLIC_BASE_URL=None,
    )

    result = runner.invoke(args=["doctor"])

    assert result.exit_code == 0
    assert "[OK] registration email: disabled" in result.output
    assert "[WARN] registration email" not in result.output

    strict_result = runner.invoke(args=["doctor", "--strict"])
    assert "[OK] registration email: disabled" in strict_result.output
    assert "[WARN] registration email" not in strict_result.output


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("RESEND_API_KEY", None),
        ("RESEND_API_KEY", "CHANGE_ME"),
        ("AUTH_EMAIL_FROM", None),
        ("AUTH_EMAIL_FROM", "CHANGE_ME"),
        ("AUTH_EMAIL_FROM", "not-an-email"),
        ("PUBLIC_BASE_URL", None),
        ("PUBLIC_BASE_URL", "CHANGE_ME"),
        ("PUBLIC_BASE_URL", "http://example.test"),
        ("PUBLIC_BASE_URL", "https://user:pass@example.test"),
        ("PUBLIC_BASE_URL", "https://example.test:notaport"),
        ("PUBLIC_BASE_URL", "https://example.test/path"),
    ],
)
def test_doctor_strict_warns_invalid_registration_email_config(
        app, runner, field, value):
    app.config.update(
        OPEN_REGISTRATION_ENABLED=True,
        RESEND_API_KEY="re_test_key",
        AUTH_EMAIL_FROM="RemeMate <no-reply@example.test>",
        PUBLIC_BASE_URL="https://example.test",
    )
    app.config[field] = value

    result = runner.invoke(args=["doctor", "--strict"])

    assert result.exit_code != 0
    assert "[WARN] registration email" in result.output
    if isinstance(value, str):
        assert value not in result.output


def test_doctor_strict_accepts_valid_registration_email_config(
        app, runner, tmp_path, monkeypatch):
    app.config.update(
        OPEN_REGISTRATION_ENABLED=True,
        RESEND_API_KEY="re_test_key",
        AUTH_EMAIL_FROM="RemeMate <no-reply@example.test>",
        PUBLIC_BASE_URL="https://example.test",
        SECRET_KEY="s" * 32,
        DATA_ENCRYPTION_KEY=Fernet.generate_key().decode(),
        DICTIONARY_DATA_DIR=str(tmp_path),
    )
    for language in ("zh", "en", "ja", "fr"):
        (tmp_path / language).mkdir()
    monkeypatch.setattr("cli.commands.llm.get_chain", lambda _name: object())

    created = runner.invoke(args=[
        "create-user", "--email", "doctor-admin@t.com", "--name", "Doctor",
        "--admin", "--password", "pw12345678",
    ])
    assert created.exit_code == 0

    result = runner.invoke(args=["doctor", "--strict"])

    assert result.exit_code == 0
    assert "[OK] registration email RESEND_API_KEY: configured" in result.output
    assert "[OK] registration email AUTH_EMAIL_FROM: configured" in result.output
    assert "[OK] registration email PUBLIC_BASE_URL: configured" in result.output
