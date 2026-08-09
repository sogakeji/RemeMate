"""OR3 Slice B: registration activation and initial-password routes."""
from hashlib import sha256
from urllib.parse import unquote, urlsplit

from sqlalchemy import text

from tests.helpers import provision_user


GENERIC_INVALID_MESSAGE = "验证链接无效或已过期，请重新申请。"


class RecordingMailer:
    def __init__(self):
        self.verification_urls = []

    def send_registration_verification(
            self, email, verification_url, idempotency_key):
        self.verification_urls.append(verification_url)
        return "fake-provider-id"


def _raw_token(mailer):
    return unquote(urlsplit(mailer.verification_urls[-1]).path.rsplit("/", 1)[-1])


def _flash_text(page):
    return page.split('<ul class="flashes">', 1)[1].split(
        "<li>", 1
    )[1].split("</li>", 1)[0]


def _copy_session(source_client, target_client):
    with source_client.session_transaction() as source:
        values = dict(source)
    with target_client.session_transaction() as target:
        target.update(values)


def test_registration_activation_ignores_flag_and_requires_initial_password(
        app, bypass_engine, client):
    app.config.update(
        OPEN_REGISTRATION_ENABLED=True,
        PUBLIC_BASE_URL="https://example.test",
    )
    mailer = RecordingMailer()
    app.extensions["auth_mailer"] = mailer

    requested = client.post(
        "/register",
        data={"email": "pending@example.com"},
        environ_base={"REMOTE_ADDR": "198.51.100.7"},
    )
    assert requested.status_code == 303
    raw_token = _raw_token(mailer)
    second_requested = client.post(
        "/register",
        data={"email": "second-pending@example.com"},
        environ_base={"REMOTE_ADDR": "198.51.100.7"},
    )
    assert second_requested.status_code == 303
    second_token = _raw_token(mailer)

    app.config["OPEN_REGISTRATION_ENABLED"] = False
    verified = client.get(f"/verify-email/{raw_token}")
    assert verified.status_code == 303
    assert verified.headers["Location"].endswith("/set-password")
    with client.session_transaction() as session:
        pending_user_id = session.get("_user_id")
    assert pending_user_id

    with bypass_engine.connect() as conn:
        pending = conn.execute(text("""
            SELECT password_setup_required
            FROM users
            WHERE id = :user_id
        """), {"user_id": int(pending_user_id)}).scalar_one()
    assert pending is True

    pending_verify = client.get(f"/verify-email/{second_token}")
    assert pending_verify.status_code == 302
    assert pending_verify.headers["Location"].endswith("/set-password")
    with bypass_engine.connect() as conn:
        second_challenge = conn.execute(text("""
            SELECT consumed_at
            FROM auth_challenges
            WHERE token_digest = :digest
        """), {"digest": sha256(second_token.encode()).hexdigest()}).scalar_one()
        second_user_count = conn.execute(text("""
            SELECT count(*)
            FROM users
            WHERE email = 'second-pending@example.com'
        """)).scalar_one()
    assert second_challenge is None
    assert second_user_count == 0

    for path in ("/", "/settings", "/write"):
        blocked = client.get(path)
        assert blocked.status_code == 302
        assert "/set-password" in blocked.headers["Location"]

    assert client.get("/static/style.css").status_code == 200
    blocked_submit = client.post(
        "/write/submit",
        data={"mode": "diary", "sentence": "should not reach the writer"},
    )
    assert blocked_submit.status_code == 302
    assert blocked_submit.headers["Location"].endswith("/set-password")
    assert client.get("/healthz").status_code == 200
    logout_client = app.test_client()
    _copy_session(client, logout_client)
    assert logout_client.get("/logout").status_code == 302

    short = client.post(
        "/set-password",
        data={"password": "short", "confirm_password": "short"},
    )
    assert short.status_code == 200
    mismatch = client.post(
        "/set-password",
        data={"password": "long-enough", "confirm_password": "different"},
    )
    assert mismatch.status_code == 200

    saved = client.post(
        "/set-password",
        data={
            "password": "new-password-123",
            "confirm_password": "new-password-123",
        },
    )
    assert saved.status_code == 303
    assert saved.headers["Location"].endswith("/")
    assert client.get("/settings").status_code == 200

    assert client.get("/logout").status_code == 302
    login = client.post(
        "/login",
        data={
            "email": "pending@example.com",
            "password": "new-password-123",
        },
    )
    assert login.status_code == 302
    assert login.headers["Location"].endswith("/")

    with bypass_engine.connect() as conn:
        flag = conn.execute(text("""
            SELECT password_setup_required
            FROM users
            WHERE email = 'pending@example.com'
        """)).scalar_one()
    assert flag is False


def test_registration_verify_invalid_expired_and_logged_in_are_safe(
        app, bypass_engine, client):
    app.config.update(
        OPEN_REGISTRATION_ENABLED=True,
        PUBLIC_BASE_URL="https://example.test",
    )
    mailer = RecordingMailer()
    app.extensions["auth_mailer"] = mailer
    request_client = app.test_client()

    request_client.post(
        "/register", data={"email": "expired@example.com"}
    )
    expired_token = _raw_token(mailer)
    with bypass_engine.begin() as conn:
        conn.execute(text("""
            UPDATE auth_challenges
            SET expires_at = now() - interval '1 second'
            WHERE token_digest = :digest
        """), {"digest": sha256(expired_token.encode()).hexdigest()})

    invalid_client = app.test_client()
    invalid = invalid_client.get("/verify-email/not-a-real-token")
    expired_client = app.test_client()
    expired = expired_client.get(f"/verify-email/{expired_token}")
    assert invalid.status_code == expired.status_code == 303
    assert invalid.headers["Location"].endswith("/login")
    assert expired.headers["Location"].endswith("/login")
    with bypass_engine.connect() as conn:
        expired_consumed_at = conn.execute(text("""
            SELECT consumed_at
            FROM auth_challenges
            WHERE token_digest = :digest
        """), {"digest": sha256(expired_token.encode()).hexdigest()}).scalar_one()
    assert expired_consumed_at is None
    invalid_page = invalid_client.get(invalid.headers["Location"]).get_data(
        as_text=True
    )
    expired_page = expired_client.get(expired.headers["Location"]).get_data(
        as_text=True
    )
    assert _flash_text(invalid_page) == _flash_text(expired_page)
    assert _flash_text(invalid_page) == GENERIC_INVALID_MESSAGE

    existing_user_id = provision_user(
        app, "already@example.com", password="existing-password"
    )
    request_client.post(
        "/register", data={"email": "other@example.com"}
    )
    other_token = _raw_token(mailer)
    client.post(
        "/login",
        data={"email": "already@example.com", "password": "existing-password"},
    )
    logged_in = client.get(f"/verify-email/{other_token}")
    assert logged_in.status_code == 303
    assert logged_in.headers["Location"].endswith("/")
    page = client.get(logged_in.headers["Location"]).get_data(as_text=True)
    assert "请先退出当前账号" in page
    with client.session_transaction() as session:
        assert int(session["_user_id"]) == existing_user_id

    with bypass_engine.connect() as conn:
        challenge = conn.execute(text("""
            SELECT consumed_at
            FROM auth_challenges
            WHERE token_digest = :digest
        """), {"digest": sha256(other_token.encode()).hexdigest()}).scalar_one()
        created = conn.execute(text("""
            SELECT count(*)
            FROM users
            WHERE email = 'other@example.com'
        """)).scalar_one()
    assert challenge is None
    assert created == 0
