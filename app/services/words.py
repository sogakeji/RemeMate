"""词库 / 词 的业务逻辑。

所有函数显式接收 user_id（第二层防御）；RLS 是数据库兜底（第三层）。
词、释义无 user_id 列，必须 JOIN word_lists 过滤 user_id。
"""
from datetime import datetime, timedelta

from app.extensions import db
from app.models.word import WordList, Word, Definition, ReviewLog
from app.services import srs


# ---- 词表 ----

def create_word_list(user_id: int, name: str, language_code: str) -> WordList:
    wl = WordList(user_id=user_id, name=name, language_code=language_code)
    db.session.add(wl)
    db.session.commit()
    return wl


def get_word_lists(user_id: int) -> list[WordList]:
    return (WordList.query
            .filter_by(user_id=user_id)
            .order_by(WordList.created_at.desc())
            .all())


def get_word_list(user_id: int, list_id: int) -> WordList | None:
    return WordList.query.filter_by(id=list_id, user_id=user_id).first()


def delete_word_list(user_id: int, list_id: int) -> bool:
    wl = get_word_list(user_id, list_id)
    if wl is None:
        return False
    db.session.delete(wl)  # cascade 删 words/definitions
    db.session.commit()
    return True


# ---- 词 ----

def add_word(user_id: int, list_id: int, word: str, *, meaning=None,
             part_of_speech=None, example=None, note=None) -> Word | None:
    wl = get_word_list(user_id, list_id)
    if wl is None:
        return None
    w = Word(list_id=wl.id, word=word, due_date=datetime.utcnow(),
             interval=1, ease=2.5, reps=0, lapses=0)
    db.session.add(w)
    db.session.flush()
    if any([meaning, part_of_speech, example, note]):
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


def get_due_words(user_id: int, limit: int | None = None) -> list[Word]:
    q = (Word.query
         .join(WordList)
         .filter(WordList.user_id == user_id,
                 Word.due_date <= datetime.utcnow())
         .order_by(Word.due_date))
    if limit:
        q = q.limit(limit)
    return q.all()


# ---- 统计 ----

def get_stats(user_id: int) -> dict:
    now = datetime.utcnow()
    today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
    total = (Word.query.join(WordList)
             .filter(WordList.user_id == user_id).count())
    due = (Word.query.join(WordList)
           .filter(WordList.user_id == user_id, Word.due_date <= now).count())
    reviewed_today = (ReviewLog.query
                      .filter(ReviewLog.user_id == user_id,
                              ReviewLog.ts >= today_start).count())
    lists = WordList.query.filter_by(user_id=user_id).count()
    return {
        "total_words": total,
        "due_count": due,
        "reviewed_today": reviewed_today,
        "list_count": lists,
    }
