"""Account-bound invitations for claiming a language-partner profile."""
from __future__ import annotations

import base64
import hashlib
import hmac
import re
import time
from dataclasses import dataclass
from urllib.parse import urljoin

from sqlalchemy import text


DEFAULT_TTL_SECONDS = 7 * 24 * 60 * 60
_TOKEN_VERSION = "v1"
_SIG_LEN = 27
_EMAIL_FINGERPRINT_LEN = 22
_EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


@dataclass(frozen=True)
class PartnerInviteToken:
    owner_user_id: int
    partner_id: int
    exp: int


@dataclass(frozen=True)
class PartnerInvitePreview:
    owner_display_name: str


@dataclass(frozen=True)
class PartnerInviteResult:
    owner_user_id: int
    owner_display_name: str


@dataclass(frozen=True)
class ReciprocalPartnerPreview:
    owner_user_id: int
    owner_display_name: str
    native_language_code: str | None
    learning_language_code: str | None
    existing_partner_id: int | None


@dataclass(frozen=True)
class ReciprocalPartnerResult:
    partner_id: int
    state: str


def normalize_recipient_email(email: str | None) -> str:
    normalized = (email or "").strip().lower()
    if len(normalized) > 255 or not _EMAIL_RE.match(normalized):
        raise ValueError("请输入有效的对方登录邮箱")
    return normalized


def make_partner_invite_token(
    secret: str,
    owner_user_id: int,
    partner_id: int,
    recipient_email: str,
    *,
    ttl_seconds: int = DEFAULT_TTL_SECONDS,
    now_ts: int | None = None,
) -> str:
    email = normalize_recipient_email(recipient_email)
    exp = int(now_ts if now_ts is not None else time.time()) + ttl_seconds
    fingerprint = _email_fingerprint(secret, email)
    payload = (
        f"{_TOKEN_VERSION}.{int(owner_user_id)}.{int(partner_id)}."
        f"{exp}.{fingerprint}"
    )
    return f"{payload}.{_sign(secret, payload)}"


def verify_partner_invite_token(
    secret: str,
    token: str,
    recipient_email: str,
    *,
    now_ts: int | None = None,
) -> PartnerInviteToken | None:
    try:
        version, owner_s, partner_s, exp_s, fingerprint, sig = (
            (token or "").split(".")
        )
        if version != _TOKEN_VERSION:
            return None
        payload = f"{version}.{owner_s}.{partner_s}.{exp_s}.{fingerprint}"
        if not hmac.compare_digest(sig, _sign(secret, payload)):
            return None
        email = normalize_recipient_email(recipient_email)
        if not hmac.compare_digest(
            fingerprint, _email_fingerprint(secret, email),
        ):
            return None
        exp = int(exp_s)
        now = int(now_ts if now_ts is not None else time.time())
        if exp < now:
            return None
        return PartnerInviteToken(
            owner_user_id=int(owner_s),
            partner_id=int(partner_s),
            exp=exp,
        )
    except (TypeError, ValueError):
        return None


def partner_invite_url(public_base_url: str, token: str) -> str:
    return urljoin(
        public_base_url.rstrip("/") + "/",
        f"partners/invitations/{token}",
    )


