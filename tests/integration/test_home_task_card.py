"""首页任务卡片的集成测试。"""
from sqlalchemy import text

from tests.helpers import provision_user, login, make_word, make_review_log

PW = "pw12345678"


def test_home_injects_task_card(app, client, bypass_engine):
    """首页 `/` 注入任务卡，含 5 项任务的中文标题。"""
    provision_user(app, "home@t.com", PW)
    login(client, "home@t.com", PW)
    resp = client.get("/")
    assert resp.status_code == 200
    body = resp.data.decode()
    assert "task-card" in body
    assert "复习单词" in body
    assert "造一句句子" in body
    assert "写三行日记" in body
    # 5 项 slug 全出现
    assert "复习单词" in body and "导入单词" in body and "阅读 1%" in body


def test_task_card_isolated_per_user(app, client, bypass_engine):
    """A 用户复习了 5 次，B 登录看到的复习进度仍是 0。"""
    uid_a = provision_user(app, "iso-a@t.com", PW)
    provision_user(app, "iso-b@t.com", PW)
    list_id, word_id = make_word(bypass_engine, uid_a, "cat")
    for _ in range(5):
        make_review_log(bypass_engine, uid_a, word_id)
    login(client, "iso-b@t.com", PW)
    body = client.get("/").get_data(as_text=True)
    assert "0/10" in body          # B 看到 0/10
    assert "5/10" not in body      # 不会看到 A 的 5/10


def test_task_card_reflects_progress(app, client, bypass_engine):
    """用户复习了 3 次，首页显示 3/10。"""
    uid = provision_user(app, "prog@t.com", PW)
    list_id, word_id = make_word(bypass_engine, uid, "cat")
    for _ in range(3):
        make_review_log(bypass_engine, uid, word_id)
    login(client, "prog@t.com", PW)
    body = client.get("/").get_data(as_text=True)
    assert "3/10" in body