"""OR2 Slice 1：注册 challenge 发放与邮件 seam。"""
from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
from hashlib import sha256
from threading import Barrier
from urllib.parse import unquote, urlsplit

from sqlalchemy import text
from werkzeug.security import check_password_hash

from app import create_app
from app.services.provisioning import create_user_with_defaults
from app.services.account_access import (
    AuthMailDeliveryError,
    ActivatedAccount,
    InitialPasswordUnavailableError,
    InvalidChallengeError,
    PasswordPolicyError,
    RequestReceipt,
    request_password_reset,
    request_registration,
    reset_password,
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
            "kind": "verification",
            "email": email,
            "verification_url": verification_url,
            "idempotency_key": idempotency_key,
        })
        return "fake-provider-id"

    def send_account_guidance(
            self, email, login_url, forgot_password_url, idempotency_key):
        event_id = int(idempotency_key.split(":", 1)[1])
        with self.bypass_engine.connect() as conn:
            event = conn.execute(text("""
                SELECT id, challenge_id, purpose, delivery_status
                FROM auth_mail_events
                WHERE id = :event_id
            """), {"event_id": event_id}).mappings().one()
            assert event["purpose"] == "account_guidance"
            assert event["delivery_status"] == "reserved"
            assert event["challenge_id"] is None

        self.calls.append({
            "kind": "guidance",
            "email": email,
            "login_url": login_url,
            "forgot_password_url": forgot_password_url,
            "idempotency_key": idempotency_key,
        })
        return "fake-guidance-provider-id"

    def send_password_reset(self, email, reset_url, idempotency_key):
        event_id = int(idempotency_key.split(":", 1)[1])
        with self.bypass_engine.connect() as conn:
            event = conn.execute(text("""
                SELECT id, challenge_id, purpose, delivery_status
                FROM auth_mail_events
                WHERE id = :event_id
            """), {"event_id": event_id}).mappings().one()
            assert event["purpose"] == "password_reset"
            assert event["delivery_status"] == "reserved"
            assert event["challenge_id"] is not None

            challenge = conn.execute(text("""
                SELECT purpose, user_id
                FROM auth_challenges
                WHERE id = :challenge_id
            """), {"challenge_id": event["challenge_id"]}).mappings().one()
            assert challenge["purpose"] == "password_reset"
            assert challenge["user_id"] is not None

        self.calls.append({
            "kind": "password_reset",
            "email": email,
            "reset_url": reset_url,
            "idempotency_key": idempotency_key,
        })
        return "fake-reset-provider-id"


class FailingMailer:
    def send_registration_verification(
            self, email, verification_url, idempotency_key):
        raise AuthMailDeliveryError()

    def send_account_guidance(
            self, email, login_url, forgot_password_url, idempotency_key):
        raise AuthMailDeliveryError()

    def send_password_reset(self, email, reset_url, idempotency_key):
        raise AuthMailDeliveryError()


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


def test_two_registration_tokens_for_same_email_create_one_account_and_one_stable_error(
        app, bypass_engine):
    app.config["PUBLIC_BASE_URL"] = "https://example.test"
    mailer = RecordingMailer(bypass_engine)
    app.extensions["auth_mailer"] = mailer

    with app.app_context():
        first_receipt = request_registration(
            " Alice@Example.COM ",
            "client-key-1",
        )
        second_receipt = request_registration(
            "alice@example.com",
            "client-key-2",
        )

    assert first_receipt == second_receipt == RequestReceipt(
        outcome="accepted"
    )
    raw_tokens = [
        unquote(urlsplit(call["verification_url"]).path.rsplit("/", 1)[-1])
        for call in mailer.calls
        if call["kind"] == "verification"
    ]
    assert len(raw_tokens) == 2
    assert len(set(raw_tokens)) == 2

    barrier = Barrier(2)

    def verify_once(raw_token):
        thread_app = create_app("testing")
        with thread_app.app_context():
            barrier.wait()
            try:
                return ("account", verify_registration(raw_token))
            except InvalidChallengeError:
                return ("invalid",)

    with ThreadPoolExecutor(max_workers=2) as executor:
        futures = [
            executor.submit(verify_once, raw_token)
            for raw_token in raw_tokens
        ]
        results = [future.result() for future in futures]

    accounts = [result[1] for result in results if result[0] == "account"]
    invalids = [result for result in results if result[0] == "invalid"]
    assert len(accounts) == 1
    assert len(invalids) == 1
    assert isinstance(accounts[0], ActivatedAccount)

    with app.app_context():
        for raw_token in raw_tokens:
            try:
                verify_registration(raw_token)
            except InvalidChallengeError:
                pass
            else:
                raise AssertionError("registration token was reusable")

    with bypass_engine.connect() as conn:
        challenges = conn.execute(text("""
            SELECT purpose, consumed_at
            FROM auth_challenges
            WHERE email = 'alice@example.com'
            ORDER BY id
        """)).mappings().all()
        users = conn.execute(text("""
            SELECT id, public_id, password_setup_required, display_name
            FROM users
        """)).mappings().all()
        settings = conn.execute(text(
            "SELECT count(*) AS count FROM user_settings"
        )).scalar_one()
        quota = conn.execute(text(
            "SELECT count(*) AS count FROM user_quota"
        )).scalar_one()

    assert len(challenges) == 2
    assert all(challenge["purpose"] == "registration" for challenge in challenges)
    assert all(challenge["consumed_at"] is not None for challenge in challenges)
    assert len(users) == 1
    assert users[0]["id"] == accounts[0].user_id
    assert users[0]["public_id"] is not None
    assert users[0]["password_setup_required"] is True
    assert users[0]["display_name"] == "alice"
    assert settings == 1
    assert quota == 1


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


