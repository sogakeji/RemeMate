"""阶段三：词库 CRUD + RLS 隔离 + 复习递推 + stats（走 HTTP，真实 RLS 路径）。"""
from sqlalchemy import text

from tests.helpers import provision_user, login, make_user, make_word

PW = "pw12345678"


def test_create_list_and_add_word(app, client, bypass_engine):
    provision_user(app, "a@t.com", PW)
    login(client, "a@t.com", PW)

    # 建词表
    client.post("/words", data={"name": "法语核心", "language_code": "fr"})
    page = client.get("/words").get_data(as_text=True)
    assert "法语核心" in page

    # 取 list_id（bypass 读）
    with bypass_engine.connect() as c:
        list_id = c.execute(text("SELECT id FROM word_lists WHERE name='法语核心'")).scalar()

    # 加词
    client.post(f"/words/{list_id}", data={"word": "décollage", "meaning": "起飞"})
    detail = client.get(f"/words/{list_id}").get_data(as_text=True)
    assert "décollage" in detail and "起飞" in detail


def test_cross_user_list_isolation(app, client, bypass_engine):
    # 用户 B 的词表（用 bypass 造），用户 A 登录后不可见、不可访问
    b = make_user(bypass_engine, "b@t.com")
    b_list, _ = make_word(bypass_engine, b)        # B 的词表 + 词

    provision_user(app, "a@t.com", PW)
    login(client, "a@t.com", PW)

    assert client.get(f"/words/{b_list}").status_code == 404   # 越权访问被拦
    assert client.get("/words").status_code == 200
    assert "b@t.com" not in client.get("/words").get_data(as_text=True)


def test_review_grade_updates_sm2(app, client, bypass_engine):
    provision_user(app, "r@t.com", PW)
    login(client, "r@t.com", PW)
    client.post("/words", data={"name": "L", "language_code": "fr"})
    with bypass_engine.connect() as c:
        list_id = c.execute(text("SELECT id FROM word_lists WHERE name='L'")).scalar()
    client.post(f"/words/{list_id}", data={"word": "w1", "meaning": "m"})
    with bypass_engine.connect() as c:
        word_id = c.execute(text("SELECT id FROM words WHERE word='w1'")).scalar()

    # 复习页应展示到期词
    assert "w1" in client.get("/review").get_data(as_text=True)

    # 评 easy → 通过：reps 0→1，due 推到未来，写一条 ReviewLog
    client.post(f"/review/{word_id}/grade", data={"button": "easy"})
    with bypass_engine.connect() as c:
        reps, due = c.execute(text(
            "SELECT reps, due_date FROM words WHERE id=:i"), {"i": word_id}).fetchone()
        logs = c.execute(text(
            "SELECT count(*) FROM review_logs WHERE word_id=:i"), {"i": word_id}).scalar()
    assert reps == 1
    assert logs == 1
    from datetime import datetime
    assert due > datetime.utcnow()      # 不再到期


def test_review_grade_other_users_word_404(app, client, bypass_engine):
    b = make_user(bypass_engine, "b@t.com")
    _, b_word = make_word(bypass_engine, b)
    provision_user(app, "a@t.com", PW)
    login(client, "a@t.com", PW)
    assert client.post(f"/review/{b_word}/grade", data={"button": "easy"}).status_code == 404


def test_stats_counts(app, client, bypass_engine):
    provision_user(app, "s@t.com", PW)
    login(client, "s@t.com", PW)
    client.post("/words", data={"name": "L", "language_code": "fr"})
    with bypass_engine.connect() as c:
        list_id = c.execute(text("SELECT id FROM word_lists WHERE name='L'")).scalar()
    client.post(f"/words/{list_id}", data={"word": "w1", "meaning": "m"})
    client.post(f"/words/{list_id}", data={"word": "w2", "meaning": "m"})

    page = client.get("/stats").get_data(as_text=True)
    assert "总词数：2" in page
    assert "今日到期：2" in page


def test_delete_list(app, client, bypass_engine):
    provision_user(app, "d@t.com", PW)
    login(client, "d@t.com", PW)
    client.post("/words", data={"name": "ToDelete", "language_code": "fr"})
    with bypass_engine.connect() as c:
        list_id = c.execute(text("SELECT id FROM word_lists WHERE name='ToDelete'")).scalar()
    client.post(f"/words/{list_id}/delete")
    assert "ToDelete" not in client.get("/words").get_data(as_text=True)
