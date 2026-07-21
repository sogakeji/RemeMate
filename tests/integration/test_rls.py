"""第三层 RLS 本层测试（绕过 service，直连 DB、用 app 角色）。

回归 review 2026-06-23 的 A1 各子项：deny-all / FORCE / fail-closed / 公开句例外 /
公开句写保护 / 连接复用。
"""
import pytest
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError

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


def test_output_entry_insert_rejects_word_owned_by_another_user(
        app_engine, bypass_engine):
    """The app role cannot bind a new private entry to another user's word."""
    owner = make_user(bypass_engine, "owner@t.com")
    attacker = make_user(bypass_engine, "attacker@t.com")
    _, owner_word_id = make_word(bypass_engine, owner, "secret")

    with pytest.raises(DBAPIError):
        with app_engine.begin() as conn:
            set_uid(conn, attacker)
            conn.execute(text("""
                INSERT INTO output_entries(
                    word_id, user_id, original, corrected, word_text,
                    language_code, is_public, upvote_count, is_nsfw,
                    created_at
                ) VALUES (
                    :word_id, :user_id, 'x', 'x', 'secret',
                    'fr', false, 0, false, now()
                )
            """), {"word_id": owner_word_id, "user_id": attacker})


def test_output_entry_update_rejects_rebind_to_another_users_word(
        app_engine, bypass_engine):
    """An owned entry cannot be rebound to a cross-user word."""
    owner = make_user(bypass_engine, "owner@t.com")
    attacker = make_user(bypass_engine, "attacker@t.com")
    _, owner_word_id = make_word(bypass_engine, owner, "secret")
    _, attacker_word_id = make_word(bypass_engine, attacker, "public")
    entry_id = make_output_entry(
        bypass_engine, attacker, attacker_word_id, is_public=False,
    )

    with pytest.raises(DBAPIError):
        with app_engine.begin() as conn:
            set_uid(conn, attacker)
            conn.execute(text("""
                UPDATE output_entries
                SET word_id = :owner_word_id
                WHERE id = :entry_id
            """), {"owner_word_id": owner_word_id, "entry_id": entry_id})

    with bypass_engine.connect() as conn:
        stored_word_id = conn.execute(text("""
            SELECT word_id FROM output_entries WHERE id = :entry_id
        """), {"entry_id": entry_id}).scalar()
    assert stored_word_id == attacker_word_id


def test_output_entry_insert_allows_owned_word_or_diary(
        app_engine, bypass_engine):
    user_id = make_user(bypass_engine, "writer@t.com")
    _, word_id = make_word(bypass_engine, user_id, "owned")

    with app_engine.begin() as conn:
        set_uid(conn, user_id)
        for candidate_word_id, word_text in ((word_id, "owned"), (None, "三行日记")):
            conn.execute(text("""
                INSERT INTO output_entries(
                    word_id, user_id, original, corrected, word_text,
                    language_code, is_public, upvote_count, is_nsfw,
                    created_at
                ) VALUES (
                    :word_id, :user_id, 'x', 'x', :word_text,
                    'fr', false, 0, false, now()
                )
            """), {"word_id": candidate_word_id, "user_id": user_id,
                    "word_text": word_text})


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
