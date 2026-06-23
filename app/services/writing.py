"""造句批改闭环的业务逻辑。

流程纪律（针对 MemoBuddy 痛点）：
- submit_correction：批改 + 额度记账，**不入库**。
- save_entry：用户显式确认后才写 output_entries。
- is_nsfw 由批改结果决定，经签名 session 传递（路由层），不信客户端。
"""
from datetime import datetime

from app.extensions import db
from app.models.word import WordList, Word
from app.models.output import OutputEntry
from app.services import correction as correction_svc
from app.services import quota as quota_svc
from app.services.words import get_word

MAX_SENTENCE_CHARS = 140


class SentenceTooLong(Exception):
    pass


def get_practice_words(user_id: int, limit: int = 50) -> list[Word]:
    """造句可选词：到期词在前，其余按加入顺序。"""
    return (Word.query.join(WordList)
            .filter(WordList.user_id == user_id)
            .order_by(Word.due_date.asc())
            .limit(limit).all())


def submit_correction(user_id: int, word_id: int, sentence: str):
    """批改一句（不入库）。返回 CorrectionResult；词不属于用户返回 None。

    可能抛 quota.SentenceQuotaExceeded / SentenceTooLong。
    """
    sentence = (sentence or "").strip()
    if len(sentence) > MAX_SENTENCE_CHARS:        # 后端兜底（前端已硬限）
        raise SentenceTooLong()

    word = get_word(user_id, word_id)
    if word is None:
        return None

    source = quota_svc.check_write_quota(user_id)   # 超限抛 SentenceQuotaExceeded
    used_user_key = source == "user_key"

    wl = db.session.get(WordList, word.list_id)
    result = correction_svc.correct_sentence(
        sentence=sentence, target_word=word.word, language_code=wl.language_code,
    )

    # 仅在真正调用了 AI（非兜底）时记账 +1
    if not result.degraded:
        quota_svc.record_correction(
            user_id, prompt_tokens=result.prompt_tokens,
            completion_tokens=result.completion_tokens,
            provider=result.provider, model=result.model,
            used_user_key=used_user_key,
        )
    return result


def save_entry(user_id: int, word_id: int, pending: dict) -> OutputEntry:
    """用户确认后入库。pending 来自签名 session（is_nsfw 可信）。"""
    word = get_word(user_id, word_id)
    if word is None:
        return None
    has_error = bool(pending.get("has_error"))   # 提交时已算好（见 write 路由）
    entry = OutputEntry(
        word_id=word_id, user_id=user_id,
        original=pending.get("original", ""),
        corrected=pending.get("corrected", ""),
        feedback=pending.get("feedback", ""),
        translation=pending.get("translation", ""),
        has_error=has_error,
        is_nsfw=bool(pending.get("is_nsfw", True)),
        is_public=False,
        created_at=datetime.utcnow(),
    )
    db.session.add(entry)
    db.session.commit()
    return entry


def get_history(user_id: int, limit: int = 50) -> list[OutputEntry]:
    return (OutputEntry.query
            .filter_by(user_id=user_id)
            .order_by(OutputEntry.created_at.desc())
            .limit(limit).all())


def get_entry(user_id: int, entry_id: int) -> OutputEntry | None:
    return OutputEntry.query.filter_by(id=entry_id, user_id=user_id).first()


def publish_entry(user_id: int, entry_id: int) -> bool:
    """公开到广场入口（广场本体阶段七）。NSFW 不允许公开（fail-closed）。"""
    entry = get_entry(user_id, entry_id)
    if entry is None or entry.is_nsfw:
        return False
    entry.is_public = True
    db.session.commit()
    return True