def test_existing_email_sends_guidance_without_registration_challenge(
        app, bypass_engine):
    app.config["PUBLIC_BASE_URL"] = "https://example.test"
    mailer = RecordingMailer(bypass_engine)
    app.extensions["auth_mailer"] = mailer

    with app.app_context():
        existing_user_id, _ = create_user_with_defaults(
            "Alice@Example.COM",
            "Alice",
        )
        existing_receipt = request_registration(
            " alice@example.com ",
            "client-key-existing",
        )
        new_receipt = request_registration(
            "new@example.com",
            "client-key-new",
        )

    assert existing_receipt == new_receipt == RequestReceipt(
        outcome="accepted"
    )
    guidance = next(call for call in mailer.calls if call["kind"] == "guidance")
    verification = next(
        call for call in mailer.calls if call["kind"] == "verification"
    )
    assert guidance["email"] == "alice@example.com"
    assert guidance["login_url"] == "https://example.test/login"
    assert guidance["forgot_password_url"] == (
        "https://example.test/forgot-password"
    )
    assert verification["email"] == "new@example.com"

    with bypass_engine.connect() as conn:
        existing_user_count = conn.execute(text("""
            SELECT count(*)
            FROM users
            WHERE id = :user_id AND email = 'alice@example.com'
        """), {"user_id": existing_user_id}).scalar_one()
        existing_challenges = conn.execute(text("""
            SELECT count(*)
            FROM auth_challenges
            WHERE email = 'alice@example.com'
        """)).scalar_one()
        existing_event = conn.execute(text("""
            SELECT id, challenge_id, purpose, delivery_status,
                   provider_message_id
            FROM auth_mail_events
            WHERE email = 'alice@example.com'
        """)).mappings().one()
        new_challenge = conn.execute(text("""
            SELECT id, purpose
            FROM auth_challenges
            WHERE email = 'new@example.com'
        """)).mappings().one()
        new_event = conn.execute(text("""
            SELECT id, challenge_id, purpose, delivery_status,
                   provider_message_id
            FROM auth_mail_events
            WHERE email = 'new@example.com'
        """)).mappings().one()

    assert existing_user_count == 1
    assert existing_challenges == 0
    assert existing_event["challenge_id"] is None
    assert existing_event["purpose"] == "account_guidance"
    assert existing_event["delivery_status"] == "sent"
    assert existing_event["provider_message_id"] == (
        "fake-guidance-provider-id"
    )
    assert guidance["idempotency_key"] == (
        f"account-guidance:{existing_event['id']}"
    )
    assert new_challenge["purpose"] == "registration"
    assert new_event["challenge_id"] == new_challenge["id"]
    assert new_event["purpose"] == "registration"
    assert new_event["delivery_status"] == "sent"
    assert new_event["provider_message_id"] == "fake-provider-id"
    assert verification["idempotency_key"] == (
        f"registration:{new_event['id']}"
    )