def partner_invite_token_hash(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def preview_partner_invite(
    conn,
    secret: str,
    token: str,
    recipient_email: str,
) -> PartnerInvitePreview | None:
    parsed = verify_partner_invite_token(secret, token, recipient_email)
    if parsed is None:
        return None
    row = conn.execute(text(
        """
        SELECT owner.display_name AS owner_display_name
        FROM language_partners partner
        JOIN users owner ON owner.id = partner.user_id
        WHERE partner.id = :partner_id
          AND partner.user_id = :owner_user_id
          AND partner.linked_user_id IS NULL
          AND partner.invite_token_hash = :token_hash
          AND owner.is_active = true
        """
    ), {
        "partner_id": parsed.partner_id,
        "owner_user_id": parsed.owner_user_id,
        "token_hash": partner_invite_token_hash(token),
    }).mappings().first()
    if row is None:
        return None
    return PartnerInvitePreview(**dict(row))


def accept_partner_invite(
    conn,
    secret: str,
    token: str,
    recipient_user_id: int,
    recipient_email: str,
) -> PartnerInviteResult | None:
    parsed = verify_partner_invite_token(secret, token, recipient_email)
    if parsed is None:
        return None
    if parsed.owner_user_id == recipient_user_id:
        raise ValueError("不能绑定自己的账号")

    recipient = conn.execute(text(
        """
        SELECT id
        FROM users
        WHERE id = :recipient_user_id
          AND lower(email) = :recipient_email
          AND is_active = true
        """
    ), {
        "recipient_user_id": recipient_user_id,
        "recipient_email": normalize_recipient_email(recipient_email),
    }).first()
    if recipient is None:
        return None

    # Lock all profiles owned by the inviter. This serializes two concurrent
    # claims aimed at the same recipient before the unique constraint is hit.
    conn.execute(text(
        "SELECT id FROM language_partners "
        "WHERE user_id = :owner_user_id FOR UPDATE"
    ), {"owner_user_id": parsed.owner_user_id}).all()
    row = conn.execute(text(
        """
        SELECT partner.linked_user_id,
               owner.display_name AS owner_display_name
        FROM language_partners partner
        JOIN users owner ON owner.id = partner.user_id
        WHERE partner.id = :partner_id
          AND partner.user_id = :owner_user_id
          AND partner.invite_token_hash = :token_hash
          AND owner.is_active = true
        FOR UPDATE OF partner
        """
    ), {
        "partner_id": parsed.partner_id,
        "owner_user_id": parsed.owner_user_id,
        "token_hash": partner_invite_token_hash(token),
    }).mappings().first()
    if row is None:
        return None
    if row["linked_user_id"] is not None:
        return None

    duplicate = conn.execute(text(
        """
        SELECT id FROM language_partners
        WHERE user_id = :owner_user_id
          AND linked_user_id = :recipient_user_id
          AND id <> :partner_id
        """
    ), {
        "owner_user_id": parsed.owner_user_id,
        "recipient_user_id": recipient_user_id,
        "partner_id": parsed.partner_id,
    }).first()
    if duplicate is not None:
        return None

    conn.execute(text(
        """
        UPDATE language_partners
        SET linked_user_id = :recipient_user_id,
            invite_token_hash = NULL,
            updated_at = now()
        WHERE id = :partner_id AND user_id = :owner_user_id
        """
    ), {
        "recipient_user_id": recipient_user_id,
        "partner_id": parsed.partner_id,
        "owner_user_id": parsed.owner_user_id,
    })
    return PartnerInviteResult(
        owner_user_id=parsed.owner_user_id,
        owner_display_name=row["owner_display_name"],
    )


def preview_reciprocal_partner(
    conn,
    recipient_user_id: int,
    owner_user_id: int,
) -> ReciprocalPartnerPreview | None:
    """Preview B's private profile for A from an established A-to-B link."""
    row = conn.execute(text(
        """
        SELECT owner.id AS owner_user_id,
               owner.display_name AS owner_display_name,
               source.learning_language_code AS native_language_code,
               source.native_language_code AS learning_language_code,
               reciprocal.id AS existing_partner_id
        FROM language_partners source
        JOIN users owner ON owner.id = source.user_id
        LEFT JOIN language_partners reciprocal
          ON reciprocal.user_id = :recipient_user_id
         AND reciprocal.linked_user_id = owner.id
        WHERE source.user_id = :owner_user_id
          AND source.linked_user_id = :recipient_user_id
          AND owner.is_active = true
        """
    ), {
        "recipient_user_id": recipient_user_id,
        "owner_user_id": owner_user_id,
    }).mappings().first()
    if row is None:
        return None
    return ReciprocalPartnerPreview(**dict(row))


def create_reciprocal_partner(
    conn,
    recipient_user_id: int,
    owner_user_id: int,
) -> ReciprocalPartnerResult | None:
    """Create B-to-A after A-to-B exists; never copy private relationship data."""
    preview = preview_reciprocal_partner(
        conn, recipient_user_id, owner_user_id,
    )
    if preview is None:
        return None
    if preview.existing_partner_id is not None:
        return ReciprocalPartnerResult(
            partner_id=preview.existing_partner_id,
            state="existing",
        )

    partner_id = conn.execute(text(
        """
        INSERT INTO language_partners(
            user_id, linked_user_id, display_name,
            native_language_code, learning_language_code,
            private_note, created_at, updated_at
        ) VALUES (
            :recipient_user_id, :owner_user_id, :owner_display_name,
            :native_language_code, :learning_language_code,
            NULL, now(), now()
        )
        ON CONFLICT (user_id, linked_user_id) DO NOTHING
        RETURNING id
        """
    ), {
        "recipient_user_id": recipient_user_id,
        "owner_user_id": owner_user_id,
        "owner_display_name": preview.owner_display_name,
        "native_language_code": preview.native_language_code,
        "learning_language_code": preview.learning_language_code,
    }).scalar()
    if partner_id is not None:
        return ReciprocalPartnerResult(partner_id=partner_id, state="created")

    existing_id = conn.execute(text(
        """
        SELECT id FROM language_partners
        WHERE user_id = :recipient_user_id
          AND linked_user_id = :owner_user_id
        """
    ), {
        "recipient_user_id": recipient_user_id,
        "owner_user_id": owner_user_id,
    }).scalar()
    if existing_id is None:
        return None
    return ReciprocalPartnerResult(partner_id=existing_id, state="existing")


def _sign(secret: str, payload: str) -> str:
    digest = hmac.new(
        secret.encode("utf-8"), payload.encode("utf-8"), hashlib.sha256,
    ).digest()
    return base64.urlsafe_b64encode(digest).decode("ascii").rstrip("=")[:_SIG_LEN]


def _email_fingerprint(secret: str, email: str) -> str:
    digest = hmac.new(
        secret.encode("utf-8"),
        f"partner-email:{email}".encode("utf-8"),
        hashlib.sha256,
    ).digest()
    return (
        base64.urlsafe_b64encode(digest).decode("ascii").rstrip("=")
        [:_EMAIL_FINGERPRINT_LEN]
    )
