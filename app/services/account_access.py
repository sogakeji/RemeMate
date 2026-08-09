"""OR2 账号访问深模块：注册、验证、首次设密、密码重置与认证邮件 seam。"""
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from hashlib import sha256
from secrets import token_urlsafe
from urllib.parse import quote

from flask import current_app
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError
from werkzeug.security import generate_password_hash

from app.models.account_access import AuthChallenge, AuthMailEvent
from app.models.user import User
from app.services.provisioning import (
    _bypass_session,
    _create_user_with_defaults_in_session,
    normalize_email,
    UserExistsError,
)
from app.services.timeutil import utc_now


@dataclass(frozen=True)
class RequestReceipt:
    outcome: str


@dataclass(frozen=True)
class ActivatedAccount:
    user_id: int


class InvalidChallengeError(Exception):
    """A registration or password-reset challenge cannot be activated."""


class PasswordPolicyError(Exception):
    """The initial password does not meet the minimum policy."""


class InitialPasswordUnavailableError(Exception):
    """The user cannot set an initial password."""


class AuthMailDeliveryError(Exception):
    """The authentication mail provider or transport failed."""

    def __init__(self, category="mail_delivery_error", *,
                 status_code=None, error_type=None, retry_after=None):
        self.category = category
        self.status_code = status_code
        self.error_type = error_type
        self.retry_after = retry_after
        super().__init__(category)


def _digest(value: str) -> str:
    return sha256(value.encode("utf-8")).hexdigest()


def _reserve_rate_limits(
        session, email: str, client_key: str, *, increment_global: bool) -> bool:
    """Reserve all applicable UTC rate-limit buckets in a fixed lock order."""
    now = datetime.now(timezone.utc)
    windows = {
        "global_day": now.replace(hour=0, minute=0, second=0, microsecond=0),
        "email_hour": now.replace(minute=0, second=0, microsecond=0),
        "email_minute": now.replace(second=0, microsecond=0),
        "client_hour": now.replace(minute=0, second=0, microsecond=0),
    }
    limits = {
        "global_day": int(current_app.config[
            "AUTH_GLOBAL_EMAIL_PER_DAY_LIMIT"
        ]),
        "email_hour": int(current_app.config[
            "AUTH_EMAIL_PER_HOUR_LIMIT"
        ]),
        "email_minute": int(current_app.config[
            "AUTH_EMAIL_PER_MINUTE_LIMIT"
        ]),
        "client_hour": int(current_app.config[
            "AUTH_CLIENT_PER_HOUR_LIMIT"
        ]),
    }
    keys = {
        "global_day": _digest("auth-rate-limit:global"),
        "email_hour": _digest(email),
        "email_minute": _digest(email),
        "client_hour": _digest(client_key),
    }
    increments = {
        "global_day": increment_global,
        "email_hour": True,
        "email_minute": True,
        "client_hour": True,
    }
    specs = [
        (scope, keys[scope], windows[scope], limits[scope])
        for scope in (
            "global_day",
            "email_hour",
            "email_minute",
            "client_hour",
        )
    ]

    for scope, key_digest, window_start, _limit in specs:
        session.execute(text("""
            INSERT INTO auth_rate_limit_buckets
                (scope, key_digest, window_start)
            VALUES (:scope, :key_digest, :window_start)
            ON CONFLICT (scope, key_digest, window_start) DO NOTHING
        """), {
            "scope": scope,
            "key_digest": key_digest,
            "window_start": window_start,
        })

    locked = []
    for scope, key_digest, window_start, limit in specs:
        row = session.execute(text("""
            SELECT used_count
            FROM auth_rate_limit_buckets
            WHERE scope = :scope
              AND key_digest = :key_digest
              AND window_start = :window_start
            FOR UPDATE
        """), {
            "scope": scope,
            "key_digest": key_digest,
            "window_start": window_start,
        }).mappings().one()
        locked.append((scope, key_digest, window_start, limit, row["used_count"]))

    if any(used_count >= limit for _, _, _, limit, used_count in locked):
        return False

    for scope, key_digest, window_start, _limit, _used_count in locked:
        if not increments[scope]:
            continue
        session.execute(text("""
            UPDATE auth_rate_limit_buckets
            SET used_count = used_count + 1, updated_at = now()
            WHERE scope = :scope
              AND key_digest = :key_digest
              AND window_start = :window_start
        """), {
            "scope": scope,
            "key_digest": key_digest,
            "window_start": window_start,
        })
    return True


