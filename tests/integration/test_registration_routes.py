"""OR3 Slice A: public registration route behavior."""
from hashlib import sha256

from sqlalchemy import text

from tests.helpers import provision_user


GENERIC_REQUEST_MESSAGE = (
    "如果该邮箱可用，我们会发送相关邮件；若未收到邮件，可稍后重试。"
)


class RecordingMailer:
    def __init__(self):
        self.calls = []

    def send_registration_verification(
            self, email, verification_url, idempotency_key):
        self.calls.append({
            "kind": "verification",
            "email": email,
            "url": verification_url,
            "idempotency_key": idempotency_key,
        })
        return "fake-verification-provider-id"

    def send_account_guidance(
            self, email, login_url, forgot_password_url, idempotency_key):
        self.calls.append({
            "kind": "guidance",
            "email": email,
            "login_url": login_url,
            "forgot_password_url": forgot_password_url,
            "idempotency_key": idempotency_key,
        })
        return "fake-guidance-provider-id"


def _auth_row_counts(bypass_engine):
    with bypass_engine.connect() as conn:
        return conn.execute(text("""
            SELECT
                (SELECT count(*) FROM auth_challenges) AS challenges,
                (SELECT count(*) FROM auth_mail_events) AS events
        """)).mappings().one()


def test_registration_is_closed_by_default_for_get_post_and_ui(
        app, bypass_engine):
    assert app.config["OPEN_REGISTRATION_ENABLED"] is False
    default_mailer = RecordingMailer()
    app.extensions["auth_mailer"] = default_mailer
    default_client = app.test_client()
    assert default_client.get("/register").status_code == 404
    assert default_client.post(
        "/register", data={"email": "closed@example.com"}
    ).status_code == 404
    assert "/register" not in default_client.get("/login").get_data(as_text=True)
    assert "/register" not in default_client.get("/").get_data(as_text=True)
    assert default_mailer.calls == []

    assert _auth_row_counts(bypass_engine) == {
        "challenges": 0,
        "events": 0,
    }


def _flash_text(page):
    return page.split('<ul class="flashes">', 1)[1].split(
        "<li>", 1
    )[1].split("</li>", 1)[0]


def test_registration_enabled_handles_unknown_known_and_client_ip(
        app, bypass_engine, client):
    app.config.update(
        OPEN_REGISTRATION_ENABLED=True,
        PUBLIC_BASE_URL="https://example.test",
    )
    mailer = RecordingMailer()
    app.extensions["auth_mailer"] = mailer
    provision_user(app, "known@example.com", password="pw12345678")

    assert client.get("/register").status_code == 200
    invalid = client.post(
        "/register",
        data={"email": "not-an-email"},
        headers={"Accept-Language": "en"},
    )
    assert invalid.status_code == 200
    invalid_page = invalid.get_data(as_text=True)
    assert "Enter a valid email address" in invalid_page
    assert "请输入有效邮箱" not in invalid_page

    unknown_client = app.test_client()
    known_client = app.test_client()
    unknown = unknown_client.post(
        "/register",
        data={"email": "unknown@example.com"},
        environ_base={
            "REMOTE_ADDR": "198.51.100.7",
            "HTTP_X_FORWARDED_FOR": "203.0.113.99",
        },
    )
    known = known_client.post(
        "/register",
        data={"email": "known@example.com"},
        environ_base={
            "REMOTE_ADDR": "198.51.100.7",
            "HTTP_X_FORWARDED_FOR": "203.0.113.99",
        },
    )
    assert unknown.status_code == known.status_code == 303
    assert unknown.headers["Location"].endswith("/login")
    assert known.headers["Location"].endswith("/login")

    unknown_page = unknown_client.get(
        unknown.headers["Location"]
    ).get_data(as_text=True)
    known_page = known_client.get(
        known.headers["Location"]
    ).get_data(as_text=True)
    assert _flash_text(unknown_page) == _flash_text(known_page)
    assert _flash_text(unknown_page) == GENERIC_REQUEST_MESSAGE

    assert [call["kind"] for call in mailer.calls] == [
        "verification", "guidance",
    ]

    expected_client_digest = sha256(b"198.51.100.7").hexdigest()
    with bypass_engine.connect() as conn:
        rows = conn.execute(text("""
            SELECT email, client_key_digest
            FROM auth_mail_events
            ORDER BY id
        """)).mappings().all()
    assert [row["email"] for row in rows] == [
        "unknown@example.com", "known@example.com",
    ]
    assert {row["client_key_digest"] for row in rows} == {
        expected_client_digest,
    }


def test_login_uses_gated_a_variant_for_recovery_and_registration(app, client):
    app.config["OPEN_REGISTRATION_ENABLED"] = False
    closed_page = client.get("/login").get_data(as_text=True)
    quiet_link = closed_page.split(
        '<a class="auth-quiet-link"', 1
    )[1].split("</a>", 1)[0]

    assert 'href="/forgot-password"' in quiet_link
    assert "<svg" in quiet_link
    assert 'aria-hidden="true"' in quiet_link
    assert "/register" not in closed_page
    assert "auth-register-cta" not in closed_page

    app.config["OPEN_REGISTRATION_ENABLED"] = True
    enabled_page = client.get("/login").get_data(as_text=True)
    register_cta = enabled_page.split(
        '<section class="auth-register-cta"', 1
    )[1].split("</section>", 1)[0]

    assert 'href="/register"' in register_cta
    assert "auth-register-microcopy" in register_cta
    assert "auth-register-button" in register_cta
