"""Detail 页 N+1 回归（review 2026-06-23 M6）。

get_word_list(eager=True) 用 selectinload 预加载 words.definitions；详情页遍历
wl.words / w.definitions 不再逐词触发查询。用查询计数断言 definitions 只查一次。
"""
from sqlalchemy import event, text

from app.extensions import db
from tests.helpers import login, provision_user

PW = "pw12345678"


def test_detail_page_no_n_plus_one_definitions(app, client, bypass_engine):
    provision_user(app, "n1@t.com", PW)
    login(client, "n1@t.com", PW)
    client.post("/words", data={"name": "N", "language_code": "fr"})
    with bypass_engine.connect() as c:
        lid = c.execute(text("SELECT id FROM word_lists WHERE name='N'")).scalar()

    # 5 个词、各带 1 条释义。lazy 路径会逐词查 → 5 次 definitions 查询；
    # eager（selectinload）应只查一次（definitions IN (...)）。
    for i in range(5):
        client.post(f"/words/{lid}", data={"word": f"w{i}", "meaning": "m"})

    counter = {"defs": 0}

    with app.app_context():
        @event.listens_for(db.engine, "before_cursor_execute")
        def _count(conn, cursor, statement, params, context, executemany):
            s = statement.lower()
            if "from definitions" in s and "select" in s:
                counter["defs"] += 1

    try:
        page = client.get(f"/words/{lid}").get_data(as_text=True)
    finally:
        with app.app_context():
            event.remove(db.engine, "before_cursor_execute", _count)

    assert counter["defs"] == 1, counter        # 不逐词 N+1
    # 页面确实渲染了所有词与释义（确认预加载真的发生了，不是空集合的 0 次）
    for i in range(5):
        assert f"w{i}" in page
    assert "m" in page