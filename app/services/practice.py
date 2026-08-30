import re
import unicodedata
from datetime import datetime, time, timedelta, timezone
from zoneinfo import ZoneInfo

from sqlalchemy.orm import selectinload

from app.extensions import db
from app.models.user import User
from app.models.word import Definition, ReviewLog, Word, WordList
from app.models.practice import PracticeItem, PracticeSession
from app.services import words as words_svc
from app.services.timeutil import utc_now


MAX_SESSION_ITEMS = 5
MAX_REPLAY_COUNT = 100
MAX_ANSWER_DURATION_MS = 3_600_000
VOICE_BLOCK_IDEMPOTENCY_WINDOW = timedelta(days=1)
PRACTICE_LANGUAGES = frozenset({"fr", "ja", "zh"})
VOICE_LOCALES = {"fr": "fr-FR", "ja": "ja-JP"}
_JA_PUNCTUATION = re.compile(r"[。．、，・.,!！?？「」『』()（）\[\]【】…―—]")
_ZH_PUNCTUATION = re.compile(
    r"[。．、，·・.,!！?？：；「」『』\"'“”‘’（）()\[\]【】《》〈〉…―—～〜]"
)
_HAN_CHAR = re.compile(r"[\u3400-\u9fff\uf900-\ufaff]")


class EmptyAnswerError(ValueError):
    pass


class OutOfOrderAnswerError(ValueError):
    pass


class VoiceUnavailableError(ValueError):
    pass


def voice_locale(language_code: str | None) -> str:
    if not language_code:
        return ""
    return VOICE_LOCALES.get(language_code, language_code)


def normalize_practice_text(value: str | None) -> str:
    return unicodedata.normalize("NFC", value or "").casefold()


def normalize_answer(value: str | None, language_code: str = "fr") -> str:
    if language_code == "zh":
        normalized = unicodedata.normalize("NFKC", value or "")
        normalized = _ZH_PUNCTUATION.sub("", normalized)
        return re.sub(r"\s+", "", normalized)
    if language_code == "ja":
        normalized = unicodedata.normalize("NFKC", value or "")
        normalized = _JA_PUNCTUATION.sub("", normalized)
        return re.sub(r"\s+", "", normalized)
    normalized = unicodedata.normalize("NFC", value or "")
    return re.sub(r"\s+", " ", normalized).strip().casefold()


def bound_duration(value: str | int | None) -> int | None:
    try:
        duration = int(value)
    except (TypeError, ValueError):
        return None
    return max(0, min(duration, MAX_ANSWER_DURATION_MS))


def _japanese_unique_span(sentence: str, target: str) -> tuple[int, int] | None:
    if not target:
        return None
    start = sentence.find(target)
    if start < 0 or sentence.find(target, start + 1) >= 0:
        return None
    return start, start + len(target)


def _has_han_neighbor(sentence: str, start: int, end: int) -> bool:
    if start > 0 and _HAN_CHAR.match(sentence[start - 1]):
        return True
    if end < len(sentence) and _HAN_CHAR.match(sentence[end]):
        return True
    return False


def _chinese_unique_span(sentence: str, target: str) -> tuple[int, int] | None:
    span = _japanese_unique_span(sentence, target)
    if span is None:
        return None
    start, end = span
    if len(target) == 1 and _has_han_neighbor(sentence, start, end):
        return None
    return span


def target_occurs_uniquely(
    sentence: str | None,
    target: str | None,
    language_code: str = "fr",
) -> bool:
    if language_code == "zh":
        sentence_nfc = unicodedata.normalize("NFC", sentence or "")
        target_nfc = unicodedata.normalize("NFC", target or "")
        return _chinese_unique_span(sentence_nfc, target_nfc) is not None
    if language_code == "ja":
        sentence_nfc = unicodedata.normalize("NFC", sentence or "")
        target_nfc = unicodedata.normalize("NFC", target or "")
        return _japanese_unique_span(sentence_nfc, target_nfc) is not None
    sentence_n = normalize_practice_text(sentence)
    target_n = normalize_practice_text(target)
    if not sentence_n or not target_n:
        return False
    pattern = rf"(?<!\w){re.escape(target_n)}(?!\w)"
    return len(re.findall(pattern, sentence_n, flags=re.UNICODE)) == 1


