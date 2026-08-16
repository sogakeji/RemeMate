"""词库 / 词 的业务逻辑。

所有函数显式接收 user_id（第二层防御）；RLS 是数据库兜底（第三层）。
词、释义无 user_id 列，必须 JOIN word_lists 过滤 user_id。

「词表」对用户是隐式派生层：用户只接触「语言」，系统按 (user_id, language_code)
唯一派生词表（不存在则建）。底表以唯一约束兜底，本模块用
get_or_create_language_list 集中创建，避免多入口分叉。
见 docs/arch/ui-rescope-plan.md §1.3 + HANDOFF 踩坑 #10。
"""
import ipaddress
import socket
from dataclasses import dataclass
from datetime import datetime, timedelta
from urllib.parse import urlsplit
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from sqlalchemy import and_, func
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import selectinload

from app.extensions import db
from app.models.user import User, UserSettings, UserQuota
from app.models.word import WordList, Word, Definition, ReviewLog
from app.models.intake import IntakeSource, WordCandidate
from app.models.reading import ReadingDocument
from app.services import srs
from app.services.languages import AI_LANGUAGE_NAMES, KNOWN_LANGUAGE_NAMES
from app.services.timeutil import next_midnight_utc, today_local_start_utc, utc_now


# language_code → 隐式词表的内部 name（用户不可见；不展示、不让改名）。
# New user-facing vocabulary and AI choices.  Keep the private known map
# below for reading legacy de/ru rows without exposing them as new choices.
_LANGUAGE_NAMES = dict(AI_LANGUAGE_NAMES)
_KNOWN_LANGUAGE_NAMES = dict(KNOWN_LANGUAGE_NAMES)
_FEEDBACK_LANGUAGE_NAMES = dict(AI_LANGUAGE_NAMES)

_PUSH_NOTIFY_FIELDS = {
    "notify_review_reminder",
    "notify_daily_summary",
    "notify_intake_done",
}

_TIMEZONE_CHOICES = {
    "Asia/Shanghai": "中国时间",
    "Europe/Paris": "法国时间",
    "UTC": "UTC",
    "Asia/Tokyo": "日本时间",
    "America/New_York": "美国东部时间",
    "America/Los_Angeles": "美国西部时间",
}


@dataclass(frozen=True)
class ReviewGradeResult:
    word: Word
    applied: bool


def review_attempt_version(due_at: datetime) -> str:
    """Canonical wire value for one due-state of a review card."""
    return due_at.isoformat(timespec="microseconds")


def _language_name(language_code: str) -> str:
    return _KNOWN_LANGUAGE_NAMES.get(language_code, language_code)


def _feedback_language_name(language_code: str | None) -> str:
    return _FEEDBACK_LANGUAGE_NAMES.get(language_code or "zh", "中文")


# ---- 词表（隐式：按语言派生） ----

def create_word_list(user_id: int, name: str, language_code: str) -> WordList:
    wl = WordList(user_id=user_id, name=name, language_code=language_code)
    db.session.add(wl)
    db.session.commit()
    return wl


def get_or_create_language_list(user_id: int, language_code: str) -> WordList:
    """隐式词表入口：返回该用户该语言唯一的词表，不存在则建。

    不变量：每 (user_id, language_code) 零或一张词表。复用现有那张不另建，
    避免导入/设语言反复建表。name 存内部语言名（如「法语」），用户不可见。
    """
    if language_code not in _KNOWN_LANGUAGE_NAMES:
        raise ValueError(f"未知语言 code：{language_code!r}")
    wl = (WordList.query
          .filter_by(user_id=user_id, language_code=language_code)
          .first())
    if wl is None:
        wl = WordList(user_id=user_id, name=_language_name(language_code),
                      language_code=language_code)
        db.session.add(wl)
        try:
            db.session.commit()
        except IntegrityError:
            db.session.rollback()
            wl = (WordList.query
                  .filter_by(user_id=user_id, language_code=language_code)
                  .first())
            if wl is None:
                raise
    return wl


