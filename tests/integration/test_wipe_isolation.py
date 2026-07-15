"""回归：验证 _wipe 能处理 user_quota → users FK 约束。

批量清理在父表处遇到 FK 时，_wipe 必须以逐用户事务重试，确保后续测试
不继承脏数据。
"""
from sqlalchemy import text

from tests.conftest import _wipe
from tests.helpers import make_user


def test_wipe_clears_user_quota_before_users(bypass_engine):
    """user_quota → users FK 不阻止 _wipe 清库（批量或逐用户均可）。"""
    # 建 user + user_quota（模拟最简 FK 场景）
    uid = make_user(bypass_engine, "wq@t.com")
    with bypass_engine.begin() as c:
        c.execute(
            text(
                "INSERT INTO user_quota(user_id, daily_base_limit,"
                "tokens_used_today, bonus_tokens_today) "
                "VALUES (:u, 50000, 0, 0)"
            ),
            {"u": uid},
        )

    # _wipe 必须不抛异常清空两张表
    _wipe(bypass_engine)

    with bypass_engine.connect() as c:
        assert c.execute(text("SELECT count(*) FROM user_quota")).scalar() == 0
        assert c.execute(text("SELECT count(*) FROM users")).scalar() == 0


def test_wipe_per_user_two_users(bypass_engine):
    """多用户场景：两个 user 各有 user_quota，_wipe 全部清空。"""
    u1 = make_user(bypass_engine, "a@t.com")
    u2 = make_user(bypass_engine, "b@t.com")
    with bypass_engine.begin() as c:
        for u in (u1, u2):
            c.execute(
                text(
                    "INSERT INTO user_quota(user_id, daily_base_limit,"
                    "tokens_used_today, bonus_tokens_today) "
                    "VALUES (:u, 50000, 0, 0)"
                ),
                {"u": u},
            )

    _wipe(bypass_engine)

    with bypass_engine.connect() as c:
        assert c.execute(text("SELECT count(*) FROM user_quota")).scalar() == 0
        assert c.execute(text("SELECT count(*) FROM users")).scalar() == 0
