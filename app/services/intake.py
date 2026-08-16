"""输入管道：CSV / 文本抽词 / 快速加词 / 阅读材料 → 候选词。

核心原则（用户决策 2026-06-23）：
- 长度/数量在解析前就拦，绝不「先烧 token 再发现超限」。
- 导入额度按候选词数/天（与造句分开，见 quota.py）。
- 抽词/归一化（烧 LLM）时计入导入额度；commit 入库不计。
- CSV/extract 走 SSE 流式分批，避免 nginx 超时。
"""
import csv
import io
import json

from sqlalchemy.exc import IntegrityError

from app.extensions import db
from app.models.word import WordList, Word, Definition
from app.models.intake import IntakeSource, SourceSegment, WordCandidate
from app.services import llm
from app.services import quota as quota_svc
from app.services import words as words_svc
from app.services.timeutil import utc_now

# 前置硬上限（可配；人工测试后调）
INTAKE_MAX_EXTRACT_CHARS = 8000
INTAKE_MAX_EXTRACT_WORDS = 50
INTAKE_MAX_CSV_ROWS = 500
INTAKE_MAX_CSV_BYTES = 256 * 1024
INTAKE_BATCH_SIZE = 20
QUICK_ADD_MAX_CHARS = 140
CANDIDATE_CONTEXT_MAX_CHARS = 300
VALID_CONTEXT_PROVENANCE = frozenset({"source_quote", "user_edited"})

_CSV_HEADER_ALIASES = {
    "word": ("word", "term", "单词", "词", "词语"),
    "part_of_speech": ("part_of_speech", "part of speech", "pos", "词性"),
    "meaning": ("meaning", "definition", "translation", "释义", "解释", "定义"),
    "example": ("example", "sentence", "例句", "句子"),
    "note": ("note", "notes", "笔记", "备注"),
    "marked": ("marked", "is_marked", "starred", "favorite", "是否标注", "是否收藏"),
}
_CSV_HEADER_ALIAS_TO_CANONICAL = {
    alias.strip().lower().replace(" ", "_").replace("-", "_"): canonical
    for canonical, aliases in _CSV_HEADER_ALIASES.items()
    for alias in aliases
}
_CSV_REQUIRED_HINT = "CSV 表头必须包含词和释义列；支持 word/单词 和 meaning/definition/释义"


class DocumentTooLong(Exception):
    pass


class CsvTooLarge(Exception):
    pass


class CsvFormatError(Exception):
    pass


def _language_word_list(user_id, language_code) -> WordList | None:
    if language_code not in words_svc._LANGUAGE_NAMES:
        return None
    return words_svc.get_or_create_language_list(user_id, language_code)


def _canonical_csv_header(header):
    normalized = (header or "").strip().lower().replace(" ", "_").replace("-", "_")
    return _CSV_HEADER_ALIAS_TO_CANONICAL.get(normalized, normalized)


def _canonicalize_csv_row(row):
    norm = {}
    for key, value in row.items():
        if key is None:
            continue
        canonical = _canonical_csv_header(key)
        if not canonical:
            continue
        val = (value or "").strip()
        if canonical not in norm or (val and not norm[canonical]):
            norm[canonical] = val
    return norm


def _merge_csv_original_fields(rows, items):
    if len(rows) != len(items):
        return items
    merged = []
    for row, item in zip(rows, items):
        if not isinstance(item, dict):
            merged.append(item)
            continue
        it = dict(item)
        for field in ("word", "part_of_speech", "meaning", "example", "note"):
            if row.get(field) and not it.get(field):
                it[field] = row[field]
        merged.append(it)
    return merged


# ---- 入口 1：CSV ----

