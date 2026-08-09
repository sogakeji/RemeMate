"""OR3 Slice C: password-reset request and completion routes."""
from hashlib import sha256
from urllib.parse import unquote, urlsplit

from sqlalchemy import text
from werkzeug.security import check_password_hash

from app.services.account_access import reset_password
from tests.helpers import provision_user


GENERIC_REQUEST_MESSAGE = (
    "如果该邮箱已注册，我们会发送重置邮件；若未收到邮件，可稍后重试。"
)
GENERIC_INVALID_MESSAGE = "重置链接无效或已过期，请重新申请。"


class RecordingMailer:
    def __init__(self):
        self.reset_urls = []

    def send_password_reset(self, email, reset_url, idempotency_key):
        self.reset_urls.append({
            "email": email,
            "reset_url": reset_url,
            "idempotency_key": idempotency_key,
        })
        return "fake-reset-provider-id"


def _raw_token(reset_url):
    return unquote(urlsplit(reset_url).path.rsplit("/", 1)[-1])


def _flash_text(page):
    return page.split('<ul class="flashes">', 1)[1].split(
        "<li>", 1
    )[1].split("</li>", 1)[0]


def _request_reset(client, email, remote_addr, forwarded_for=None):
    request_kwargs = {
        "data": {"email": email},
        "environ_base": {"REMOTE_ADDR": remote_addr},
    }
    if forwarded_for is not None:
        request_kwargs["headers"] = {"X-Forwarded-For": forwarded_for}
    response = client.post("/forgot-password", **request_kwargs)
    assert response.status_code == 303
    assert response.headers["Location"].endswith("/login")
    return response


def test_password_reset_routes_are_non_enumerating_and_reset_account(
        app, bypass_engine, client):
    app.config.update(
        OPEN_REGISTRATION_ENABLED=False,
        PUBLIC_BASE_URL="https://example.test",
    )
    target_id = provision_user(
        app, "target@example.com", password="old-password-123"
    )
    mailer = RecordingMailer()
    app.extensions["auth_mailer"] = mailer

    assert client.get("/forgot-password").status_code == 200
    assert "/forgot-password" in client.get("/login").get_data(as_text=True)

    known = _request_reset(
        client,
        "target@example.com",
        "198.51.100.7",
        forwarded_for="203.0.113.9",
    )
    unknown_client = app.test_client()
    unknown = _request_reset(
        unknown_client, "unknown@example.com", "198.51.100.7"
    )

    known_page = client.get(known.headers["Location"]).get_data(as_text=True)
    unknown_page = unknown_client.get(
        unknown.headers["Location"]
    ).get_data(as_text=True)
    assert _flash_text(known_page) == _flash_text(unknown_page)
    assert _flash_text(known_page) == GENERIC_REQUEST_MESSAGE
    assert len(mailer.reset_urls) == 1

    reset_call = mailer.reset_urls[0]
    raw_token = _raw_token(reset_call["reset_url"])
    assert reset_call["email"] == "target@example.com"
    with bypass_engine.connect() as conn:
        event = conn.execute(text("""
            SELECT client_key_digest, delivery_status, provider_message_id
            FROM auth_mail_events
            WHERE email = 'target@example.com'
              AND purpose = 'password_reset'
        """)).mappings().one()
    assert event["client_key_digest"] == sha256(b"198.51.100.7").hexdigest()
    assert event["client_key_digest"] != sha256(b"203.0.113.9").hexdigest()
    assert event["delivery_status"] == "sent"
    assert event["provider_message_id"] == "fake-reset-provider-id"

    reset_path = f"/reset-password/{raw_token}"
    assert client.get(reset_path).status_code == 200

    short = client.post(
        reset_path,
        data={"password": "short", "confirm_password": "short"},
    )
    mismatch = client.post(
        reset_path,
        data={"password": "new-password-123", "confirm_password": "other"},
    )
    assert short.status_code == 200
    assert mismatch.status_code == 200
    with bypass_engine.connect() as conn:
        challenge = conn.execute(text("""
            SELECT consumed_at
            FROM auth_challenges
            WHERE token_digest = :digest
              AND purpose = 'password_reset'
        """), {"digest": sha256(raw_token.encode()).hexdigest()}).scalar_one()
    assert challenge is None

    saved = client.post(
        reset_path,
        data={
            "password": "new-password-123",
            "confirm_password": "new-password-123",
        },
    )
    assert saved.status_code == 303
    assert saved.headers["Location"].endswith("/")
    with client.session_transaction() as session:
        assert int(session["_user_id"]) == target_id

    assert client.get("/logout").status_code == 302
    old_login = client.post(
        "/login",
        data={"email": "target@example.com", "password": "old-password-123"},
    )
    assert old_login.status_code == 200
    new_login = client.post(
        "/login",
        data={"email": "target@example.com", "password": "new-password-123"},
    )
    assert new_login.status_code == 302
    with bypass_engine.connect() as conn:
        user = conn.execute(text("""
            SELECT password_hash, password_setup_required
            FROM users
            WHERE id = :user_id
        """), {"user_id": target_id}).mappings().one()
    assert check_password_hash(user["password_hash"], "new-password-123")
    assert user["password_setup_required"] is False


