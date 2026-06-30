"""造句 + AI 批改闭环。

流程纪律（针对 MemoBuddy 三个流程 bug）：
- submit 只批改不入库；批改结果存签名 session（is_nsfw 可信、防篡改）。
- save 显式确认才写库。
- 刷新不重提交：submit/save 都走 hx-post，刷新 GET /write 是干净表单，不重放 POST。
"""
from flask import (Blueprint, render_template, redirect, url_for, request,
                   flash, abort, session)
from flask_login import login_required, current_user

from app.services import writing as writing_svc
from app.services import quota as quota_svc

bp = Blueprint("write", __name__)


def _uid():
    return current_user.id


@bp.get("/write")
@login_required
def compose():
    from app.services import words as words_svc
    lang = words_svc.get_current_language(_uid())
    return render_template(
        "write/compose.html",
        words=writing_svc.get_practice_words(_uid(), language_code=lang),
        quota=quota_svc.write_quota_status(_uid()),
        max_chars=writing_svc.MAX_SENTENCE_CHARS,
        current_language=lang,
        lang_name=words_svc._language_name(lang) if lang else None,
    )


@bp.post("/write/submit")
@login_required
def submit():
    word_id = request.form.get("word_id", type=int)
    sentence = request.form.get("sentence", "")
    if not word_id:
        abort(400)
    try:
        result = writing_svc.submit_correction(_uid(), word_id, sentence)
    except quota_svc.SentenceQuotaExceeded as e:
        return render_template("write/_quota_exceeded.html", used=e.used, limit=e.limit)
    except writing_svc.SentenceTooLong:
        abort(400)
    if result is None:
        abort(404)

    # 暂存待保存内容到签名 session（含可信 is_nsfw），不入库
    # 只存 save 需要的字段，避免把 LLM 返回的 errors[] 整列塞进签名 cookie（4KB 限）。
    # has_error 在此一次性算好（errors[] 仅用于它），不进 session。
    has_error = (bool(result.errors) or not result.target_word_used
                 or result.incomplete)
    session["pending"] = {
        "word_id": word_id,
        "original": sentence.strip(),
        "corrected": result.corrected,
        "translation": result.translation,
        "feedback": result.feedback,
        "has_error": has_error,
        "is_nsfw": result.is_nsfw,
    }
    return render_template("write/_result.html", r=result, degraded=result.degraded)


@bp.post("/write/save")
@login_required
def save():
    pending = session.get("pending")
    if not pending:
        return render_template("write/_expired.html")
    entry = writing_svc.save_entry(_uid(), pending["word_id"], pending)
    session.pop("pending", None)        # 用后即清，刷新不重存
    if entry is None:
        abort(404)
    return render_template("write/_saved.html", entry=entry)


@bp.post("/write/discard")
@login_required
def discard():
    session.pop("pending", None)
    return render_template("write/_discarded.html")


@bp.post("/write/<int:entry_id>/publish")
@login_required
def publish(entry_id):
    ok = writing_svc.publish_entry(_uid(), entry_id)
    if not ok:
        abort(400)                       # 不存在 / NSFW 不可公开
    return render_template("write/_published.html")


@bp.get("/write/history")
@login_required
def history():
    return render_template("write/history.html",
                           entries=writing_svc.get_history(_uid()))
