"""provisioning：三表一事务 + quota_reset_at 初始化 + 重名拒绝。"""
from concurrent.futures import ThreadPoolExecutor
import threading
from uuid import uuid4

import pytest
from sqlalchemy import event, text
from sqlalchemy.engine import Engine
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.extensions import db
from app.models.user import User, UserSettings, UserQuota
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


def test_create_user_rejects_invalid_email(app):
    with app.app_context():
        with pytest.raises(ValueError, match="邮箱格式不正确"):
            provisioning.create_user_with_defaults("not-an-email", "Bad")


def test_reset_quota_and_password(app, bypass_engine):
    with app.app_context():
        uid, _ = provisioning.create_user_with_defaults("r@t.com", "R")
    with bypass_engine.begin() as c:
        c.execute(text(
            "UPDATE user_quota SET tokens_used_today=10, bonus_tokens_today=5, "
            "corrections_today=3, imports_today=7 WHERE user_id=:i"
        ), {"i": uid})

    with app.app_context():
        newpw = provisioning.reset_password("r@t.com")
        assert newpw
        provisioning.reset_quota("r@t.com")

    with bypass_engine.connect() as c:
        row = c.execute(text(
            "SELECT tokens_used_today, bonus_tokens_today, corrections_today, imports_today "
            "FROM user_quota WHERE user_id=:i"
        ), {"i": uid}).one()
        assert row == (0, 0, 0, 0)


def test_deactivate_user(app, bypass_engine):
    with app.app_context():
        uid, _ = provisioning.create_user_with_defaults("d@t.com", "D")
        provisioning.deactivate_user("d@t.com")
    with bypass_engine.connect() as c:
        active = c.execute(text("SELECT is_active FROM users WHERE id=:i"),
                           {"i": uid}).scalar()
        assert active is False


def test_existing_style_provisioning_defaults_uuid_and_password_setup_state(
        app, bypass_engine):
    with app.app_context():
        uid, password = provisioning.create_user_with_defaults(
            "legacy-defaults@t.com", "Legacy Defaults", password="pw12345678",
        )

    assert password == "pw12345678"
    with bypass_engine.connect() as c:
        row = c.execute(text(
            "SELECT public_id, password_setup_required FROM users WHERE id=:i"
        ), {"i": uid}).one()

    assert row.public_id is not None
    assert row.password_setup_required is False


def test_new_users_receive_distinct_uuids(app, bypass_engine):
    with app.app_context():
        first_id, _ = provisioning.create_user_with_defaults(
            "uuid-first@t.com", "UUID First",
        )
        second_id, _ = provisioning.create_user_with_defaults(
            "uuid-second@t.com", "UUID Second",
        )

    with bypass_engine.connect() as c:
        ids = c.execute(text(
            "SELECT public_id FROM users WHERE id IN (:first_id, :second_id) "
            "ORDER BY id"
        ), {"first_id": first_id, "second_id": second_id}).scalars().all()

    assert len(ids) == 2
    assert ids[0] is not None and ids[1] is not None
    assert ids[0] != ids[1]


def test_internal_provisioning_session_contract_returns_user_without_commit(
        app, bypass_engine):
    with app.app_context():
        session = Session(bypass_engine)
        try:
            user = provisioning._create_user_with_defaults_in_session(
                session,
                "pending-password@t.com",
                "Pending Password",
                password="pw12345678",
                password_setup_required=True,
            )

            assert isinstance(user, User)
            assert user.public_id is not None
            assert user.password_setup_required is True
            assert user.password_hash != "pw12345678"
            assert session.get(UserSettings, user.id) is not None
            quota = session.get(UserQuota, user.id)
            assert quota is not None
            assert quota.quota_reset_at is not None
            session.rollback()
        finally:
            session.close()

    with bypass_engine.connect() as c:
        row = c.execute(text(
            "SELECT id FROM users WHERE email='pending-password@t.com'"
        )).scalar_one_or_none()
    assert row is None