# ---- 当前语言状态（首页切换器/设置页/词列表页共用） ----

def _parse_learning(raw: str | None) -> list[str]:
    """users.learning_languages 逗号串 → code 列表（去重保序、过滤非法）。"""
    if not raw:
        return []
    return [c for c in (s.strip() for s in raw.split(",")) if c in _KNOWN_LANGUAGE_NAMES]


def _serialize_learning(codes: list[str]) -> str | None:
    return ",".join(codes) if codes else None


def get_learning_languages(user_id: int) -> list[str]:
    """用户在学语言集合（code 列表，保序）；老用户未设为空。"""
    u = db.session.get(User, user_id)
    return _parse_learning((u or User()).learning_languages)


def set_learning_languages(user_id: int, codes: list[str]) -> list[str]:
    """设置页多选保存：写 learning_languages，并保证 current_language 收敛到集合内。

    不变量收敛：
    - 过滤非法 code、去重保序。
    - 集合变空 → current_language 清空（用户没在学任何语言，首页引导去设置）。
    - 当前 current_language 不在新集合内 → 自动收成集合首个（若无则清空）。
    - 同时 ensure 每个新进集合的语言有隐式词表（get_or_create_language_list）。
    """
    seen, cleaned = set(), []
    for c in codes:
        if c in _LANGUAGE_NAMES and c not in seen:
            seen.add(c)
            cleaned.append(c)
    u = db.session.get(User, user_id)
    if u is None:
        raise ValueError(f"用户不存在：{user_id}")
    # 给每个在学语言建（或复用）隐式词表，方便随时切过去刷词/加词。
    for c in cleaned:
        get_or_create_language_list(user_id, c)
    u.learning_languages = _serialize_learning(cleaned)
    if not cleaned:
        u.current_language = None
    elif u.current_language not in cleaned:
        u.current_language = cleaned[0]
    db.session.commit()
    return cleaned


def get_current_language(user_id: int) -> str | None:
    """用户当前正在学的语言 code；未设过为 None（首页/词列表应提示去设置选语言）。"""
    u = db.session.get(User, user_id)
    return (u or User()).current_language


def set_current_language(user_id: int, language_code: str) -> str:
    """设当前语言（首页切换器用），并保证该语言已在学集合内 + 隐式词表存在。

    不变量：current_language 必须是 learning_languages 子集。该语言若不在学集合，
    一并加入（用户在首页切语言即默认「在学」），保证首切不卡。
    """
    if language_code not in _KNOWN_LANGUAGE_NAMES:
        raise ValueError(f"未知语言 code：{language_code!r}")
    u = db.session.get(User, user_id)
    if u is None:
        raise ValueError(f"用户不存在：{user_id}")
    learning = _parse_learning(u.learning_languages)
    if language_code not in learning:
        learning.append(language_code)
        u.learning_languages = _serialize_learning(learning)
    get_or_create_language_list(user_id, language_code)   # 隐式词表存在
    u.current_language = language_code
    db.session.commit()
    return language_code


def get_feedback_language(user_id: int) -> str:
    settings = db.session.get(UserSettings, user_id)
    code = (settings.feedback_language if settings else None) or "zh"
    return code if code in _FEEDBACK_LANGUAGE_NAMES else "zh"


def set_feedback_language(user_id: int, language_code: str) -> str:
    if language_code not in _FEEDBACK_LANGUAGE_NAMES:
        raise ValueError(f"未知反馈语言 code：{language_code!r}")
    settings = db.session.get(UserSettings, user_id)
    if settings is None:
        settings = UserSettings(user_id=user_id)
        db.session.add(settings)
    settings.feedback_language = language_code
    db.session.commit()
    return language_code


