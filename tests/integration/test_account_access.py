"""OR2 Slice 1：注册 challenge 发放与邮件 seam。"""
from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
from hashlib import sha256
from threading import Barrier
from urllib.parse import unquote, urlsplit

from sqlalchemy import text
from werkzeug.security import check_password_hash

from app import create_app
from app.services.account_access import (
    ActivatedAccount,
    InitialPasswordUnavailableError,
    InvalidChallengeError,
    PasswordPolicyError,
    RequestReceipt,
    request_registration,
    set_initial_password,
    verify_registration,
)


class RecordingMailer:
    def __init__(self, bypass_engine):
        self.bypass_engine = bypass_engine
        self.calls = []

    def send_registration_verification(
            self, email, verification_url, idempotency_key):
        event_id = int(idempotency_key.split(":", 1)[1])
        with self.bypass_engine.connect() as conn:
            event = conn.execute(text("""
                SELECT id, challenge_id, delivery_status
                FROM auth_mail_events
                WHERE id = :event_id
            """), {"event_id": event_id}).mappings().one()
            assert event["delivery_status"] == "reserved"
            assert event["challenge_id"] is not None

            challenge = conn.execute(text("""
                SELECT purpose, email
                FROM auth_challenges
                WHERE id = :challenge_id
            """), {"challenge_id": event["challenge_id"]}).mappings().one()
            assert challenge["purpose"] == "registration"
            assert challenge["email"] == email

        self.calls.append({
            "email": email,
            "verification_url": verification_url,
            "idempotency_key": idempotency_key,
        })
        return "fake-provider-id"


def test_request_registration_records_digest_and_sends_verification(
        app, bypass_engine):
    app.config["PUBLIC_BASE_URL"] = "https://example.test"
    mailer = RecordingMailer(bypass_engine)
    app.extensions["auth_mailer"] = mailer

    with app.app_context():
        assert app.config["REGISTRATION_TOKEN_TTL_SECONDS"] == 86_400
        receipt = request_registration(
            "  Alice@Example.COM ",
            "client-key-1",
        )

    assert receipt == RequestReceipt(outcome="accepted")
    assert len(mailer.calls) == 1
    call = mailer.calls[0]
    assert call["email"] == "alice@example.com"

    url = urlsplit(call["verification_url"])
    raw_token = unquote(url.path.rsplit("/", 1)[-1])
    assert raw_token
    assert url.scheme == "https"
    assert url.netloc == "example.test"
    assert url.path == f"/verify-email/{raw_token}"

    expected_token_digest = sha256(raw_token.encode("utf-8")).hexdigest()
    expected_client_digest = sha256(b"client-key-1").hexdigest()
    with bypass_engine.connect() as conn:
        challenge = conn.execute(text("""
            SELECT token_digest, purpose, email, expires_at, created_at
            FROM auth_challenges
        """)).mappings().one()
        event = conn.execute(text("""
            SELECT id, challenge_id, purpose, email, client_key_digest,
                   delivery_status, provider_message_id
            FROM auth_mail_events
        """)).mappings().one()

    assert challenge["token_digest"] == expected_token_digest
    assert raw_token not in challenge["token_digest"]
    assert challenge["purpose"] == "registration"
    assert challenge["email"] == "alice@example.com"
    assert timedelta(seconds=86_399) <= (
        challenge["expires_at"] - challenge["created_at"]
    ) <= timedelta(seconds=86_401)

    assert event["challenge_id"] is not None
    assert event["purpose"] == "registration"
    assert event["email"] == "alice@example.com"
    assert event["client_key_digest"] == expected_client_digest
    assert event["delivery_status"] == "sent"
    assert event["provider_message_id"] == "fake-provider-id"
    assert call["idempotency_key"] == f"registration:{event['id']}"


