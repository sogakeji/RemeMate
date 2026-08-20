"""造句 + AI 批改闭环。

流程纪律（针对 MemoBuddy 三个流程 bug）：
- submit 只批改不入库；批改结果存签名 session（is_nsfw 可信、防篡改）。
- save 显式确认才写库。
- 刷新不重提交：submit/save 都走 hx-post，刷新 GET /write 是干净表单，不重放 POST。
"""
from flask import (Blueprint, render_template, redirect, url_for, request,
                   flash, abort, session, current_app)
from flask_login import login_required, current_user

from app.extensions import db
from app.i18n import localized_language_names, translate as _
from app.services import review_story_events as story_events_svc
from app.services import review_story_handoff as story_handoff_svc
from app.services import writing as writing_svc
from app.services import quota as quota_svc

bp = Blueprint("write", __name__)
_STORY_HANDOFF_SESSION_KEY = "review_story_handoff"


def _uid():
    return current_user.id


def _story_handoff_from_session():
    value = session.get(_STORY_HANDOFF_SESSION_KEY)
    if not isinstance(value, dict):
        return None
    run_id = value.get("run_id")
    term_key = value.get("term_key")
    if isinstance(run_id, bool) or not isinstance(run_id, int):
        return None
    if not isinstance(term_key, str):
        return None
    return story_handoff_svc.resolve_review_story_writing_target(
        user_id=_uid(),
        run_id=run_id,
        term_key=term_key,
    )


def _record_story_event_safely(*, run_id, event_type):
    try:
        story_events_svc.record_review_story_event(
            user_id=_uid(),
            run_id=run_id,
            event_type=event_type,
        )
    except Exception:
        db.session.rollback()
        current_app.logger.exception(
            "review story writing event failed: %s",
            event_type,
        )


@bp.post("/write/from-story")
@login_required
def story_handoff():
    run_id = request.form.get("story_run_id", type=int)
    term_key = (request.form.get("term_key") or "").strip()
    if run_id is None:
        abort(404)
    target = story_handoff_svc.resolve_review_story_writing_target(
        user_id=_uid(),
        run_id=run_id,
        term_key=term_key,
    )
    if target is None:
        abort(404)

    session[_STORY_HANDOFF_SESSION_KEY] = {
        "run_id": target.run_id,
        "term_key": target.term_key,
    }
    _record_story_event_safely(
        run_id=target.run_id,
        event_type="story_writing_handoff",
    )
    return redirect(url_for("write.compose", source="review-story"))


@bp.get("/write")
@login_required
def compose():
    from app.services import words as words_svc

    story_target = None
    if request.args.get("source") == "review-story":
        story_target = _story_handoff_from_session()
        if story_target is None:
            session.pop(_STORY_HANDOFF_SESSION_KEY, None)

    mode = request.args.get("mode") if request.args.get("mode") in {"diary"} else "sentence"
    stored_lang = words_svc.get_current_language(_uid())
    lang = (
        story_target.target_language
        if story_target is not None
        else stored_lang
    )
    feedback_lang = words_svc.get_feedback_language(_uid())
    words = [] if lang is None else writing_svc.get_practice_words(
        _uid(), language_code=lang)
    has_any_words = lang is not None and any(
        count > 0 for _, count in words_svc.get_word_lists(_uid(), language_code=lang))
    if story_target is not None:
        if all(word.id != story_target.word_id for word in words):
            words.insert(0, story_target.word)
        target_word = story_target.word
    else:
        target_word = words[0] if words else None
    return render_template(
        "write/compose.html",
        words=words,
        target_word=target_word,
        story_handoff=(story_target is not None),
        has_any_words=has_any_words,
        quota=quota_svc.write_quota_status(_uid()),
        max_chars=writing_svc.MAX_SENTENCE_CHARS,
        diary_line_count=writing_svc.DIARY_LINE_COUNT,
        diary_line_chars=writing_svc.MAX_DIARY_LINE_CHARS,
        diary_prompt=writing_svc.random_diary_prompt(feedback_lang),
        mode=mode,
        writing_language=lang,
        lang_name=localized_language_names().get(lang, lang) if lang else None,
    )


