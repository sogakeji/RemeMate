"""词库 / 词 的业务逻辑。

所有函数显式接收 user_id（第二层防御）；RLS 是数据库兜底（第三层）。
词、释义无 user_id 列，必须 JOIN word_lists 过滤 user_id。

「词表」对用户是隐式派生层：用户只接触「语言」，系统按 (user_id, language_code)
唯一派生词表（不存在则建）。底表 word_lists schema 不变，不变量靠本模块
get_or_create_language_list 的 upsert 保证，不靠 schema 唯一索引。
见 docs/arch/ui-rescope-plan.md §1.3 + HANDOFF 踩坑 #10。
"""
from datetime import datetime, timedelta

from sqlalchemy import func
from sqlalchemy.orm import selectinload

from app.extensions import db
from app.models.user import User
from app.models.word import WordList, Word, Definition, ReviewLog
from app.services import srs
from app.services.timeutil import today_local_start_utc


# language_code → 隐式词表的内部 name（用户不可见；不展示、不让改名）。
_LANGUAGE_NAMES = {
    "fr": "法语", "en": "英语", "ja": "日语",
    "de": "德语", "es": "西语", "ru": "俄语",
}


def _language_name(language_code: str) -> str:
    return _LANGUAGE_NAMES.get(language_code, language_code)


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
    wl = (WordList.query
          .filter_by(user_id=user_id, language_code=language_code)
          .first())
    if wl is None:
        wl = WordList(user_id=user_id, name=_language_name(language_code),
                      language_code=language_code)
        db.session.add(wl)
        db.session.commit()
    return wl


# ---- 当前语言状态（首页切换器/设置页/词列表页共用） ----

def _parse_learning(raw: str | None) -> list[str]:
    """users.learning_languages 逗号串 → code 列表（去重保序、过滤非法）。"""
    if not raw:
        return []
    return [c for c in (s.strip() for s in raw.split(",")) if c in _LANGUAGE_NAMES]


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
    if language_code not in _LANGUAGE_NAMES:
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


def get_current_language_list(user_id: int) -> WordList | None:
    """当前语言对应的隐式词表；未设语言或尚无词表都返回 None。"""
    lang = get_current_language(user_id)
    if lang is None:
        return None
    return (WordList.query
            .filter_by(user_id=user_id, language_code=lang).first())


def get_words_for_current_language(user_id: int) -> tuple[str | None, list[Word]]:
    """词列表页用：返回 (当前语言 code 或 None, 该语言隐式词表的词列表)。

    预加载 definitions 消除模板逐词懒加载。未设语言 → (None, [])，调用方提示去设置。
    """
    wl = get_current_language_list(user_id)
    if wl is None:
        return (get_current_language(user_id), [])
    ws = (Word.query.filter_by(list_id=wl.id)
          .options(selectinload(Word.definitions))
          .order_by(Word.due_date).all())
    return (wl.language_code, ws)


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


def delete_word_list(user_id: int, list_id: int) -> bool:
    wl = get_word_list(user_id, list_id)
    if wl is None:
        return False
    db.session.delete(wl)  # cascade 删 words/definitions
    db.session.commit()
    return True


# ---- 词 ----

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
    w = Word(list_id=wl.id, word=word, due_date=datetime.utcnow(),
             interval=1, ease=2.5, reps=0, lapses=0)
    db.session.add(w)
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
    return w


def get_word(user_id: int, word_id: int) -> Word | None:
    return (Word.query
            .join(WordList)
            .filter(Word.id == word_id, WordList.user_id == user_id)
            .first())


def review_word(user_id: int, word_id: int, button: str) -> Word | None:
    """复习评分：映射按钮→质量分，更新 SM-2，写 ReviewLog。返回 word（不属于该用户则 None）。"""
    w = get_word(user_id, word_id)
    if w is None:
        return None
    quality = srs.quality_from_button(button)
    srs.grade(w, quality)
    db.session.add(ReviewLog(
        word_id=w.id, user_id=user_id, ts=w.last_review,
        grade=quality, source="review", interval_after=w.interval,
    ))
    db.session.commit()
    return w


def get_due_words(user_id: int, limit: int | None = None, *,
                  language_code: str | None = None) -> list[Word]:
    """取到期词。language_code 给定时只查该语言（首页/复习按当前语言刷）。

    language_code=None 且当前语言未设时，调用方应先提示去设置选语言；
    None=跨所有语言（兼容旧调用，但隐式化后首页应传当前语言）。
    """
    q = (Word.query
         .join(WordList)
         .filter(WordList.user_id == user_id,
                 Word.due_date <= datetime.utcnow()))
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
    now = datetime.utcnow()
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
    since = datetime.utcnow() - timedelta(weeks=weeks)
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
