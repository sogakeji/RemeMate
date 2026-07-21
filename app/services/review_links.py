"""Signed review links for Bark notification callbacks.

The link grants access to exactly one word review card without logging in. It
does not create a session and it does not expose general user data.
"""
from __future__ import annotations

import base64
import hashlib
import hmac
import time
from dataclasses import dataclass
from datetime import datetime
from types import SimpleNamespace
from urllib.parse import urljoin

from sqlalchemy import text

from app.services import srs
from app.services.timeutil import utc_now


DEFAULT_TTL_SECONDS = 7 * 24 * 60 * 60
_SIG_LEN = 27
_TOKEN_VERSION = "v1"


@dataclass(frozen=True)
class ReviewToken:
    user_id: int
    word_id: int
    exp: int


@dataclass(frozen=True)
class ReviewLinkWord:
    user_id: int
    word_id: int
    word: str
    language_code: str
    part_of_speech: str
    meaning: str
    example: str
    note: str


@dataclass(frozen=True)
class ReviewLinkResult:
    word: ReviewLinkWord
    already_reviewed: bool = False


def _sign(secret: str, payload: str) -> str:
    digest = hmac.new(secret.encode("utf-8"), payload.encode("utf-8"),
                      hashlib.sha256).digest()
    return base64.urlsafe_b64encode(digest).decode("ascii").rstrip("=")[:_SIG_LEN]


def make_review_token(secret: str, user_id: int, word_id: int, *,
                      ttl_seconds: int = DEFAULT_TTL_SECONDS,
                      now_ts: int | None = None) -> str:
    exp = int(now_ts if now_ts is not None else time.time()) + ttl_seconds
    payload = f"{_TOKEN_VERSION}.{int(user_id)}.{int(word_id)}.{exp}"
    return f"{payload}.{_sign(secret, payload)}"


def verify_review_token(secret: str, token: str, *,
                        now_ts: int | None = None) -> ReviewToken | None:
    try:
        version, user_s, word_s, exp_s, sig = (token or "").rsplit(".", 4)
        if version != _TOKEN_VERSION:
            return None
        payload = f"{version}.{user_s}.{word_s}.{exp_s}"
        if not hmac.compare_digest(sig, _sign(secret, payload)):
            return None
        exp = int(exp_s)
        now = int(now_ts if now_ts is not None else time.time())
        if exp < now:
            return None
        return ReviewToken(int(user_s), int(word_s), exp)
    except (TypeError, ValueError):
        return None


def review_link_url(public_base_url: str | None, token: str) -> str | None:
    base = (public_base_url or "").strip()
    if not base:
        return None
    return urljoin(base.rstrip("/") + "/", f"bark/review/{token}")


def get_review_link_word(conn, secret: str, token: str) -> ReviewLinkWord | None:
    parsed = verify_review_token(secret, token)
    if parsed is None:
        return None
    return _fetch_word(conn, parsed.user_id, parsed.word_id)


def apply_review_link_grade(conn, secret: str, token: str,
                            button: str) -> ReviewLinkResult | None:
    parsed = verify_review_token(secret, token)
    if parsed is None:
        return None
    quality = srs.quality_from_button(button)
    now = utc_now()
    row = _fetch_review_state_for_update(
        conn, parsed.user_id, parsed.word_id,
    )
    if row is None:
        return None
    word = _fetch_word(conn, parsed.user_id, parsed.word_id)
    if word is None:
        return None

    key = _grade_key(token)
    inserted = conn.execute(text(
        """
        INSERT INTO push_log(idempotency_key, user_id, push_type, created_at)
        VALUES (:key, :user_id, 'review_grade', :created_at)
        ON CONFLICT (idempotency_key) DO NOTHING
        RETURNING id
        """
    ), {
        "key": key,
        "user_id": parsed.user_id,
        "created_at": now,
    }).first()
    if inserted is None:
        return ReviewLinkResult(word=word, already_reviewed=True)

    if row["due_date"] > now:
        return ReviewLinkResult(word=word, already_reviewed=True)
    state = SimpleNamespace(
        interval=row["interval"],
        ease=row["ease"],
        reps=row["reps"],
        lapses=row["lapses"],
        due_date=None,
        last_review=None,
    )
    srs.grade(state, quality, now=now)
    conn.execute(text(
        """
        UPDATE words
        SET interval = :interval,
            ease = :ease,
            reps = :reps,
            lapses = :lapses,
            due_date = :due_date,
            last_review = :last_review
        WHERE id = :word_id
        """
    ), {
        "word_id": parsed.word_id,
        "interval": state.interval,
        "ease": state.ease,
        "reps": state.reps,
        "lapses": state.lapses,
        "due_date": state.due_date,
        "last_review": state.last_review,
    })
    conn.execute(text(
        """
        INSERT INTO review_logs(word_id, user_id, ts, grade, source, interval_after)
        VALUES (:word_id, :user_id, :ts, :grade, 'bark', :interval_after)
        """
    ), {
        "word_id": parsed.word_id,
        "user_id": parsed.user_id,
        "ts": state.last_review,
        "grade": quality,
        "interval_after": state.interval,
    })
    return ReviewLinkResult(word=word)


def _fetch_review_state_for_update(conn, user_id: int, word_id: int):
    """Lock the owned word row shared by web and Bark grading."""
    return conn.execute(text(
        """
        SELECT w.interval,
               w.ease,
               w.reps,
               w.lapses,
               w.due_date
        FROM words w
        JOIN word_lists wl ON wl.id = w.list_id
        JOIN users u ON u.id = wl.user_id
        WHERE u.id = :user_id
          AND u.is_active = true
          AND w.id = :word_id
        FOR UPDATE OF w
        """
    ), {
        "user_id": user_id,
        "word_id": word_id,
    }).mappings().first()


def _fetch_word(conn, user_id: int, word_id: int) -> ReviewLinkWord | None:
    row = conn.execute(text(
        """
        SELECT u.id AS user_id,
               w.id AS word_id,
               w.word,
               wl.language_code,
               COALESCE(d.part_of_speech, '') AS part_of_speech,
               COALESCE(d.meaning, '') AS meaning,
               COALESCE(d.example, '') AS example,
               COALESCE(d.note, '') AS note
        FROM users u
        JOIN word_lists wl ON wl.user_id = u.id
        JOIN words w ON w.list_id = wl.id
        LEFT JOIN LATERAL (
            SELECT part_of_speech, meaning, example, note
            FROM definitions
            WHERE word_id = w.id
            ORDER BY id
            LIMIT 1
        ) d ON true
        WHERE u.id = :user_id
          AND u.is_active = true
          AND w.id = :word_id
        """
    ), {"user_id": user_id, "word_id": word_id}).mappings().first()
    if row is None:
        return None
    return ReviewLinkWord(**dict(row))


def _grade_key(token: str) -> str:
    digest = hashlib.sha256(token.encode("utf-8")).hexdigest()[:32]
    return f"review-grade:{digest}"
