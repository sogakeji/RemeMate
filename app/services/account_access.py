"""开放注册 Slice 1：注册 challenge 发放与邮件 seam。"""
from dataclasses import dataclass
from datetime import timedelta
from hashlib import sha256
from secrets import token_urlsafe
from urllib.parse import quote

from flask import current_app

from app.models.account_access import AuthChallenge, AuthMailEvent
from app.services.provisioning import _bypass_session, normalize_email
from app.services.timeutil import utc_now


@dataclass(frozen=True)
class RequestReceipt:
    outcome: str


def _digest(value: str) -> str:
    return sha256(value.encode("utf-8")).hexdigest()


def request_registration(email: str, client_key: str) -> RequestReceipt:
    """Record a registration challenge and send its verification message."""
    normalized_email = normalize_email(email)
    raw_token = token_urlsafe(32)
    token_digest = _digest(raw_token)
    client_key_digest = _digest(client_key)
    now = utc_now()
    ttl_seconds = int(current_app.config["REGISTRATION_TOKEN_TTL_SECONDS"])
    base_url = current_app.config["PUBLIC_BASE_URL"].rstrip("/")
    verification_url = (
        f"{base_url}/verify-email/{quote(raw_token, safe='')}"
    )

    session = _bypass_session()
    engine = session.bind
    try:
        challenge = AuthChallenge(
            token_digest=token_digest,
            purpose="registration",
            email=normalized_email,
            user_id=None,
            expires_at=now + timedelta(seconds=ttl_seconds),
        )
        session.add(challenge)
        session.flush()

        event = AuthMailEvent(
            challenge_id=challenge.id,
            purpose="registration",
            email=normalized_email,
            client_key_digest=client_key_digest,
            delivery_status="reserved",
        )
        session.add(event)
        session.flush()
        event_id = event.id
        session.commit()
    finally:
        session.close()
        engine.dispose()

    idempotency_key = f"registration:{event_id}"
    provider_message_id = current_app.extensions[
        "auth_mailer"
    ].send_registration_verification(
        normalized_email,
        verification_url,
        idempotency_key,
    )

    session = _bypass_session()
    engine = session.bind
    try:
        event = session.get(AuthMailEvent, event_id)
        if event is None:
            raise RuntimeError("registration mail event disappeared")
        event.delivery_status = "sent"
        event.provider_message_id = provider_message_id
        session.commit()
    finally:
        session.close()
        engine.dispose()

    return RequestReceipt(outcome="accepted")


__all__ = ["RequestReceipt", "request_registration"]
