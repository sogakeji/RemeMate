"""provisioning：三表一事务 + quota_reset_at 初始化 + 重名拒绝。"""
import pytest
from sqlalchemy import text

from app.services import provisioning


def test_create_user_builds_three_tables(app, bypass_engine):
    with app.app_context():
        uid, pw = provisioning.create_user_with_defaults("a@t.com", "Alice")
    assert pw and len(pw) >= 8

    with bypass_engine.connect() as c:
        assert c.execute(text("SELECT count(*) FROM users WHERE id=:i"),
                         {"i": uid}).scalar() == 1
        assert c.execute(text("SELECT count(*) FROM user_settings WHERE user_id=:i"),
                         {"i": uid}).scalar() == 1
        # quota_reset_at 必须被初始化，不能是 NULL（否则永不重置）
        reset_at = c.execute(text("SELECT quota_reset_at FROM user_quota WHERE user_id=:i"),
                             {"i": uid}).scalar()
        assert reset_at is not None
        # 四个通知开关默认值
        row = c.execute(text(
            "SELECT feedback_language, notify_review_reminder, notify_daily_summary, "
            "notify_intake_done, notify_partner_activity "
            "FROM user_settings WHERE user_id=:i"), {"i": uid}).fetchone()
        assert row == ("zh", True, True, True, False)


def test_create_user_can_preset_languages_and_feedback(app, bypass_engine):
    with app.app_context():
        uid, _ = provisioning.create_user_with_defaults(
            "frfriend@t.com", "French Friend",
            learning_languages=["zh"], feedback_language="fr",
            password="pw12345678",
        )

    with bypass_engine.connect() as c:
        row = c.execute(text(
            "SELECT current_language, learning_languages FROM users WHERE id=:i"),
            {"i": uid}).fetchone()
        fb = c.execute(text(
            "SELECT feedback_language FROM user_settings WHERE user_id=:i"),
            {"i": uid}).scalar()
        wl = c.execute(text(
            "SELECT name, language_code FROM word_lists WHERE user_id=:i"),
            {"i": uid}).fetchone()
    assert row == ("zh", "zh")
    assert fb == "fr"
    assert wl == ("中文", "zh")


def test_create_user_duplicate_email_rejected(app):
    with app.app_context():
        provisioning.create_user_with_defaults("dup@t.com", "A")
        with pytest.raises(provisioning.UserExistsError):
            provisioning.create_user_with_defaults("dup@t.com", "B")


def test_reset_quota_and_password(app, bypass_engine):
    with app.app_context():
        uid, _ = provisioning.create_user_with_defaults("r@t.com", "R")
        newpw = provisioning.reset_password("r@t.com")
        assert newpw
        provisioning.reset_quota("r@t.com")

    with bypass_engine.connect() as c:
        used = c.execute(text("SELECT tokens_used_today FROM user_quota WHERE user_id=:i"),
                         {"i": uid}).scalar()
        assert used == 0


def test_deactivate_user(app, bypass_engine):
    with app.app_context():
        uid, _ = provisioning.create_user_with_defaults("d@t.com", "D")
        provisioning.deactivate_user("d@t.com")
    with bypass_engine.connect() as c:
        active = c.execute(text("SELECT is_active FROM users WHERE id=:i"),
                           {"i": uid}).scalar()
        assert active is False