def test_logged_in_other_user_can_reset_without_identity_switch(
        app, bypass_engine):
    app.config["PUBLIC_BASE_URL"] = "https://example.test"
    target_id = provision_user(
        app, "target@example.com", password="target-old-123"
    )
    other_id = provision_user(
        app, "other@example.com", password="other-old-123"
    )
    mailer = RecordingMailer()
    app.extensions["auth_mailer"] = mailer
    request_client = app.test_client()
    _request_reset(request_client, "target@example.com", "198.51.100.8")
    raw_token = _raw_token(mailer.reset_urls[0]["reset_url"])

    logged_client = app.test_client()
    login = logged_client.post(
        "/login",
        data={"email": "other@example.com", "password": "other-old-123"},
    )
    assert login.status_code == 302
    reset = logged_client.post(
        f"/reset-password/{raw_token}",
        data={"password": "target-new-123", "confirm_password": "target-new-123"},
    )
    assert reset.status_code == 303
    assert reset.headers["Location"].endswith("/")
    with logged_client.session_transaction() as session:
        assert int(session["_user_id"]) == other_id

    with bypass_engine.connect() as conn:
        target = conn.execute(text("""
            SELECT password_hash, password_setup_required
            FROM users
            WHERE id = :user_id
        """), {"user_id": target_id}).mappings().one()
    assert check_password_hash(target["password_hash"], "target-new-123")
    assert target["password_setup_required"] is False


def test_invalid_expired_and_consumed_reset_tokens_are_uniform(
        app, bypass_engine):
    app.config["PUBLIC_BASE_URL"] = "https://example.test"
    provision_user(app, "target@example.com", password="old-password-123")
    mailer = RecordingMailer()
    app.extensions["auth_mailer"] = mailer
    request_client = app.test_client()
    _request_reset(request_client, "target@example.com", "198.51.100.9")
    _request_reset(request_client, "target@example.com", "198.51.100.10")
    expired_token = _raw_token(mailer.reset_urls[0]["reset_url"])
    consumed_token = _raw_token(mailer.reset_urls[1]["reset_url"])

    with bypass_engine.begin() as conn:
        conn.execute(text("""
            UPDATE auth_challenges
            SET expires_at = now() - interval '1 second'
            WHERE token_digest = :digest
        """), {"digest": sha256(expired_token.encode()).hexdigest()})
    with app.app_context():
        reset_password(consumed_token, "consumed-password-123")

    cases = [
        ("not-a-real-token", app.test_client()),
        (expired_token, app.test_client()),
        (consumed_token, app.test_client()),
    ]
    with bypass_engine.connect() as conn:
        states_before_get = {}
        for raw_token, _reset_client in cases:
            states_before_get[raw_token] = conn.execute(text("""
                SELECT consumed_at
                FROM auth_challenges
                WHERE token_digest = :digest
                  AND purpose = 'password_reset'
            """), {
                "digest": sha256(raw_token.encode()).hexdigest(),
            }).scalar_one_or_none()

    for raw_token, reset_client in cases:
        get_response = reset_client.get(f"/reset-password/{raw_token}")
        get_page = get_response.get_data(as_text=True)
        assert get_response.status_code == 200
        assert '<form method="post"' in get_page
        assert 'name="password"' in get_page
        assert 'name="confirm_password"' in get_page
        assert GENERIC_INVALID_MESSAGE not in get_page

    with bypass_engine.connect() as conn:
        states_after_get = {}
        for raw_token, _reset_client in cases:
            states_after_get[raw_token] = conn.execute(text("""
                SELECT consumed_at
                FROM auth_challenges
                WHERE token_digest = :digest
                  AND purpose = 'password_reset'
            """), {
                "digest": sha256(raw_token.encode()).hexdigest(),
            }).scalar_one_or_none()
    assert states_after_get == states_before_get

    pages = []
    for raw_token, reset_client in cases:
        response = reset_client.post(
            f"/reset-password/{raw_token}",
            data={"password": "new-password-123", "confirm_password": "new-password-123"},
        )
        assert response.status_code == 303
        assert response.headers["Location"].endswith("/login")
        pages.append(
            _flash_text(
                reset_client.get(response.headers["Location"]).get_data(
                    as_text=True
                )
            )
        )
    assert pages == [GENERIC_INVALID_MESSAGE] * 3
