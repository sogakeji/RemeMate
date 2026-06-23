"""第三层 RLS 本层测试（绕过 service，直连 DB、用 app 角色）。

回归 review 2026-06-23 的 A1 各子项：deny-all / FORCE / fail-closed / 公开句例外 /
公开句写保护 / 连接复用。
"""
from sqlalchemy import text

from tests.helpers import (
    make_user, make_word, make_output_entry, make_review_log, set_uid,
)


def test_rls_blocks_raw_query_without_service_layer(app_engine, bypass_engine):
    """A1：service 漏写 user_id 过滤时，RLS 兜底拦截跨用户裸查询。"""
    a = make_user(bypass_engine, "a@t.com")
    b = make_user(bypass_engine, "b@t.com")
    make_word(bypass_engine, a)

    with app_engine.connect() as conn:
        set_uid(conn, b)
        rows = conn.execute(text("SELECT * FROM words")).fetchall()
        assert rows == []                      # b 看不到 a 的词
        set_uid(conn, a)
        rows = conn.execute(text("SELECT * FROM words")).fetchall()
        assert len(rows) == 1                  # a 看得到自己的


def test_rls_enabled_tables_not_deny_all_for_owner(app_engine, bypass_engine):
    """A1a：ENABLE 但漏建 policy 会让本人也读空——验证本人能读自己的数据。"""
    a = make_user(bypass_engine, "a@t.com")
    _, word_id = make_word(bypass_engine, a)
    make_review_log(bypass_engine, a, word_id)
    make_output_entry(bypass_engine, a, word_id, is_public=False)

    with app_engine.connect() as conn:
        set_uid(conn, a)
        assert conn.execute(text("SELECT count(*) FROM review_logs")).scalar() == 1
        assert conn.execute(text("SELECT count(*) FROM output_entries")).scalar() == 1


def test_rls_unset_guc_fails_closed(app_engine, bypass_engine):
    """A1d：GUC 未设置 → 读空而非 500。"""
    a = make_user(bypass_engine, "a@t.com")
    make_word(bypass_engine, a)
    with app_engine.connect() as conn:
        # 不调 set_uid
        rows = conn.execute(text("SELECT * FROM words")).fetchall()
        assert rows == []


def test_rls_empty_guc_fails_closed(app_engine, bypass_engine):
    """teardown 把 GUC 置空字符串后，''::int 不能报错（NULLIF 保护）。"""
    a = make_user(bypass_engine, "a@t.com")
    make_word(bypass_engine, a)
    with app_engine.connect() as conn:
        set_uid(conn, None)                    # 置空字符串
        rows = conn.execute(text("SELECT * FROM words")).fetchall()
        assert rows == []                      # 不抛 invalid integer，安全读空


def test_output_entries_public_visible_across_users(app_engine, bypass_engine):
    """A1c/公开例外：广场公开句跨用户可读。"""
    a = make_user(bypass_engine, "a@t.com")
    b = make_user(bypass_engine, "b@t.com")
    _, word_id = make_word(bypass_engine, a)
    make_output_entry(bypass_engine, a, word_id, is_public=True)
    make_output_entry(bypass_engine, a, word_id, is_public=False)

    with app_engine.connect() as conn:
        set_uid(conn, b)
        # b 只能看到 a 的公开句，看不到私有句
        public = conn.execute(text("SELECT count(*) FROM output_entries")).scalar()
        assert public == 1


def test_output_entries_public_not_writable_by_others(app_engine, bypass_engine):
    """读写分离：他人公开句可读但不可改/删。"""
    a = make_user(bypass_engine, "a@t.com")
    b = make_user(bypass_engine, "b@t.com")
    _, word_id = make_word(bypass_engine, a)
    eid = make_output_entry(bypass_engine, a, word_id, is_public=True)

    with app_engine.connect() as conn:
        set_uid(conn, b)
        # UPDATE 命中 0 行（oe_upd 仅本人）
        r = conn.execute(text("UPDATE output_entries SET corrected='hacked' WHERE id=:i"),
                         {"i": eid})
        assert r.rowcount == 0
        d = conn.execute(text("DELETE FROM output_entries WHERE id=:i"), {"i": eid})
        assert d.rowcount == 0
        conn.commit()

    # 原内容未被篡改
    with bypass_engine.connect() as conn:
        val = conn.execute(text("SELECT corrected FROM output_entries WHERE id=:i"),
                           {"i": eid}).scalar()
        assert val == "phrase"


def test_consecutive_requests_different_users(app_engine, bypass_engine):
    """连接复用：同一连接先后扮演两个用户，互不串数据。"""
    a = make_user(bypass_engine, "a@t.com")
    b = make_user(bypass_engine, "b@t.com")
    make_word(bypass_engine, a, "alpha")
    make_word(bypass_engine, b, "beta")

    with app_engine.connect() as conn:
        set_uid(conn, a)
        rows_a = conn.execute(text("SELECT word FROM words")).fetchall()
        assert [r[0] for r in rows_a] == ["alpha"]
        set_uid(conn, b)
        rows_b = conn.execute(text("SELECT word FROM words")).fetchall()
        assert [r[0] for r in rows_b] == ["beta"]