def prepare_csv(user_id, language_code, file_bytes, filename):
    """校验 CSV 大小/行数/格式，建 intake_source + source_segments（不调 LLM）。"""
    if len(file_bytes) > INTAKE_MAX_CSV_BYTES:
        raise CsvTooLarge(f"CSV 超过 {INTAKE_MAX_CSV_BYTES // 1024}KB，请拆分上传")
    wl = _language_word_list(user_id, language_code)
    if wl is None:
        return None

    try:
        text = file_bytes.decode("utf-8-sig")
    except UnicodeDecodeError:
        raise CsvFormatError("CSV 必须是 UTF-8 编码")

    reader = csv.DictReader(io.StringIO(text))
    if reader.fieldnames is None:
        raise CsvFormatError("CSV 为空或缺少表头")
    cols = {_canonical_csv_header(c) for c in reader.fieldnames}
    if "word" not in cols or "meaning" not in cols:
        raise CsvFormatError(_CSV_REQUIRED_HINT)

    rows = []
    for row in reader:
        norm = _canonicalize_csv_row(row)
        if not norm.get("word"):
            continue
        rows.append(norm)
        if len(rows) > INTAKE_MAX_CSV_ROWS:
            raise CsvTooLarge(f"CSV 超过 {INTAKE_MAX_CSV_ROWS} 行，请拆分上传")
    if not rows:
        raise CsvFormatError("CSV 没有有效词行")

    source = IntakeSource(
        user_id=user_id, source_type="csv", language_code=language_code,
        word_list_id=wl.id, original_name=filename or "import.csv",
        status="processing", total_segments=len(rows),
    )
    db.session.add(source)
    db.session.flush()
    for i, row in enumerate(rows):
        db.session.add(SourceSegment(
            source_id=source.id, user_id=user_id, segment_index=i,
            raw_text=json.dumps(row, ensure_ascii=False),
        ))
    db.session.commit()
    return source


# ---- 入口 2：文本抽词 ----

def prepare_extract(user_id, language_code, text):
    """校验文档长度，建 intake_source + 单 segment（原文）。超长不进 LLM。"""
    text = (text or "").strip()
    if not text:
        raise CsvFormatError("文本为空")
    if len(text) > INTAKE_MAX_EXTRACT_CHARS:
        raise DocumentTooLong(
            f"文档 {len(text)} 字符，超过 {INTAKE_MAX_EXTRACT_CHARS}，请分段")
    wl = _language_word_list(user_id, language_code)
    if wl is None:
        return None

    source = IntakeSource(
        user_id=user_id, source_type="text_extract", language_code=language_code,
        word_list_id=wl.id, original_name=text[:50], status="processing",
        total_segments=1,
    )
    db.session.add(source)
    db.session.flush()
    db.session.add(SourceSegment(
        source_id=source.id, user_id=user_id, segment_index=0, raw_text=text))
    db.session.commit()
    return source


# ---- LLM 辅助 ----

_LANG = dict(words_svc._LANGUAGE_NAMES)
_FEEDBACK_LANG = dict(words_svc._FEEDBACK_LANGUAGE_NAMES)


def _feedback_lang_name(feedback_language_code):
    return _FEEDBACK_LANG.get(feedback_language_code or "zh", "中文")


def _normalize_csv_batch(rows, language_code, feedback_language_code="zh"):
    """归一化一批 CSV 词条：补全缺失、规范词性。返回候选 dict 列表 + usage。"""
    lang = _LANG.get(language_code, language_code)
    feedback_lang = _feedback_lang_name(feedback_language_code)
    system = (f"你是{lang}词条整理助手。对每个词补全释义/词性/例句（已有则保留），"
              f"meaning 字段必须使用{feedback_lang}解释。"
              "只输出 JSON：{\"items\":[{\"word\",\"part_of_speech\",\"meaning\",\"example\",\"note\"}]}，"
              "数量与输入一致，不要新增或删除词；note 字段已有则保留。")
    user = json.dumps(rows, ensure_ascii=False)
    try:
        res = llm.chat([{"role": "system", "content": system},
                        {"role": "user", "content": user}], task="extract", json_mode=True)
    except llm.AllProvidersDown:
        return [], None
    items = _parse_items(res.content)
    return items, res


def _extract_from_text(text, language_code, max_words, feedback_language_code="zh"):
    lang = _LANG.get(language_code, language_code)
    feedback_lang = _feedback_lang_name(feedback_language_code)
    system = (f"你是{lang}抽词助手。从文本中抽出对学习者可能陌生的词（非极高频、"
              f"非专有名词/数字），最多 {max_words} 个。每词给词性、释义、从原文摘取的例句。"
              f"meaning 字段必须使用{feedback_lang}解释。"
              "只输出 JSON：{\"items\":[{\"word\",\"part_of_speech\",\"meaning\",\"example\"}]}。")
    try:
        res = llm.chat([{"role": "system", "content": system},
                        {"role": "user", "content": text}], task="extract", json_mode=True)
    except llm.AllProvidersDown:
        return [], None
    return _parse_items(res.content), res


