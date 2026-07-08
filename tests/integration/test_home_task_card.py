"""首页不渲染每日任务卡。

任务聚合服务暂时保留为 dormant code；首页先回到「第一眼是复习词卡」。
"""

from tests.helpers import provision_user, login, make_word, make_review_log

PW = "pw12345678"


def test_home_does_not_render_task_card(app, client, bypass_engine):
    provision_user(app, "home@t.com", PW)
    login(client, "home@t.com", PW)

    resp = client.get("/")

    assert resp.status_code == 200
    body = resp.get_data(as_text=True)
    assert "task-card" not in body
    assert "今日任务" not in body


def test_home_hidden_task_card_does_not_leak_other_user_progress(
        app, client, bypass_engine):
    """A 用户复习了 5 次，B 首页不应出现任务卡进度数字。"""
    uid_a = provision_user(app, "iso-a@t.com", PW)
    provision_user(app, "iso-b@t.com", PW)
    list_id, word_id = make_word(bypass_engine, uid_a, "cat")
    for _ in range(5):
        make_review_log(bypass_engine, uid_a, word_id)

    login(client, "iso-b@t.com", PW)
    body = client.get("/").get_data(as_text=True)

    assert "5/10" not in body
    assert "0/10" not in body