def test_concurrent_same_normalized_email_has_one_complete_winner(
        app, bypass_engine):
    prechecks = 0
    blocked_connections = set()
    precheck_lock = threading.Lock()
    both_prechecks_done = threading.Event()
    release_prechecks = threading.Event()

    def after_cursor_execute(conn, cursor, statement, parameters, context,
                             executemany):
        nonlocal prechecks
        if release_prechecks.is_set():
            return
        normalized_statement = " ".join(statement.lower().split())
        if "from users" not in normalized_statement:
            return
        if "where users.email =" not in normalized_statement:
            return

        connection_key = id(conn)
        with precheck_lock:
            if connection_key in blocked_connections:
                return
            blocked_connections.add(connection_key)
            prechecks += 1
            if prechecks == 2:
                both_prechecks_done.set()

        if not release_prechecks.wait(timeout=15):
            raise AssertionError("并发 provisioning 预查未被释放")

    def create_racing_user():
        with app.app_context():
            try:
                result = provisioning.create_user_with_defaults(
                    "  Race@T.Com  ", "Race", password="pw12345678",
                )
            except provisioning.UserExistsError as exc:
                return "user_exists", exc
            return "success", result

    executor = ThreadPoolExecutor(max_workers=2)
    event.listen(Engine, "after_cursor_execute", after_cursor_execute)
    try:
        futures = [executor.submit(create_racing_user) for _ in range(2)]
        assert both_prechecks_done.wait(timeout=15)
        release_prechecks.set()
        outcomes = [future.result() for future in futures]
    finally:
        release_prechecks.set()
        executor.shutdown(wait=True)
        event.remove(Engine, "after_cursor_execute", after_cursor_execute)

    assert not event.contains(Engine, "after_cursor_execute", after_cursor_execute)
    assert prechecks == 2
    assert len(blocked_connections) == 2
    assert [kind for kind, _ in outcomes].count("success") == 1
    assert [kind for kind, _ in outcomes].count("user_exists") == 1
    errors = [value for kind, value in outcomes if kind == "user_exists"]
    assert isinstance(errors[0], provisioning.UserExistsError)

    with bypass_engine.connect() as conn:
        counts = conn.execute(text("""
            SELECT
                (SELECT count(*) FROM users WHERE email='race@t.com'),
                (SELECT count(*) FROM user_settings AS s
                 JOIN users AS u ON u.id=s.user_id WHERE u.email='race@t.com'),
                (SELECT count(*) FROM user_quota AS q
                 JOIN users AS u ON u.id=q.user_id WHERE u.email='race@t.com')
        """)).one()
    assert counts == (1, 1, 1)


def test_wrapper_reraises_non_email_integrity_error(app, monkeypatch):
    expected = IntegrityError(
        "synthetic non-email constraint", {}, RuntimeError("quota constraint")
    )

    def fail_inside_session(*args, **kwargs):
        raise expected

    monkeypatch.setattr(
        provisioning,
        "_create_user_with_defaults_in_session",
        fail_inside_session,
    )

    with app.app_context():
        with pytest.raises(IntegrityError) as caught:
            provisioning.create_user_with_defaults(
                "non-email-integrity@t.com", "Non Email Integrity",
            )

    assert caught.value is expected
    assert not isinstance(caught.value, provisioning.UserExistsError)


def test_database_default_sets_password_setup_required_false(bypass_engine):
    with bypass_engine.begin() as connection:
        password_setup_required = connection.execute(
            text(
                """
                INSERT INTO users (
                    public_id,
                    email,
                    password_hash,
                    display_name,
                    role,
                    is_active,
                    login_attempts,
                    timezone,
                    created_at
                )
                VALUES (
                    :public_id,
                    :email,
                    :password_hash,
                    :display_name,
                    :role,
                    TRUE,
                    0,
                    :timezone,
                    now()
                )
                RETURNING password_setup_required
                """
            ),
            {
                "public_id": str(uuid4()),
                "email": "raw-default@example.com",
                "password_hash": "hash",
                "display_name": "Raw Default",
                "role": "user",
                "timezone": "UTC",
            },
        ).scalar_one()

    assert password_setup_required is False


def test_orm_rejects_persisted_public_id_mutation(app):
    with app.app_context():
        user_id, _ = provisioning.create_user_with_defaults(
            "immutable-public-id@example.com", "Immutable Public ID",
        )
        user = db.session.get(User, user_id)
        original_public_id = user.public_id
        user.public_id = uuid4()

        with pytest.raises(ValueError, match="public_id"):
            db.session.commit()

        db.session.rollback()
        assert db.session.get(User, user_id).public_id == original_public_id
