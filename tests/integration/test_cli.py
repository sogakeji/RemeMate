"""CLI create-user 后用户能登录（端到端）。"""
import re


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