def _enrich_word(word, meaning, language_code, feedback_language_code="zh"):
    lang = _LANG.get(language_code, language_code)
    feedback_lang = _feedback_lang_name(feedback_language_code)
    system = (f"你是{lang}词条助手。给出该词的词性、释义、一个例句。"
              f"meaning 字段必须使用{feedback_lang}解释。"
              "只输出 JSON：{\"part_of_speech\",\"meaning\",\"example\"}。")
    user = f"词：{word}" + (f"\n已有释义：{meaning}" if meaning else "")
    try:
        res = llm.chat([{"role": "system", "content": system},
                        {"role": "user", "content": user}], task="extract", json_mode=True)
    except llm.AllProvidersDown:
        return {}, None
    try:
        return json.loads(res.content), res
    except (json.JSONDecodeError, TypeError):
        return {}, res


def _parse_items(content):
    try:
        data = json.loads(content)
    except (json.JSONDecodeError, TypeError):
        try:
            data = json.loads(content[content.index("{"):content.rindex("}") + 1])
        except (ValueError, json.JSONDecodeError):
            return []
    items = data.get("items") if isinstance(data, dict) else data
    return items if isinstance(items, list) else []


# ---- 处理（SSE 生成器；逐批调 LLM、记额度、写候选）----

def process_source(user_id, source_id):
    """生成器：分批处理 source，yield 进度事件。导入额度在每批 LLM 前检查。"""
    source = IntakeSource.query.filter_by(id=source_id, user_id=user_id).first()
    if source is None:
        yield {"type": "error", "message": "来源不存在"}
        return

    if source.status == "done":      # 幂等：已处理过，不重复抽词（防 SSE GET 被重开）
        yield {"type": "done", "candidates": source.total_candidates or 0,
               "source_id": source.id}
        return

    # 重处理（如上一次 SSE 被中断、status 仍为 processing）前清掉旧候选，避免累积
    _candidate_query(user_id, source.id).delete(synchronize_session=False)
    db.session.commit()

    remaining = quota_svc.import_remaining(user_id)
    if remaining <= 0:
        st = quota_svc.import_quota_status(user_id)
        source.status = "error"
        db.session.commit()
        yield {"type": "error", "message": f"今日导入额度已用完（{st['used']}/{st['limit']}）"}
        return

    own = quota_svc.import_quota_status(user_id)["own_key"]
    feedback_lang = words_svc.get_feedback_language(user_id)
    created = 0

    if source.source_type == "text_extract":
        seg = SourceSegment.query.filter_by(source_id=source.id).first()
        cap = min(INTAKE_MAX_EXTRACT_WORDS, remaining)
        items, res = _extract_from_text(
            seg.raw_text, source.language_code, cap, feedback_lang)
        if res is None:  # AI 不可用
            source.status = "error"
            db.session.commit()
            yield {"type": "error", "message": "AI 暂不可用，请稍后重试"}
            return
        items = _dedupe(items)[:cap]
        created = _write_candidates(user_id, source, items)
        quota_svc.record_import(user_id, count=created,
                                prompt_tokens=res.prompt_tokens,
                                completion_tokens=res.completion_tokens,
                                provider=res.provider, model=res.model,
                                used_user_key=own, feature="extract")
        yield {"type": "progress", "done": created, "total": created}

    elif source.source_type == "csv":
        segs = (SourceSegment.query.filter_by(source_id=source.id)
                .order_by(SourceSegment.segment_index).all())
        total = min(len(segs), remaining)
        segs = segs[:total]
        for start in range(0, len(segs), INTAKE_BATCH_SIZE):
            batch = segs[start:start + INTAKE_BATCH_SIZE]
            rows = [json.loads(s.raw_text) for s in batch]
            items, res = _normalize_csv_batch(
                rows, source.language_code, feedback_lang)
            if res is None:                    # AI 不可用 → CSV 原始列值兜底
                items = rows
                prompt_tokens = completion_tokens = 0
                provider, model, feature = "local", "csv", "clean_fallback"
                used_user_key = False
            else:
                if not items:                  # LLM 失败 → 用原始列值兜底
                    items = rows
                else:
                    items = _merge_csv_original_fields(rows, items)
                prompt_tokens = res.prompt_tokens
                completion_tokens = res.completion_tokens
                provider, model, feature = res.provider, res.model, "clean"
                used_user_key = own
            n = _write_candidates(user_id, source, items)
            created += n
            quota_svc.record_import(user_id, count=n,
                                    prompt_tokens=prompt_tokens,
                                    completion_tokens=completion_tokens,
                                    provider=provider, model=model,
                                    used_user_key=used_user_key, feature=feature)
            yield {"type": "progress", "done": created, "total": total}

    else:
        source.status = "error"
        db.session.commit()
        yield {"type": "error", "message": "不支持的导入来源类型"}
        return

    source.status = "done"
    source.total_candidates = created
    db.session.commit()
    yield {"type": "done", "candidates": created, "source_id": source.id}