def test_registration_mail_failure_is_retryable_without_account_creation(
        app, bypass_engine):
    app.config["PUBLIC_BASE_URL"] = "https://example.test"

    with app.app_context():
        existing_user_id, _ = create_user_with_defaults(
            "Alice@Example.COM",
            "Alice",
        )
        app.extensions["auth_mailer"] = FailingMailer()
        new_receipt = request_registration(
            "new@example.com",
            "client-key-new",
        )
        existing_receipt = request_registration(
            " alice@example.com ",
            "client-key-existing",
        )

    assert new_receipt == existing_receipt == RequestReceipt(
        outcome="retry_later"
    )
    with bypass_engine.connect() as conn:
        events = conn.execute(text("""
            SELECT purpose, challenge_id, delivery_status,
                   provider_message_id
            FROM auth_mail_events
            ORDER BY id
        """)).mappings().all()
        challenge_count = conn.execute(text(
            "SELECT count(*) FROM auth_challenges"
        )).scalar_one()
        user_count = conn.execute(text(
            "SELECT count(*) FROM users"
        )).scalar_one()

    assert len(events) == 2
    assert {event["purpose"] for event in events} == {
        "registration",
        "account_guidance",
    }
    assert all(event["delivery_status"] == "failed" for event in events)
    assert all(event["provider_message_id"] is None for event in events)
    assert next(
        event for event in events if event["purpose"] == "registration"
    )["challenge_id"] is None
    assert challenge_count == 0
    assert user_count == 1

    with app.app_context():
        app.extensions["auth_mailer"] = RecordingMailer(bypass_engine)
        retry_receipt = request_registration(
            "new@example.com",
            "client-key-new-retry",
        )

    assert retry_receipt == RequestReceipt(outcome="accepted")
    with bypass_engine.connect() as conn:
        challenges = conn.execute(text("""
            SELECT id, token_digest, purpose, expires_at, created_at
            FROM auth_challenges
            WHERE email = 'new@example.com'
        """)).mappings().all()
        sent_event = conn.execute(text("""
            SELECT challenge_id, delivery_status, provider_message_id
            FROM auth_mail_events
            WHERE email = 'new@example.com'
              AND delivery_status = 'sent'
        """)).mappings().one()
        final_user_count = conn.execute(text(
            "SELECT count(*) FROM users"
        )).scalar_one()

    assert len(challenges) == 1
    assert len(challenges[0]["token_digest"]) == 64
    assert challenges[0]["purpose"] == "registration"
    assert challenges[0]["expires_at"] > challenges[0]["created_at"]
    assert sent_event["challenge_id"] == challenges[0]["id"]
    assert sent_event["delivery_status"] == "sent"
    assert sent_event["provider_message_id"] == "fake-provider-id"
    assert final_user_count == 1
    assert existing_user_id > 0


def test_password_reset_is_non_enumerating_and_records_digest(
        app, bypass_engine):
    app.config["PUBLIC_BASE_URL"] = "https://example.test"
    mailer = RecordingMailer(bypass_engine)
    app.extensions["auth_mailer"] = mailer

    with app.app_context():
        existing_user_id, _ = create_user_with_defaults(
            "Alice@Example.COM",
            "Alice",
        )
        unknown_receipt = request_password_reset(
            "unknown@example.com",
            "client-key-unknown",
        )
        existing_receipt = request_password_reset(
            " alice@example.com ",
            "client-key-reset",
        )

    assert unknown_receipt == existing_receipt == RequestReceipt(
        outcome="accepted"
    )
    assert len(mailer.calls) == 1
    call = mailer.calls[0]
    assert call["kind"] == "password_reset"
    assert call["email"] == "alice@example.com"
    url = urlsplit(call["reset_url"])
    raw_token = unquote(url.path.rsplit("/", 1)[-1])
    assert raw_token
    assert url.scheme == "https"
    assert url.netloc == "example.test"
    assert url.path == f"/reset-password/{raw_token}"

    expected_token_digest = sha256(raw_token.encode("utf-8")).hexdigest()
    expected_client_digest = sha256(b"client-key-reset").hexdigest()
    with bypass_engine.connect() as conn:
        unknown_challenges = conn.execute(text("""
            SELECT count(*)
            FROM auth_challenges
            WHERE email = 'unknown@example.com'
        """)).scalar_one()
        unknown_events = conn.execute(text("""
            SELECT count(*)
            FROM auth_mail_events
            WHERE email = 'unknown@example.com'
        """)).scalar_one()
        challenge = conn.execute(text("""
            SELECT id, token_digest, purpose, email, user_id,
                   expires_at, created_at
            FROM auth_challenges
            WHERE email = 'alice@example.com'
        """)).mappings().one()
        event = conn.execute(text("""
            SELECT id, challenge_id, purpose, email, client_key_digest,
                   delivery_status, provider_message_id
            FROM auth_mail_events
            WHERE email = 'alice@example.com'
        """)).mappings().one()
        user_count = conn.execute(text(
            "SELECT count(*) FROM users"
        )).scalar_one()

    assert app.config["PASSWORD_RESET_TOKEN_TTL_SECONDS"] == 3_600
    assert unknown_challenges == 0
    assert unknown_events == 0
    assert challenge["token_digest"] == expected_token_digest
    assert raw_token not in challenge["token_digest"]
    assert challenge["purpose"] == "password_reset"
    assert challenge["email"] == "alice@example.com"
    assert challenge["user_id"] == existing_user_id
    assert timedelta(seconds=3_599) <= (
        challenge["expires_at"] - challenge["created_at"]
    ) <= timedelta(seconds=3_601)
    assert event["challenge_id"] == challenge["id"]
    assert event["purpose"] == "password_reset"
    assert event["email"] == "alice@example.com"
    assert event["client_key_digest"] == expected_client_digest
    assert event["delivery_status"] == "sent"
    assert event["provider_message_id"] == "fake-reset-provider-id"
    assert call["idempotency_key"] == f"password-reset:{event['id']}"
    assert user_count == 1


