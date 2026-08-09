"""OR2 Slice 1：注册 challenge 发放与邮件 seam。"""
from datetime import timedelta
from hashlib import sha256
from urllib.parse import unquote, urlsplit

from sqlalchemy import text

from app.services.account_access import RequestReceipt, request_registration


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