def _mark_mail_delivery_failed(event_id: int) -> None:
    session = _bypass_session()
    engine = session.bind
    try:
        event = (
            session.query(AuthMailEvent)
            .filter_by(id=event_id)
            .with_for_update()
            .one()
        )
        event.delivery_status = "failed"
        event.provider_message_id = None
        if (
            event.purpose in {"registration", "password_reset"}
            and event.challenge_id is not None
        ):
            challenge = session.get(AuthChallenge, event.challenge_id)
            if challenge is not None:
                session.delete(challenge)
            event.challenge_id = None
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()
        engine.dispose()


def _consume_registration_challenge(token_digest: str) -> None:
    session = _bypass_session()
    engine = session.bind
    try:
        challenge = (
            session.query(AuthChallenge)
            .filter_by(token_digest=token_digest, purpose="registration")
            .with_for_update()
            .one_or_none()
        )
        if challenge is not None and challenge.consumed_at is None:
            challenge.consumed_at = utc_now()
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()
        engine.dispose()


def request_registration(email: str, client_key: str) -> RequestReceipt:
    """Record a registration challenge and send its verification message."""
    normalized_email = normalize_email(email)
    client_key_digest = _digest(client_key)
    base_url = current_app.config["PUBLIC_BASE_URL"].rstrip("/")

    session = _bypass_session()
    engine = session.bind
    try:
        existing_user = session.query(User).filter_by(
            email=normalized_email
        ).first()
        if not _reserve_rate_limits(
            session, normalized_email, client_key, increment_global=True
        ):
            session.rollback()
            return RequestReceipt(outcome="retry_later")
        if existing_user is not None:
            event = AuthMailEvent(
                challenge_id=None,
                purpose="account_guidance",
                email=normalized_email,
                client_key_digest=client_key_digest,
                delivery_status="reserved",
            )
            session.add(event)
            session.flush()
            delivery_kind = "guidance"
        else:
            raw_token = token_urlsafe(32)
            token_digest = _digest(raw_token)
            now = utc_now()
            ttl_seconds = int(
                current_app.config["REGISTRATION_TOKEN_TTL_SECONDS"]
            )
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
            verification_url = (
                f"{base_url}/verify-email/{quote(raw_token, safe='')}"
            )
            delivery_kind = "verification"
        event_id = event.id
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()
        engine.dispose()

    try:
        if delivery_kind == "guidance":
            idempotency_key = f"account-guidance:{event_id}"
            provider_message_id = current_app.extensions[
                "auth_mailer"
            ].send_account_guidance(
                normalized_email,
                f"{base_url}/login",
                f"{base_url}/forgot-password",
                idempotency_key,
            )
        else:
            idempotency_key = f"registration:{event_id}"
            provider_message_id = current_app.extensions[
                "auth_mailer"
            ].send_registration_verification(
                normalized_email,
                verification_url,
                idempotency_key,
            )
    except AuthMailDeliveryError:
        _mark_mail_delivery_failed(event_id)
        return RequestReceipt(outcome="retry_later")

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


def request_password_reset(email: str, client_key: str) -> RequestReceipt:
    """Record and send one password-reset challenge for an existing user."""
    normalized_email = normalize_email(email)
    client_key_digest = _digest(client_key)
    base_url = current_app.config["PUBLIC_BASE_URL"].rstrip("/")

    session = _bypass_session()
    engine = session.bind
    try:
        user = session.query(User).filter_by(email=normalized_email).first()
        if not _reserve_rate_limits(
            session,
            normalized_email,
            client_key,
            increment_global=user is not None,
        ):
            session.rollback()
            return RequestReceipt(outcome="retry_later")
        if user is None:
            session.commit()
            return RequestReceipt(outcome="accepted")

        raw_token = token_urlsafe(32)
        challenge = AuthChallenge(
            token_digest=_digest(raw_token),
            purpose="password_reset",
            email=normalized_email,
            user_id=user.id,
            expires_at=utc_now() + timedelta(
                seconds=int(
                    current_app.config["PASSWORD_RESET_TOKEN_TTL_SECONDS"]
                )
            ),
        )
        session.add(challenge)
        session.flush()

        event = AuthMailEvent(
            challenge_id=challenge.id,
            purpose="password_reset",
            email=normalized_email,
            client_key_digest=client_key_digest,
            delivery_status="reserved",
        )
        session.add(event)
        session.flush()
        event_id = event.id
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()
        engine.dispose()

    idempotency_key = f"password-reset:{event_id}"
    reset_url = f"{base_url}/reset-password/{quote(raw_token, safe='')}"
    try:
        provider_message_id = current_app.extensions[
            "auth_mailer"
            ].send_password_reset(
                normalized_email,
                reset_url,
                idempotency_key,
            )
    except AuthMailDeliveryError:
        _mark_mail_delivery_failed(event_id)
        return RequestReceipt(outcome="accepted")

    session = _bypass_session()
    engine = session.bind
    try:
        event = session.get(AuthMailEvent, event_id)
        if event is None:
            raise RuntimeError("password reset mail event disappeared")
        event.delivery_status = "sent"
        event.provider_message_id = provider_message_id
        session.commit()
    finally:
        session.close()
        engine.dispose()

    return RequestReceipt(outcome="accepted")