def quick_add(user_id, language_code, word, meaning=None):
    """快速加词：单词，AI 补全，建 source + 1 候选。返回 (source, candidate)。"""
    word = (word or "").strip()
    if not word or len(word) > QUICK_ADD_MAX_CHARS:
        raise CsvFormatError("词为空或过长")
    wl = _language_word_list(user_id, language_code)
    if wl is None:
        return None, None
    quota_svc.check_import_quota(user_id, 1)    # 超限抛 ImportQuotaExceeded

    source = IntakeSource(
        user_id=user_id, source_type="quick_add", language_code=language_code,
        word_list_id=wl.id, original_name=word, status="processing",
        total_segments=1,
    )
    db.session.add(source)
    db.session.flush()

    feedback_lang = words_svc.get_feedback_language(user_id)
    enriched, res = _enrich_word(word, meaning, language_code, feedback_lang)
    if res is None:  # AI 不可用
        db.session.rollback()
        raise CsvFormatError("AI 暂不可用，请稍后重试")
    own = quota_svc.import_quota_status(user_id)["own_key"]
    cand = _write_candidates(user_id, source, [{
        "word": word,
        "part_of_speech": enriched.get("part_of_speech"),
        "meaning": enriched.get("meaning") or meaning,
        "example": enriched.get("example"),
    }])
    quota_svc.record_import(user_id, count=1,
                            prompt_tokens=res.prompt_tokens,
                            completion_tokens=res.completion_tokens,
                            provider=res.provider, model=res.model,
                            used_user_key=own, feature="quick_add")
    source.status = "done"
    source.total_candidates = 1
    db.session.commit()
    candidate = _candidate_query(user_id, source.id).first()
    return source, candidate


def _dedupe(items):
    seen, out = set(), []
    for it in items:
        w = (it.get("word") or "").strip().lower()
        if w and w not in seen:
            seen.add(w)
            out.append(it)
    return out


def _normalize_context_excerpt(value):
    if value is None:
        return None
    if not isinstance(value, str):
        raise ValueError("candidate context must be text")
    value = value.strip()
    if not value:
        return None
    if len(value) > CANDIDATE_CONTEXT_MAX_CHARS:
        raise ValueError("candidate context cannot exceed 300 characters")
    return value


def _candidate_context_pair(value, provenance):
    context = _normalize_context_excerpt(value)
    if context is None:
        if provenance not in (None, ""):
            raise ValueError("empty candidate context cannot have provenance")
        return None, None
    if provenance not in VALID_CONTEXT_PROVENANCE:
        raise ValueError("invalid candidate context provenance")
    return context, provenance


def _write_candidates(user_id, source, items) -> int:
    n = 0
    for it in items:
        w = (it.get("word") or "").strip()
        if not w:
            continue
        context_excerpt, context_provenance = _candidate_context_pair(
            it.get("context_excerpt"),
            it.get("context_provenance"),
        )
        db.session.add(WordCandidate(
            source_id=source.id, user_id=user_id, word=w,
            part_of_speech=it.get("part_of_speech"),
            meaning=it.get("meaning"), example=it.get("example"),
            source_example=it.get("source_example"),
            context_excerpt=context_excerpt,
            context_provenance=context_provenance,
            note=it.get("note"),
            context_start=it.get("context_start"),
            context_end=it.get("context_end"),
            status="pending",
        ))
        n += 1
    db.session.flush()
    return n


# ---- 候选词审核 + commit 入库 ----

def get_source(user_id, source_id) -> IntakeSource | None:
    return IntakeSource.query.filter_by(id=source_id, user_id=user_id).first()


def _candidate_query(user_id, source_id, status=None):
    q = WordCandidate.query.filter_by(source_id=source_id, user_id=user_id)
    if status is not None:
        q = q.filter_by(status=status)
    return q


def _existing_words(word_list_id) -> set:
    rows = (Word.query.with_entities(Word.word)
            .filter(Word.list_id == word_list_id).all())
    return {words_svc.normalize_word_identity(r[0]) for r in rows}


def list_candidates(user_id, source_id, status=None):
    """返回候选词列表，每条标注是否与目标词表已有词重复（去重提示）。

    默认按创建时间倒序（新在前）。可通过 status 过滤（'pending'/'accepted'/'ignored'）。
    """
    source = get_source(user_id, source_id)
    if source is None:
        return None, []
    existing = _existing_words(source.word_list_id)
    q = _candidate_query(user_id, source_id, status if status in ("pending", "accepted", "ignored") else None)
    cands = q.order_by(WordCandidate.created_at.desc()).all()
    out = [
        (c, words_svc.normalize_word_identity(c.word) in existing)
        for c in cands
    ]
    return source, out