def get_eligible_items(user_id: int, language_code: str) -> list[dict]:
    if language_code not in PRACTICE_LANGUAGES:
        return []
    words = (
        Word.query
        .join(WordList)
        .options(selectinload(Word.definitions))
        .filter(WordList.user_id == user_id, WordList.language_code == language_code)
        .order_by(Word.id.asc())
        .all()
    )
    items = []
    for word in words:
        for definition in sorted(word.definitions, key=lambda item: item.id):
            if target_occurs_uniquely(definition.example, word.word, language_code):
                items.append({"word": word, "definition": definition})
                break
    if not items:
        return []

    now = utc_now()
    word_ids = [item["word"].id for item in items]
    recent_reviews = (
        ReviewLog.query
        .filter(
            ReviewLog.user_id == user_id,
            ReviewLog.word_id.in_(word_ids),
            ReviewLog.ts >= now - timedelta(days=30),
        )
        .order_by(ReviewLog.ts.desc(), ReviewLog.id.desc())
        .all()
    )
    grades_by_word = {}
    weak_review_at_by_word = {}
    for review in recent_reviews:
        grades_by_word.setdefault(review.word_id, []).append(review.grade)
        if review.grade in (2, 3):
            weak_review_at_by_word.setdefault(review.word_id, review.ts)

    user = db.session.get(User, user_id)
    tz = ZoneInfo((user.timezone if user else None) or "UTC")
    local_today = now.replace(tzinfo=timezone.utc).astimezone(tz).date()
    practiced_today = {
        word_id for (word_id,) in db.session.query(PracticeItem.word_id)
        .join(PracticeSession, PracticeSession.id == PracticeItem.session_id)
        .filter(
            PracticeSession.user_id == user_id,
            PracticeSession.created_at >= local_today_start_utc(local_today, tz),
        )
        .all()
    }

    def priority(item):
        word = item["word"]
        grades = grades_by_word.get(word.id, [])
        if 2 in grades:
            bucket = 0
        elif 3 in grades:
            bucket = 1
        elif (word.lapses or 0) > 0:
            bucket = 2
        elif word.due_date <= now:
            bucket = 3
        else:
            bucket = 4
        if bucket in (0, 1):
            weak_review_at = weak_review_at_by_word[word.id]
            signal = -weak_review_at.replace(
                tzinfo=timezone.utc,
            ).timestamp()
        elif bucket == 2:
            signal = -(word.lapses or 0)
        elif bucket == 3:
            signal = word.due_date
        else:
            signal = 0
        return (
            bucket,
            0 if word.id not in practiced_today else 1,
            signal,
            word.id,
        )

    eligible_items = [item for item in items if priority(item)[0] < 4]
    return sorted(eligible_items, key=priority)


def get_start_state(user_id: int) -> tuple[str | None, int]:
    language_code = words_svc.get_current_language(user_id)
    if language_code not in PRACTICE_LANGUAGES:
        return language_code, 0
    return language_code, min(
        MAX_SESSION_ITEMS,
        len(get_eligible_items(user_id, language_code)),
    )


def local_today_start_utc(local_today, tz):
    return datetime.combine(
        local_today,
        time.min,
        tzinfo=tz,
    ).astimezone(timezone.utc).replace(tzinfo=None)


def start_session(
    user_id: int,
    *,
    voice_available: bool | None = None,
) -> PracticeSession | None:
    if voice_available is not True:
        raise VoiceUnavailableError
    language_code = words_svc.get_current_language(user_id)
    if language_code not in PRACTICE_LANGUAGES:
        return None
    eligible = get_eligible_items(user_id, language_code)[:MAX_SESSION_ITEMS]
    if not eligible:
        return None
    now = utc_now()
    practice_session = PracticeSession(
        user_id=user_id,
        language_code=language_code,
        status="active",
        current_position=0,
        voice_available=voice_available,
        started_at=now,
        created_at=now,
        updated_at=now,
    )
    db.session.add(practice_session)
    for position, eligible_item in enumerate(eligible):
        word = eligible_item["word"]
        definition = eligible_item["definition"]
        db.session.add(PracticeItem(
            practice_session=practice_session,
            user_id=user_id,
            word_id=word.id,
            definition_id=definition.id,
            position=position,
            sentence=definition.example,
            target=word.word,
            meaning=definition.meaning,
            replay_count=0,
            created_at=now,
            updated_at=now,
        ))
    db.session.commit()
    return practice_session


def record_voice_unavailable(
    user_id: int,
) -> PracticeSession | None:
    language_code = words_svc.get_current_language(user_id)
    if language_code not in PRACTICE_LANGUAGES:
        return None
    now = utc_now()
    existing = (
        PracticeSession.query
        .filter(
            PracticeSession.user_id == user_id,
            PracticeSession.language_code == language_code,
            PracticeSession.status == "blocked",
            PracticeSession.voice_available.is_(False),
            PracticeSession.blocked_at >= now - VOICE_BLOCK_IDEMPOTENCY_WINDOW,
        )
        .order_by(PracticeSession.blocked_at.desc(), PracticeSession.id.desc())
        .first()
    )
    if existing is not None:
        db.session.commit()
        return existing
    blocked = PracticeSession(
        user_id=user_id,
        language_code=language_code,
        status="blocked",
        current_position=0,
        voice_available=False,
        started_at=now,
        blocked_at=now,
        created_at=now,
        updated_at=now,
    )
    db.session.add(blocked)
    db.session.commit()
    return blocked