@bp.post("/write/submit")
@login_required
def submit():
    from app.services import words as words_svc

    mode = request.form.get("mode", "sentence")
    word_id = request.form.get("word_id", type=int)
    sentence = request.form.get("sentence", "")
    if mode != "diary" and not word_id:
        abort(400)
    story_target = None
    if request.form.get("story_handoff") == "1":
        if mode == "diary":
            abort(400)
        story_target = _story_handoff_from_session()
        if story_target is None or story_target.word_id != word_id:
            abort(404)
    lang = (
        story_target.target_language
        if story_target is not None
        else words_svc.get_current_language(_uid())
    )
    if lang is None:
        abort(400)
    feedback_lang = words_svc.get_feedback_language(_uid())
    try:
        if mode == "diary":
            result = writing_svc.submit_diary(
                _uid(), request.form.get("diary", ""),
                prompt=request.form.get("prompt", ""), language_code=lang,
                feedback_language_code=feedback_lang,
            )
        else:
            result = writing_svc.submit_correction(
                _uid(), word_id, sentence, language_code=lang,
                feedback_language_code=feedback_lang,
            )
    except quota_svc.SentenceQuotaExceeded as e:
        return render_template("write/_quota_exceeded.html", used=e.used, limit=e.limit)
    except writing_svc.SentenceTooLong:
        abort(400)
    except writing_svc.DiaryFormatError:
        session.pop("pending", None)
        return render_template("write/_diary_format_error.html")
    except writing_svc.SentenceLanguageMismatch:
        return render_template("write/_language_mismatch.html")
    if result is None:
        abort(404)

    if result.degraded:
        session.pop("pending", None)
        return render_template(
            "write/_result.html", r=result, degraded=True,
            degraded_message=_("write.ai_unavailable"),
        )

    # 暂存待保存内容到签名 session（含可信 is_nsfw），不入库。
    # 只存 save 需要的字段，避免把 LLM 返回的 errors[] 整列塞进签名 cookie（4KB 限）。
    has_error = (bool(result.errors) or not result.target_word_used
                 or result.incomplete)
    pending = {
        "mode": mode,
        "word_id": word_id,
        "original": (request.form.get("diary", "") if mode == "diary" else sentence).strip(),
        "corrected": result.corrected,
        "translation": result.translation,
        "feedback": result.feedback,
        "has_error": has_error,
        "is_nsfw": result.is_nsfw,
        "language_code": lang,
    }
    if story_target is not None:
        pending["story_run_id"] = story_target.run_id
        pending["story_term_key"] = story_target.term_key
        session.pop(_STORY_HANDOFF_SESSION_KEY, None)
    session["pending"] = pending
    return render_template("write/_result.html", r=result, degraded=result.degraded)


@bp.post("/write/save")
@login_required
def save():
    pending = session.get("pending")
    if not pending:
        return render_template("write/_expired.html")
    if pending.get("mode") == "diary":
        entry = writing_svc.save_diary_entry(_uid(), pending)
    else:
        entry = writing_svc.save_entry(_uid(), pending["word_id"], pending)
    session.pop("pending", None)
    if entry is None:
        abort(404)

    story_run_id = pending.get("story_run_id")
    story_term_key = pending.get("story_term_key")
    if (
        isinstance(story_run_id, int)
        and not isinstance(story_run_id, bool)
        and isinstance(story_term_key, str)
        and story_term_key
    ):
        _record_story_event_safely(
            run_id=story_run_id,
            event_type="story_output_saved",
        )
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
        abort(400)
    if not request.headers.get("HX-Request"):
        flash(_("write.published"))
        return redirect(url_for("write.history"))
    return render_template("write/_published.html")


@bp.post("/write/<int:entry_id>/unpublish")
@login_required
def unpublish(entry_id):
    ok = writing_svc.unpublish_entry(_uid(), entry_id)
    if not ok:
        abort(400)
    flash(_("write.unpublished"))
    if request.form.get("next") == "square":
        lang = request.form.get("lang") or "all"
        content_type = request.form.get("kind") or request.form.get("type") or "all"
        return redirect(url_for("square.index", lang=lang, kind=content_type))
    return redirect(url_for("write.history"))


@bp.get("/write/history")
@login_required
def history():
    return render_template("write/history.html",
                           entries=writing_svc.get_history(_uid()))
