"""CLI create-user 后用户能登录（端到端）。"""
import re
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