def test_same_registration_token_concurrent_verification_creates_one_complete_account(
        app, bypass_engine):
    app.config["PUBLIC_BASE_URL"] = "https://example.test"
    mailer = RecordingMailer(bypass_engine)
    app.extensions["auth_mailer"] = mailer

    with app.app_context():
        request_registration("  Alice@Example.COM ", "client-key-1")
    raw_token = unquote(
        urlsplit(mailer.calls[0]["verification_url"]).path.rsplit("/", 1)[-1]
    )
    barrier = Barrier(2)

    def verify_once():
        thread_app = create_app("testing")
        with thread_app.app_context():
            barrier.wait()
            try:
                return ("account", verify_registration(raw_token))
            except InvalidChallengeError:
                return ("invalid",)

    with ThreadPoolExecutor(max_workers=2) as executor:
        futures = [executor.submit(verify_once) for _ in range(2)]
        results = [future.result() for future in futures]

    accounts = [result[1] for result in results if result[0] == "account"]
    invalids = [result for result in results if result[0] == "invalid"]
    assert len(accounts) == 1
    assert len(invalids) == 1
    assert isinstance(accounts[0], ActivatedAccount)
    assert accounts[0].user_id > 0

    with bypass_engine.connect() as conn:
        challenge = conn.execute(text("""
            SELECT purpose, consumed_at
            FROM auth_challenges
        """)).mappings().one()
        user = conn.execute(text("""
            SELECT id, public_id, password_setup_required, display_name
            FROM users
        """)).mappings().one()
        settings = conn.execute(text(
            "SELECT count(*) AS count FROM user_settings"
        )).scalar_one()
        quota = conn.execute(text("""
            SELECT count(*) AS count, max(quota_reset_at) AS quota_reset_at
            FROM user_quota
        """)).mappings().one()

    assert challenge["purpose"] == "registration"
    assert challenge["consumed_at"] is not None
    assert user["id"] == accounts[0].user_id
    assert user["public_id"] is not None
    assert user["password_setup_required"] is True
    assert user["display_name"] == "alice"
    assert settings == 1
    assert quota["count"] == 1
    assert quota["quota_reset_at"] is not None


def test_set_initial_password_enforces_policy_and_is_one_time(
        app, bypass_engine):
    app.config["PUBLIC_BASE_URL"] = "https://example.test"
    mailer = RecordingMailer(bypass_engine)
    app.extensions["auth_mailer"] = mailer

    with app.app_context():
        request_registration("  Alice@Example.COM ", "client-key-1")
        raw_token = unquote(
            urlsplit(mailer.calls[0]["verification_url"])
            .path.rsplit("/", 1)[-1]
        )
        account = verify_registration(raw_token)

    assert isinstance(account, ActivatedAccount)
    with bypass_engine.connect() as conn:
        before = conn.execute(text("""
            SELECT password_setup_required, password_hash
            FROM users
            WHERE id = :user_id
        """), {"user_id": account.user_id}).mappings().one()

    with app.app_context():
        try:
            set_initial_password(account.user_id, "short")
        except PasswordPolicyError:
            pass
        else:
            raise AssertionError("short password was accepted")

    with bypass_engine.connect() as conn:
        after_short = conn.execute(text("""
            SELECT password_setup_required, password_hash
            FROM users
            WHERE id = :user_id
        """), {"user_id": account.user_id}).mappings().one()

    assert after_short == before

    with app.app_context():
        set_initial_password(account.user_id, "password")

    with bypass_engine.connect() as conn:
        after_valid = conn.execute(text("""
            SELECT password_setup_required, password_hash
            FROM users
            WHERE id = :user_id
        """), {"user_id": account.user_id}).mappings().one()

    assert after_valid["password_setup_required"] is False
    assert check_password_hash(after_valid["password_hash"], "password")

    with app.app_context():
        try:
            set_initial_password(account.user_id, "different")
        except InitialPasswordUnavailableError:
            pass
        else:
            raise AssertionError("initial password was reset")

    with bypass_engine.connect() as conn:
        after_second = conn.execute(text("""
            SELECT password_setup_required, password_hash
            FROM users
            WHERE id = :user_id
        """), {"user_id": account.user_id}).mappings().one()

    assert after_second == after_valid