def test_expired_and_missing_challenges_use_one_invalid_error_without_mutation(
        app, bypass_engine):
    app.config["PUBLIC_BASE_URL"] = "https://example.test"
    mailer = RecordingMailer(bypass_engine)
    app.extensions["auth_mailer"] = mailer

    with app.app_context():
        existing_user_id, _ = create_user_with_defaults(
            "Alice@Example.COM",
            "Alice",
        )
        request_registration("new@example.com", "client-key-registration")
        request_password_reset("alice@example.com", "client-key-reset")

    registration_token = unquote(
        next(
            call for call in mailer.calls
            if call["kind"] == "verification"
        )["verification_url"].rsplit("/", 1)[-1]
    )
    reset_token = unquote(
        next(
            call for call in mailer.calls
            if call["kind"] == "password_reset"
        )["reset_url"].rsplit("/", 1)[-1]
    )

    with bypass_engine.begin() as conn:
        conn.execute(text("""
            UPDATE auth_challenges
            SET expires_at = now() - interval '1 second'
            WHERE (email = 'new@example.com' AND purpose = 'registration')
               OR (email = 'alice@example.com' AND purpose = 'password_reset')
        """))
        before_user = conn.execute(text("""
            SELECT password_hash, password_setup_required
            FROM users
            WHERE id = :user_id
        """), {"user_id": existing_user_id}).mappings().one()
        before_challenges = conn.execute(text("""
            SELECT purpose, consumed_at
            FROM auth_challenges
            ORDER BY id
        """)).mappings().all()

    def assert_invalid(call):
        try:
            call()
        except InvalidChallengeError:
            return
        except Exception as error:
            raise AssertionError(
                f"unexpected challenge error: {type(error).__name__}"
            ) from error
        raise AssertionError("challenge was accepted")

    with app.app_context():
        assert_invalid(lambda: verify_registration(registration_token))
        assert_invalid(
            lambda: reset_password(reset_token, "NewPass123")
        )
        assert_invalid(lambda: verify_registration("missing-registration"))
        assert_invalid(lambda: reset_password("missing-reset", "NewPass123"))

    with bypass_engine.connect() as conn:
        after_user = conn.execute(text("""
            SELECT password_hash, password_setup_required
            FROM users
            WHERE id = :user_id
        """), {"user_id": existing_user_id}).mappings().one()
        after_challenges = conn.execute(text("""
            SELECT purpose, consumed_at
            FROM auth_challenges
            ORDER BY id
        """)).mappings().all()
        user_count = conn.execute(text(
            "SELECT count(*) FROM users"
        )).scalar_one()

    assert after_user == before_user
    assert after_challenges == before_challenges
    assert user_count == 1