def _get_candidate(user_id, candidate_id) -> WordCandidate | None:
    return WordCandidate.query.filter_by(id=candidate_id, user_id=user_id).first()


def get_candidate_source(user_id, candidate_id) -> IntakeSource | None:
    """Return the user-owned source for a candidate."""
    return (
        IntakeSource.query
        .join(WordCandidate, WordCandidate.source_id == IntakeSource.id)
        .filter(
            WordCandidate.id == candidate_id,
            WordCandidate.user_id == user_id,
            IntakeSource.user_id == user_id,
        )
        .first()
    )


def accept_candidate(user_id, candidate_id, edits=None) -> bool:
    """接受候选词（可带内联编辑后的字段）。"""
    c = _get_candidate(user_id, candidate_id)
    if c is None:
        return False

    has_context_edit = edits is not None and "context_excerpt" in edits
    edited_context = None
    if has_context_edit:
        edited_context = _normalize_context_excerpt(edits["context_excerpt"])

    if edits:
        for f in ("word", "part_of_speech", "meaning", "example", "note"):
            if f in edits and edits[f] is not None:
                setattr(c, f, edits[f])
    if has_context_edit and edited_context != c.context_excerpt:
        c.context_excerpt = edited_context
        c.context_provenance = "user_edited" if edited_context else None
    c.status = "accepted"
    db.session.commit()
    return True


def ignore_candidate(user_id, candidate_id) -> bool:
    c = _get_candidate(user_id, candidate_id)
    if c is None:
        return False
    c.status = "ignored"
    db.session.commit()
    return True


def bulk_accept(user_id, source_id) -> int:
    """一键接受该 source 下所有 pending 候选词。"""
    count = _candidate_query(user_id, source_id, status="pending").update(
        {"status": "accepted"}, synchronize_session=False)
    db.session.commit()
    return count


def commit_intake_source(user_id, source_id) -> int:
    """把已接受候选词写入 words + definitions。同词表内同词静默跳过（去重）。"""
    source = get_source(user_id, source_id)
    if source is None:
        return 0
    accepted = _candidate_query(user_id, source_id, status="accepted").all()
    existing = _existing_words(source.word_list_id)

    committed = 0
    for c in accepted:
        identity = words_svc.normalize_word_identity(c.word)
        if identity in existing:        # 静默去重
            conflict = (
                Word.query
                .filter(
                    Word.list_id == source.word_list_id,
                    db.func.lower(db.func.btrim(Word.word)) == identity,
                )
                .first()
            )
            if conflict is not None:
                c.word_id = conflict.id
            continue
        try:
            with db.session.begin_nested():
                word = Word(list_id=source.word_list_id, word=c.word.strip(),
                            due_date=utc_now(), interval=1, ease=2.5,
                            reps=0, lapses=0)
                db.session.add(word)
                db.session.flush()
                if source.source_type == "sessionpad":
                    example = (
                        c.example
                        if c.example and c.example.strip()
                        else None
                    )
                else:
                    example = c.source_example or c.example
                if any([c.meaning, c.part_of_speech, example, c.note]):
                    db.session.add(Definition(
                        word_id=word.id, part_of_speech=c.part_of_speech,
                        meaning=c.meaning, example=example, note=c.note))
                c.word_id = word.id
                db.session.flush()
        except IntegrityError:
            conflict = (Word.query
                        .filter(
                            Word.list_id == source.word_list_id,
                            db.func.lower(db.func.btrim(Word.word)) == identity,
                        ).first())
            if conflict is None:
                raise
            c.word_id = conflict.id
            existing.add(identity)
            continue
        existing.add(identity)
        committed += 1

    source.accepted_count = committed
    source.completed_at = utc_now()
    db.session.commit()
    return committed


def commit_all(user_id, source_id) -> int:
    """一键入库：先全部接受 pending，再写入 words + definitions。"""
    bulk_accept(user_id, source_id)
    return commit_intake_source(user_id, source_id)


def _cleanup_by_status(user_id, source_id, status) -> int:
    count = _candidate_query(user_id, source_id, status=status).delete(
        synchronize_session=False)
    db.session.commit()
    return count


def cleanup_ignored(user_id, source_id) -> int:
    return _cleanup_by_status(user_id, source_id, "ignored")


def cleanup_accepted(user_id, source_id) -> int:
    return _cleanup_by_status(user_id, source_id, "accepted")