def get_timezone(user_id: int) -> str:
    user = db.session.get(User, user_id)
    tz = (user.timezone if user else None) or "Asia/Shanghai"
    return tz if tz in _TIMEZONE_CHOICES else "Asia/Shanghai"


def set_timezone(user_id: int, timezone_name: str) -> str:
    if timezone_name not in _TIMEZONE_CHOICES:
        raise ValueError(f"未知时区：{timezone_name!r}")
    try:
        ZoneInfo(timezone_name)
    except ZoneInfoNotFoundError as exc:
        raise ValueError(f"未知时区：{timezone_name!r}") from exc
    user = db.session.get(User, user_id)
    if user is None:
        raise ValueError(f"用户不存在：{user_id}")
    user.timezone = timezone_name
    quota = db.session.get(UserQuota, user_id)
    if quota is not None:
        quota.quota_reset_at = next_midnight_utc(timezone_name)
    db.session.commit()
    return timezone_name


def _unsafe_push_ip(ip: str) -> bool:
    parsed = ipaddress.ip_address(ip)
    return (
        parsed.is_private
        or parsed.is_loopback
        or parsed.is_link_local
        or parsed.is_reserved
        or parsed.is_multicast
        or parsed.is_unspecified
    )


def _validate_push_url(url: str | None) -> str | None:
    """保存推送 URL 前做第一层 SSRF 防护；发送前仍需二次校验。"""
    normalized = (url or "").strip()
    if not normalized:
        return None
    if len(normalized) > 500:
        raise ValueError("Bark 地址过长")
    try:
        parts = urlsplit(normalized)
    except ValueError as exc:
        raise ValueError("Bark 地址格式不正确") from exc
    if parts.scheme != "https" or not parts.hostname:
        raise ValueError("Bark 地址必须是 https 公网地址")
    if parts.username or parts.password:
        raise ValueError("Bark 地址不能包含用户名或密码")

    host = parts.hostname
    if host.lower() == "localhost":
        raise ValueError("Bark 地址不能指向本机或内网")
    try:
        literal_ip = ipaddress.ip_address(host)
    except ValueError:
        literal_ip = None
    if literal_ip is not None and _unsafe_push_ip(str(literal_ip)):
        raise ValueError("Bark 地址不能指向本机或内网")

    try:
        infos = socket.getaddrinfo(host, parts.port or 443, proto=socket.IPPROTO_TCP)
    except socket.gaierror as exc:
        raise ValueError("Bark 地址无法解析") from exc
    for *_, sockaddr in infos:
        if _unsafe_push_ip(sockaddr[0]):
            raise ValueError("Bark 地址不能指向本机或内网")
    return normalized


def get_notification_settings(user_id: int) -> dict:
    settings = db.session.get(UserSettings, user_id)
    if settings is None:
        return {
            "bark_url": "",
            "notify_review_reminder": True,
            "notify_daily_summary": True,
            "notify_intake_done": True,
        }
    return {
        "bark_url": settings.bark_url or "",
        "notify_review_reminder": bool(settings.notify_review_reminder),
        "notify_daily_summary": bool(settings.notify_daily_summary),
        "notify_intake_done": bool(settings.notify_intake_done),
    }


def set_notification_settings(user_id: int, bark_url: str | None, **flags) -> dict:
    settings = db.session.get(UserSettings, user_id)
    if settings is None:
        settings = UserSettings(user_id=user_id)
        db.session.add(settings)
    settings.bark_url = _validate_push_url(bark_url)
    for field in _PUSH_NOTIFY_FIELDS:
        if field in flags:
            setattr(settings, field, bool(flags[field]))
    db.session.commit()
    return get_notification_settings(user_id)


def send_bark_test_notification(user_id: int) -> None:
    from app.services.notifications import NotificationError, send_bark_payload

    settings = db.session.get(UserSettings, user_id)
    payload = {
        "title": "记搭 RemeMate",
        "body": "测试推送发送成功。",
        "group": "RemeMate",
    }
    try:
        send_bark_payload(settings.bark_url if settings else None, payload)
    except NotificationError as exc:
        raise ValueError(str(exc).replace("Bark 推送", "Bark 测试推送")) from exc