def test_password_reset_mail_failure_is_retryable_and_compensated(
        app, bypass_engine):
    app.config["PUBLIC_BASE_URL"] = "https://example.test"

    with app.app_context():
        existing_user_id, _ = create_user_with_defaults(
            "Alice@Example.COM",
            "Alice",
        )
        app.extensions["auth_mailer"] = FailingMailer()
        failed_receipt = request_password_reset(
            " alice@example.com ",
            "client-key-reset",
        )

    assert failed_receipt == RequestReceipt(outcome="retry_later")
    with bypass_engine.connect() as conn:
        failed_event = conn.execute(text("""
            SELECT challenge_id, delivery_status, provider_message_id
            FROM auth_mail_events
            WHERE purpose = 'password_reset'
        """)).mappings().one()
        challenge_count = conn.execute(text("""
            SELECT count(*)
            FROM auth_challenges
            WHERE purpose = 'password_reset'
        """)).scalar_one()

    assert failed_event["challenge_id"] is None
    assert failed_event["delivery_status"] == "failed"
    assert failed_event["provider_message_id"] is None
    assert challenge_count == 0

    retry_mailer = RecordingMailer(bypass_engine)
    with app.app_context():
        app.extensions["auth_mailer"] = retry_mailer
        retry_receipt = request_password_reset(
            "alice@example.com",
            "client-key-reset-retry",
        )

    assert retry_receipt == RequestReceipt(outcome="accepted")
    assert len(retry_mailer.calls) == 1
    assert retry_mailer.calls[0]["kind"] == "password_reset"
    with bypass_engine.connect() as conn:
        sent_event = conn.execute(text("""
            SELECT challenge_id, delivery_status, provider_message_id
            FROM auth_mail_events
            WHERE purpose = 'password_reset'
              AND delivery_status = 'sent'
        """)).mappings().one()
        final_challenge_count = conn.execute(text("""
            SELECT count(*)
            FROM auth_challenges
            WHERE purpose = 'password_reset'
        """)).scalar_one()
        user_count = conn.execute(text(
            "SELECT count(*) FROM users"
        )).scalar_one()

    assert sent_event["challenge_id"] is not None
    assert sent_event["delivery_status"] == "sent"
    assert sent_event["provider_message_id"] == "fake-reset-provider-id"
    assert final_challenge_count == 1
    assert user_count == 1
    assert existing_user_id > 0


def test_same_password_reset_token_concurrent_consumption_is_one_time(
        app, bypass_engine):
    app.config["PUBLIC_BASE_URL"] = "https://example.test"
    mailer = RecordingMailer(bypass_engine)
    app.extensions["auth_mailer"] = mailer

    with app.app_context():
        user_id, _ = create_user_with_defaults(
            "Alice@Example.COM",
            "Alice",
        )
        with bypass_engine.begin() as conn:
            conn.execute(text("""
                UPDATE users
                SET password_setup_required = TRUE
                WHERE id = :user_id
            """), {"user_id": user_id})
        request_password_reset("alice@example.com", "client-key-reset")

    raw_token = unquote(
        urlsplit(mailer.calls[0]["reset_url"]).path.rsplit("/", 1)[-1]
    )
    with bypass_engine.connect() as conn:
        before_user = conn.execute(text("""
            SELECT password_hash, password_setup_required
            FROM users
            WHERE id = :user_id
        """), {"user_id": user_id}).mappings().one()
        before_challenge = conn.execute(text("""
            SELECT id, consumed_at
            FROM auth_challenges
            WHERE email = 'alice@example.com'
              AND purpose = 'password_reset'
        """)).mappings().one()

    with app.app_context():
        try:
            reset_password(raw_token, "short")
        except PasswordPolicyError:
            pass
        else:
            raise AssertionError("short reset password was accepted")

    with bypass_engine.connect() as conn:
        after_short_user = conn.execute(text("""
            SELECT password_hash, password_setup_required
            FROM users
            WHERE id = :user_id
        """), {"user_id": user_id}).mappings().one()
        after_short_challenge = conn.execute(text("""
            SELECT consumed_at
            FROM auth_challenges
            WHERE id = :challenge_id
        """), {"challenge_id": before_challenge["id"]}).mappings().one()

    assert after_short_user == before_user
    assert after_short_challenge["consumed_at"] == (
        before_challenge["consumed_at"]
    )

    barrier = Barrier(2)

    def reset_once():
        thread_app = create_app("testing")
        with thread_app.app_context():
            barrier.wait()
            try:
                return ("user", reset_password(raw_token, "NewPass123"))
            except InvalidChallengeError:
                return ("invalid",)

    with ThreadPoolExecutor(max_workers=2) as executor:
        futures = [executor.submit(reset_once) for _ in range(2)]
        results = [future.result() for future in futures]

    user_results = [result[1] for result in results if result[0] == "user"]
    invalid_results = [result for result in results if result[0] == "invalid"]
    assert user_results == [user_id]
    assert len(invalid_results) == 1

    with bypass_engine.connect() as conn:
        final_challenge = conn.execute(text("""
            SELECT consumed_at
            FROM auth_challenges
            WHERE id = :challenge_id
        """), {"challenge_id": before_challenge["id"]}).mappings().one()
        final_user = conn.execute(text("""
            SELECT password_hash, password_setup_required
            FROM users
            WHERE id = :user_id
        """), {"user_id": user_id}).mappings().one()

    assert final_challenge["consumed_at"] is not None
    assert check_password_hash(final_user["password_hash"], "NewPass123")
    assert final_user["password_setup_required"] is False