def reset_password(raw_token: str, password: str) -> int:
    """Consume one password-reset challenge and set the user's password."""
    if len(password) < 8:
        raise PasswordPolicyError()

    token_digest = _digest(raw_token)
    session = _bypass_session()
    engine = session.bind
    try:
        challenge = (
            session.query(AuthChallenge)
            .filter_by(token_digest=token_digest, purpose="password_reset")
            .with_for_update()
            .one_or_none()
        )
        if (
            challenge is None
            or challenge.consumed_at is not None
            or challenge.expires_at <= utc_now()
        ):
            raise InvalidChallengeError()

        user = (
            session.query(User)
            .filter_by(id=challenge.user_id)
            .with_for_update()
            .one_or_none()
        )
        if user is None:
            raise InvalidChallengeError()

        user.password_hash = generate_password_hash(password)
        user.password_setup_required = False
        challenge.consumed_at = utc_now()
        user_id = user.id
        session.commit()
        return user_id
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()
        engine.dispose()


def verify_registration(raw_token: str) -> ActivatedAccount:
    """Activate one registration challenge and create its initial account."""
    token_digest = _digest(raw_token)
    session = _bypass_session()
    engine = session.bind
    try:
        challenge = (
            session.query(AuthChallenge)
            .filter_by(token_digest=token_digest, purpose="registration")
            .with_for_update()
            .one_or_none()
        )
        if (
            challenge is None
            or challenge.consumed_at is not None
            or challenge.expires_at <= utc_now()
        ):
            raise InvalidChallengeError()

        normalized_email = normalize_email(challenge.email)
        user = _create_user_with_defaults_in_session(
            session,
            normalized_email,
            normalized_email.split("@", 1)[0],
            password_setup_required=True,
        )
        user_id = user.id
        challenge.consumed_at = utc_now()
        session.commit()
        return ActivatedAccount(user_id=user_id)
    except Exception as error:
        session.rollback()
        is_email_conflict = isinstance(error, UserExistsError)
        if isinstance(error, IntegrityError):
            diagnostic = getattr(getattr(error, "orig", None), "diag", None)
            is_email_conflict = (
                getattr(diagnostic, "constraint_name", None)
                == "users_email_key"
            )
        if (
            is_email_conflict
            and "normalized_email" in locals()
            and session.query(User).filter_by(email=normalized_email).first()
            is not None
        ):
            _consume_registration_challenge(token_digest)
            raise InvalidChallengeError() from None
        raise
    finally:
        session.close()
        engine.dispose()


def set_initial_password(user_id: int, password: str) -> None:
    """Set a newly activated user's password exactly once."""
    if len(password) < 8:
        raise PasswordPolicyError()

    session = _bypass_session()
    engine = session.bind
    try:
        user = (
            session.query(User)
            .filter_by(id=user_id)
            .with_for_update()
            .one_or_none()
        )
        if user is None or not user.password_setup_required:
            raise InitialPasswordUnavailableError()

        user.password_hash = generate_password_hash(password)
        user.password_setup_required = False
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()
        engine.dispose()


__all__ = [
    "ActivatedAccount",
    "AuthMailDeliveryError",
    "InitialPasswordUnavailableError",
    "InvalidChallengeError",
    "PasswordPolicyError",
    "RequestReceipt",
    "request_registration",
    "request_password_reset",
    "reset_password",
    "set_initial_password",
    "verify_registration",
]