def get_current_language_list(user_id: int) -> WordList | None:
    """当前语言对应的隐式词表；未设语言或尚无词表都返回 None。"""
    lang = get_current_language(user_id)
    if lang is None:
        return None
    return (WordList.query
            .filter_by(user_id=user_id, language_code=lang).first())


def get_words_for_current_language(user_id: int, *, sort: str = "due",
                                   marked_only: bool = False) -> tuple[str | None, list[Word]]:
    """Return current-language words with optional marked-only filtering and ordering."""
    wl = get_current_language_list(user_id)
    if wl is None:
        return (get_current_language(user_id), [])
    q = Word.query.filter_by(list_id=wl.id).options(selectinload(Word.definitions))
    if marked_only:
        q = q.filter(Word.marked.is_(True))
    if sort == "recent":
        q = q.order_by(Word.id.desc())
    elif sort == "lapses":
        q = q.order_by(Word.lapses.desc(), Word.due_date.asc(), Word.id.desc())
    else:
        q = q.order_by(Word.due_date.asc(), Word.id.desc())
    return (wl.language_code, q.all())

def get_word_lists(user_id: int, *, language_code: str | None = None) -> list[tuple[WordList, int]]:
    """返回 [(word_list, word_count), ...]，一次聚合查出词数，避免模板 N+1。

    language_code 给定时按该语言过滤（隐式词表页：只展示当前语言的词库）。
    None=所有语言（兼容跨语言概览）。
    """
    q = (db.session.query(WordList, func.count(Word.id))
         .outerjoin(Word, Word.list_id == WordList.id)
         .filter(WordList.user_id == user_id))
    if language_code is not None:
        q = q.filter(WordList.language_code == language_code)
    return (q.group_by(WordList.id)
            .order_by(WordList.created_at.desc())
            .all())


def get_word_list(user_id: int, list_id: int, *, eager: bool = False) -> WordList | None:
    """取词表。eager=True 时预加载 words 及其 definitions，消除详情页逐词懒加载的 N+1
    （review 2026-06-23 M6）。默认不预加载，供 delete/add_word 等仅需存在性校验的场景。"""
    q = WordList.query.filter_by(id=list_id, user_id=user_id)
    if eager:
        q = q.options(selectinload(WordList.words).selectinload(Word.definitions))
    return q.first()


def get_reading_sources_for_words(user_id: int, word_ids: list[int]) -> dict[int, dict]:
    """一次取回词条的阅读来源，供词库详情做轻量来源展示。"""
    unique_ids = list(dict.fromkeys(word_id for word_id in word_ids if word_id))
    if not unique_ids:
        return {}

    rows = (
        db.session.query(
            WordCandidate.word_id.label("word_id"),
            WordCandidate.source_example.label("source_example"),
            IntakeSource.original_name.label("original_name"),
            ReadingDocument.title.label("document_title"),
        )
        .join(
            IntakeSource,
            and_(
                IntakeSource.id == WordCandidate.source_id,
                IntakeSource.user_id == user_id,
            ),
        )
        .join(Word, Word.id == WordCandidate.word_id)
        .join(
            WordList,
            and_(WordList.id == Word.list_id, WordList.user_id == user_id),
        )
        .outerjoin(
            ReadingDocument,
            and_(
                ReadingDocument.intake_source_id == IntakeSource.id,
                ReadingDocument.user_id == user_id,
            ),
        )
        .filter(
            WordCandidate.user_id == user_id,
            WordCandidate.word_id.in_(unique_ids),
            IntakeSource.source_type == "reading_pdf",
        )
        .order_by(WordCandidate.created_at.desc(), WordCandidate.id.desc())
        .all()
    )

    result = {}
    for row in rows:
        result.setdefault(row.word_id, {
            "title": row.document_title or row.original_name,
            "original_name": row.original_name,
            "source_example": row.source_example,
        })
    return result