def get_session(user_id: int, session_id: int) -> PracticeSession | None:
    return (
        PracticeSession.query
        .options(selectinload(PracticeSession.items))
        .filter(
            PracticeSession.id == session_id,
            PracticeSession.user_id == user_id,
        )
        .first()
    )


def submit_answer(
    user_id: int,
    session_id: int,
    item_id: int,
    submitted_answer: str,
    answer_duration_ms: str | int | None = None,
) -> tuple[PracticeSession, PracticeItem] | None:
    practice_session = (
        PracticeSession.query
        .filter(
            PracticeSession.id == session_id,
            PracticeSession.user_id == user_id,
        )
        .with_for_update()
        .first()
    )
    if practice_session is None:
        return None
    item = (
        PracticeItem.query
        .filter(
            PracticeItem.id == item_id,
            PracticeItem.session_id == practice_session.id,
            PracticeItem.user_id == user_id,
        )
        .with_for_update()
        .first()
    )
    if item is None:
        return None
    if item.submitted_at is not None:
        db.session.commit()
        return practice_session, item
    if (
        practice_session.status != "active"
        or item.position != practice_session.current_position
    ):
        raise OutOfOrderAnswerError
    now = utc_now()
    language_code = practice_session.language_code
    normalized = normalize_answer(submitted_answer, language_code)
    if not normalized:
        raise EmptyAnswerError
    item.submitted_answer = submitted_answer
    item.normalized_answer = normalized
    item.is_correct = normalized == normalize_answer(item.target, language_code)
    item.submitted_at = now
    item.answer_duration_ms = bound_duration(answer_duration_ms)
    item.updated_at = now
    db.session.commit()
    return practice_session, item


def continue_session(user_id: int, session_id: int) -> PracticeSession | None:
    practice_session = (
        PracticeSession.query
        .filter(
            PracticeSession.id == session_id,
            PracticeSession.user_id == user_id,
            PracticeSession.status == "active",
        )
        .with_for_update()
        .first()
    )
    if practice_session is None:
        return None
    items = list(practice_session.items)
    if not items or practice_session.current_position >= len(items):
        return None
    current_item = items[practice_session.current_position]
    if current_item.submitted_at is None:
        return None
    now = utc_now()
    if practice_session.current_position == len(items) - 1:
        practice_session.status = "completed"
        practice_session.completed_at = now
    else:
        practice_session.current_position += 1
    practice_session.updated_at = now
    db.session.commit()
    return practice_session


def record_replay(user_id: int, session_id: int, item_id: int) -> bool:
    item = (
        PracticeItem.query
        .join(PracticeSession, PracticeSession.id == PracticeItem.session_id)
        .filter(
            PracticeItem.id == item_id,
            PracticeItem.session_id == session_id,
            PracticeItem.user_id == user_id,
            PracticeSession.user_id == user_id,
        )
        .with_for_update()
        .first()
    )
    if item is None:
        return False
    item.replay_count = min((item.replay_count or 0) + 1, MAX_REPLAY_COUNT)
    item.updated_at = utc_now()
    db.session.commit()
    return True


def abandon_session(user_id: int, session_id: int) -> bool:
    practice_session = (
        PracticeSession.query
        .filter(
            PracticeSession.id == session_id,
            PracticeSession.user_id == user_id,
            PracticeSession.status == "active",
        )
        .with_for_update()
        .first()
    )
    if practice_session is None:
        return False
    now = utc_now()
    practice_session.status = "abandoned"
    practice_session.abandoned_at = now
    practice_session.updated_at = now
    db.session.commit()
    return True


def prompt_parts(
    sentence: str, target: str, language_code: str = "fr",
) -> tuple[str, str]:
    sentence = unicodedata.normalize("NFC", sentence)
    target = unicodedata.normalize("NFC", target)
    if language_code == "zh":
        span = _chinese_unique_span(sentence, target)
        if span is None:
            return sentence, ""
        start, end = span
        return sentence[:start], sentence[end:]
    if language_code == "ja":
        span = _japanese_unique_span(sentence, target)
        if span is None:
            return sentence, ""
        start, end = span
        return sentence[:start], sentence[end:]
    pattern = rf"(?<!\w){re.escape(target)}(?!\w)"
    match = re.search(pattern, sentence, flags=re.IGNORECASE | re.UNICODE)
    if match is None:
        return sentence, ""
    return sentence[:match.start()], sentence[match.end():]