def delete_word_list(user_id: int, list_id: int) -> bool:
    wl = get_word_list(user_id, list_id)
    if wl is None:
        return False
    db.session.delete(wl)  # cascade 删 words/definitions
    db.session.commit()
    return True


# ---- 词 ----

class DuplicateWordError(ValueError):
    """The normalized word identity already exists in this language list."""


def normalize_word_identity(value: str | None) -> str:
    """Identity used for one word inside one language list."""
    return (value or "").strip().lower()


def add_word(user_id, list_id, word, *, meaning=None,
             part_of_speech=None, example=None, note=None,
             definitions=None) -> Word | None:
    """加词。两种释义方式：

    - 单释义（旧调用）：传 meaning/part_of_speech/example/note，建一条 Definition。
    - 多释义（加词中心 JSON）：传 ``definitions``，元素形如
      {"part_of_speech","meaning","example","note"}，按序建多条 Definition。
      多释义时忽略单释义参数。空释义（全 None）不建 Definition。
    """
    wl = get_word_list(user_id, list_id)
    if wl is None:
        return None
    display_word = (word or "").strip()
    identity = normalize_word_identity(display_word)
    existing = (Word.query
                .filter(
                    Word.list_id == wl.id,
                    func.lower(func.btrim(Word.word)) == identity,
                )
                .first())
    if existing is not None:
        return existing
    w = Word(list_id=wl.id, word=display_word, due_date=utc_now(),
             interval=1, ease=2.5, reps=0, lapses=0)
    db.session.add(w)
    try:
        db.session.flush()
        if definitions:
            for d in definitions:
                db.session.add(Definition(
                    word_id=w.id,
                    meaning=(d or {}).get("meaning") or None,
                    part_of_speech=(d or {}).get("part_of_speech") or None,
                    example=(d or {}).get("example") or None,
                    note=(d or {}).get("note") or None,
                ))
        elif any([meaning, part_of_speech, example, note]):
            db.session.add(Definition(word_id=w.id, meaning=meaning,
                                      part_of_speech=part_of_speech,
                                      example=example, note=note))
        db.session.commit()
    except IntegrityError:
        db.session.rollback()
        existing = (Word.query
                    .filter(
                        Word.list_id == wl.id,
                        func.lower(func.btrim(Word.word)) == identity,
                    )
                    .first())
        if existing is None:
            raise
        return existing
    return w


def update_word(user_id: int, word_id: int, word: str, definitions: list[dict]) -> Word | None:
    """更新词条本体与多条释义；不属于该用户返回 None。"""
    w = get_word(user_id, word_id)
    if w is None:
        return None
    word = (word or "").strip()
    if not word:
        raise ValueError("词不能为空")
    identity = normalize_word_identity(word)
    conflict = (Word.query
                .filter(
                    Word.list_id == w.list_id,
                    Word.id != w.id,
                    func.lower(func.btrim(Word.word)) == identity,
                ).first())
    if conflict is not None:
        raise DuplicateWordError
    w.word = word
    Definition.query.filter_by(word_id=w.id).delete()
    for d in definitions:
        db.session.add(Definition(
            word_id=w.id,
            part_of_speech=(d or {}).get("part_of_speech") or None,
            meaning=(d or {}).get("meaning") or None,
            example=(d or {}).get("example") or None,
            note=(d or {}).get("note") or None,
        ))
    try:
        db.session.commit()
    except IntegrityError:
        db.session.rollback()
        conflict = (Word.query
                    .filter(
                        Word.list_id == w.list_id,
                        Word.id != w.id,
                        func.lower(func.btrim(Word.word)) == identity,
                    ).first())
        if conflict is not None:
            raise DuplicateWordError
        raise
    return w


def delete_word(user_id: int, word_id: int) -> bool:
    """Delete one word owned by user_id.

    ReviewLog has no model relationship/ondelete cascade in this branch, so
    delete logs explicitly before deleting the word row.
    """
    w = get_word(user_id, word_id)
    if w is None:
        return False
    ReviewLog.query.filter_by(word_id=w.id).delete()
    db.session.delete(w)
    db.session.commit()
    return True


def toggle_marked(user_id: int, word_id: int) -> Word | None:
    """切换星标；不属于该用户返回 None。"""
    w = get_word(user_id, word_id)
    if w is None:
        return None
    w.marked = not w.marked
    db.session.commit()
    return w


def get_word(user_id: int, word_id: int) -> Word | None:
    return (Word.query
            .join(WordList)
            .options(selectinload(Word.definitions), selectinload(Word.word_list))
            .filter(Word.id == word_id, WordList.user_id == user_id)
            .first())


def parse_review_attempt_version(raw: str | None) -> datetime:
    """Parse the exact naive-UTC due timestamp rendered with a review card."""
    if not isinstance(raw, str) or not raw:
        raise ValueError("missing review attempt version")
    try:
        parsed = datetime.fromisoformat(raw)
    except ValueError as exc:
        raise ValueError("invalid review attempt version") from exc
    if parsed.tzinfo is not None or review_attempt_version(parsed) != raw:
        raise ValueError("non-canonical review attempt version")
    return parsed


def review_word(user_id: int, word_id: int, button: str,
                expected_due_at: datetime, *,
                now: datetime | None = None) -> ReviewGradeResult | None:
    """Atomically grade one current due-state; stale attempts are no-ops."""
    quality = srs.quality_from_button(button)
    now = now or utc_now()
    w = (Word.query
         .join(WordList)
         .filter(Word.id == word_id, WordList.user_id == user_id)
         .with_for_update(of=Word)
         .first())
    if w is None:
        return None

    if w.due_date != expected_due_at or w.due_date > now:
        db.session.commit()
        return ReviewGradeResult(word=w, applied=False)

    srs.grade(w, quality, now=now)
    db.session.add(ReviewLog(
        word_id=w.id, user_id=user_id, ts=w.last_review,
        grade=quality, source="review", interval_after=w.interval,
    ))
    db.session.commit()
    return ReviewGradeResult(word=w, applied=True)


def get_due_words(user_id: int, limit: int | None = None, *,
                  language_code: str | None = None) -> list[Word]:
    """取到期词。language_code 给定时只查该语言（首页/复习按当前语言刷）。

    language_code=None 且当前语言未设时，调用方应先提示去设置选语言；
    None=跨所有语言（兼容旧调用，但隐式化后首页应传当前语言）。
    """
    q = (Word.query
         .join(WordList)
         .filter(WordList.user_id == user_id,
                 Word.due_date <= utc_now()))
    if language_code is not None:
        q = q.filter(WordList.language_code == language_code)
    q = q.order_by(Word.due_date)
    if limit:
        q = q.limit(limit)
    return q.all()


# ---- 统计 ----

def get_stats(user_id: int, *, language_code: str | None = None) -> dict:
    # 「今日已复习」按用户本地午夜切（review 2026-06-23 M2）。
    # 注意 `due_count` 是「所有到期（due_date <= now）」语义，含逾期未做的词；
    # 模板文案以「待复习」表达，不要称作「今日到期」（review 2026-06-23 L1）。
    tz = (db.session.get(User, user_id) or User()).timezone or "Asia/Shanghai"
    now = utc_now()
    today_start = today_local_start_utc(tz)
    # 注意：lang_filter 是 SA 二元表达式，其布尔值不可靠（语言 expression 的 __bool__ 在
    # 不同 SA 版本会报错或恒为 False）。用字符串 language_code 的 truthiness 判断是否过滤。
    lang_q = [WordList.language_code == language_code] if language_code else []
    total = (Word.query.join(WordList)
             .filter(WordList.user_id == user_id, *lang_q).count())
    due = (Word.query.join(WordList)
           .filter(WordList.user_id == user_id, *lang_q, Word.due_date <= now).count())
    # reviewed_today / heatmap 跨语言合计（复习历史不按语言切，更稳）
    reviewed_today = (ReviewLog.query
                      .filter(ReviewLog.user_id == user_id,
                              ReviewLog.ts >= today_start).count())
    lists = WordList.query.filter_by(user_id=user_id)
    if language_code:
        lists = lists.filter_by(language_code=language_code)
    lists = lists.count()
    return {
        "total_words": total,
        "due_count": due,
        "reviewed_today": reviewed_today,
        "list_count": lists,
        "top_lapses": _top_lapses(user_id, language_code=language_code),
        "heatmap": _heatmap(user_id, tz, weeks=12),
    }


def _top_lapses(user_id: int, limit: int = 20, *,
                language_code: str | None = None) -> list[Word]:
    """易忘词 Top：按忘记次数（lapses）降序的词（属该用户）。写句日记/广场强相关。"""
    q = (Word.query.join(WordList)
         .filter(WordList.user_id == user_id, Word.lapses > 0))
    if language_code is not None:
        q = q.filter(WordList.language_code == language_code)
    return q.order_by(Word.lapses.desc()).limit(limit).all()


def _heatmap(user_id: int, tz_name: str, *, weeks: int = 12) -> dict:
    """学习热力图：近 weeks 周每天复习次数（按 ReviewLog.ts，用户本地日聚合）。

    返回 {"weeks": [[count,...], ...], "total": N}。
    weeks 列：列 0 = 最早那周，每列 7 天（周日起，对齐 demo）。
    未来日期格用 None（末列尾部留空），不计入 total。
    用文本 SQL 走 `AT TIME ZONE` 把 ts 映射到用户本地日，避免 ORM 拼时区表达式。
    """
    from zoneinfo import ZoneInfo
    tz = tz_name or "Asia/Shanghai"
    since = utc_now() - timedelta(weeks=weeks)
    from sqlalchemy import text as _text
    rows = db.session.execute(_text(
        "SELECT to_char((ts AT TIME ZONE 'UTC') AT TIME ZONE :tz, 'YYYY-MM-DD') d,"
        " count(*) c FROM review_logs"
        " WHERE user_id=:u AND ts>=:since GROUP BY d"),
        {"tz": tz, "u": user_id, "since": since},
    ).all()
    counts = {d: int(c) for (d, c) in rows}

    # 网格对齐 demo：周日为列首。今日所属周的周日为最右列起点。
    # today_local 也从 DB now() 取，与上面按 ts 聚合用的同一时钟，
    # 避免「DB 把今天的复习分到明天的格子、Python 判今天为未来格」的不一致（时钟/调用间隔）。
    tzinfo = ZoneInfo(tz)
    today_local_str = db.session.execute(_text(
        "SELECT to_char((now() AT TIME ZONE 'UTC') AT TIME ZONE :tz, 'YYYY-MM-DD')"
    ), {"tz": tz}).scalar()
    from datetime import date as _date
    today_local = _date.fromisoformat(today_local_str)
    # weekday(): 周一=0..周日=6；本周末日 = today - ((weekday()+1)%7) 天
    end_sunday = today_local - timedelta(days=(today_local.weekday() + 1) % 7)
    start = end_sunday - timedelta(days=(weeks - 1) * 7)
    grid = []
    total = 0
    for w in range(weeks):
        col = []
        for d in range(7):
            day = start + timedelta(days=w * 7 + d)
            if day > today_local:
                col.append(None)
            else:
                n = counts.get(day.isoformat(), 0)
                col.append(n)
                total += n
        grid.append(col)
    return {"weeks": grid, "total": total}
