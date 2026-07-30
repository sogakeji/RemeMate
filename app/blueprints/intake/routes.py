"""输入管道：CSV / 文本抽词 / 快速加词 + 候选词审核 + commit。

CSV/extract 走 SSE：上传/提交先建 source（快，不烧 token），再由前端 EventSource
连 /process 流式分批处理。前置上限超限直接提示，不进 LLM。
"""
import json

from flask import (Blueprint, render_template, redirect, url_for, request,
                   flash, abort, Response, stream_with_context)
from flask_login import login_required, current_user

from app.extensions import db
from app.i18n import localized_language_names, translate as _
from app.services import intake as intake_svc
from app.services import quota as quota_svc
from app.services import sessionpad_review as sessionpad_review_svc
from app.services import words as words_svc
from app.models.reading import ReadingDocument

bp = Blueprint("intake", __name__)


def _uid():
    return current_user.id


def _language_choices():
    names = localized_language_names()
    return [(code, names.get(code, code))
            for code in words_svc.get_learning_languages(_uid())]


def _current_language():
    return words_svc.get_current_language(_uid())


# ---- CSV ----

@bp.get("/intake/import")
@login_required
def import_page():
    return render_template("intake/import.html",
                           available_languages=_language_choices(),
                           current_language=_current_language(),
                           quota=quota_svc.import_quota_status(_uid()))


@bp.post("/intake/import")
@login_required
def import_csv():
    language_code = request.form.get("language_code", "").strip()
    file = request.files.get("file")
    if not language_code or file is None or not file.filename:
        flash(_("intake.choose_and_upload"))
        return redirect(url_for("intake.import_page"))
    try:
        source = intake_svc.prepare_csv(
            _uid(), language_code, file.read(), file.filename)
    except intake_svc.CsvTooLarge:
        flash(_("intake.csv_too_large"))
        return redirect(url_for("intake.import_page"))
    except intake_svc.CsvFormatError:
        flash(_("intake.invalid_input"))
        return redirect(url_for("intake.import_page"))
    if source is None:
        abort(404)
    return redirect(url_for("intake.processing", source_id=source.id))


# ---- 文本抽词 ----

@bp.get("/intake/extract")
@login_required
def extract_page():
    return render_template("intake/extract.html",
                           available_languages=_language_choices(),
                           current_language=_current_language(),
                           quota=quota_svc.import_quota_status(_uid()),
                           max_chars=intake_svc.INTAKE_MAX_EXTRACT_CHARS)


@bp.post("/intake/extract")
@login_required
def extract():
    language_code = request.form.get("language_code", "").strip()
    if not language_code:
        flash(_("intake.choose_language"))
        return redirect(url_for("intake.extract_page"))
    try:
        source = intake_svc.prepare_extract(
            _uid(), language_code, request.form.get("text", ""))
    except intake_svc.DocumentTooLong:
        flash(_("intake.text_too_long"))
        return redirect(url_for("intake.extract_page"))
    except intake_svc.CsvFormatError:
        flash(_("intake.invalid_input"))
        return redirect(url_for("intake.extract_page"))
    if source is None:
        abort(404)
    return redirect(url_for("intake.processing", source_id=source.id))


# ---- SSE 处理 ----

@bp.get("/intake/<int:source_id>/processing")
@login_required
def processing(source_id):
    if intake_svc.get_source(_uid(), source_id) is None:
        abort(404)
    return render_template("intake/processing.html", source_id=source_id)


@bp.get("/intake/<int:source_id>/process")
@login_required
def process_stream(source_id):
    uid = _uid()

    @stream_with_context
    def gen():
        for event in intake_svc.process_source(uid, source_id):
            if event.get("type") == "error":
                event = {**event, "message": _("intake.processing_error")}
            yield f"event: {event['type']}\ndata: {json.dumps(event, ensure_ascii=False)}\n\n"

    return Response(gen(), mimetype="text/event-stream",
                    headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})


# ---- 快速加词 ----

@bp.get("/intake/quick-add")
@login_required
def quick_add_page():
    return render_template("intake/quick_add.html",
                           available_languages=_language_choices(),
                           current_language=_current_language(),
                           quota=quota_svc.import_quota_status(_uid()))


@bp.post("/intake/quick-add")
@login_required
def quick_add():
    language_code = request.form.get("language_code", "").strip()
    if not language_code:
        flash(_("intake.choose_language"))
        return redirect(url_for("intake.quick_add_page"))
    try:
        source, candidate = intake_svc.quick_add(
            _uid(), language_code, request.form.get("word", ""),
            request.form.get("meaning"))
    except quota_svc.ImportQuotaExceeded as e:
        flash(_("intake.quota_exceeded", used=e.used, limit=e.limit))
        return redirect(url_for("intake.quick_add_page"))
    except intake_svc.CsvFormatError as exc:
        key = "manual.ai_unavailable" if "AI" in str(exc) else "intake.invalid_input"
        flash(_(key))
        return redirect(url_for("intake.quick_add_page"))
    if source is None:
        abort(404)
    return redirect(url_for("intake.candidates", source_id=source.id))


# ---- 候选词审核 ----

@bp.get("/intake/<int:source_id>/candidates")
@login_required
def candidates(source_id):
    status = request.args.get("status") or None
    source, cands = intake_svc.list_candidates(_uid(), source_id, status=status)
    if source is None:
        abort(404)
    if source.source_type == "sessionpad":
        state = sessionpad_review_svc.get_review_state(
            _uid(), source_id, status=status,
        )
        if state is None:
            abort(404)
        return render_template(
            "intake/sessionpad_candidates.html",
            state=state,
            ai_degraded=request.args.get("ai") == "unavailable",
        )
    # 找关联的阅读材料，用于「返回书本」链接
    doc = ReadingDocument.query.filter_by(
        user_id=_uid(), intake_source_id=source_id).first()
    return render_template("intake/candidates.html", source=source,
                           candidates=cands, current_status=status,
                           document=doc)


@bp.post("/intake/sessionpad/candidates/<int:candidate_id>/accept")
@login_required
def accept_sessionpad_candidate(candidate_id):
    edits = {
        field: request.form.get(field)
        for field in (
            "word",
            "context_excerpt",
            "part_of_speech",
            "meaning",
            "example",
            "note",
        )
        if field in request.form
    }
    try:
        source_id = sessionpad_review_svc.accept_candidate(
            _uid(), candidate_id, edits,
        )
    except sessionpad_review_svc.SessionPadReviewError as exc:
        db.session.rollback()
        state = sessionpad_review_svc.get_review_state(
            _uid(), exc.source_id,
        )
        if state is None:
            abort(404)
        message = _(exc.message_key)
        if request.headers.get("HX-Request") == "true":
            return render_template(
                "intake/_sessionpad_review_main.html",
                state=state,
                review_error=message,
                review_error_code=exc.code,
            )
        flash(message)
        return redirect(url_for(
            "intake.candidates", source_id=exc.source_id,
        ))
    if source_id is None:
        abort(404)
    if request.headers.get("HX-Request") == "true":
        state = sessionpad_review_svc.get_review_state(_uid(), source_id)
        return render_template(
            "intake/_sessionpad_review_main.html",
            state=state,
        )
    return redirect(url_for("intake.candidates", source_id=source_id))

@bp.post("/intake/candidates/<int:candidate_id>/accept")
@login_required
def accept(candidate_id):
    source = intake_svc.get_candidate_source(_uid(), candidate_id)
    if source is not None and source.source_type == "sessionpad":
        abort(404)
    edits = {f: request.form.get(f) for f in
             ("word", "part_of_speech", "meaning", "example") if f in request.form}
    if not intake_svc.accept_candidate(_uid(), candidate_id, edits or None):
        abort(404)
    return render_template("intake/_candidate_done.html", action="candidate.done_accepted")


@bp.post("/intake/sessionpad/candidates/<int:candidate_id>/ignore")
@login_required
def ignore_sessionpad_candidate(candidate_id):
    source_id = sessionpad_review_svc.ignore_candidate(_uid(), candidate_id)
    if source_id is None:
        abort(404)
    if request.headers.get("HX-Request") == "true":
        state = sessionpad_review_svc.get_review_state(_uid(), source_id)
        return render_template(
            "intake/_sessionpad_review_main.html",
            state=state,
        )
    return redirect(url_for("intake.candidates", source_id=source_id))

@bp.post("/intake/candidates/<int:candidate_id>/ignore")
@login_required
def ignore(candidate_id):
    source = intake_svc.get_candidate_source(_uid(), candidate_id)
    if source is not None and source.source_type == "sessionpad":
        abort(404)
    if not intake_svc.ignore_candidate(_uid(), candidate_id):
        abort(404)
    return render_template("intake/_candidate_done.html", action="candidate.done_ignored")


@bp.post("/intake/<int:source_id>/bulk-accept")
@login_required
def bulk_accept(source_id):
    source = intake_svc.get_source(_uid(), source_id)
    if source is None or source.source_type == "sessionpad":
        abort(404)
    intake_svc.bulk_accept(_uid(), source_id)
    return redirect(url_for("intake.candidates", source_id=source_id))


@bp.post("/intake/<int:source_id>/commit")
@login_required
def commit(source_id):
    """提交入库：仅写入已接受的候选词（不含全部接受）。"""
    return _do_commit(source_id, intake_svc.commit_intake_source)


@bp.post("/intake/<int:source_id>/commit-all")
@login_required
def commit_all(source_id):
    """一键入库：先全部接受 pending，再写入词库。"""
    source = intake_svc.get_source(_uid(), source_id)
    if source is None or source.source_type == "sessionpad":
        abort(404)
    return _do_commit(source_id, intake_svc.commit_all)


def _do_commit(source_id, service_fn):
    source = intake_svc.get_source(_uid(), source_id)
    if source is None:
        abort(404)
    n = service_fn(_uid(), source_id)
    words_svc.set_current_language(_uid(), source.language_code)
    flash(_("candidate.committed", count=n))
    return redirect(url_for("words.lists"))


@bp.post("/intake/<int:source_id>/cleanup-all")
@login_required
def cleanup_all(source_id):
    """一键清理：同时删除已忽略和已接受的候选词。"""
    n_ignored = intake_svc.cleanup_ignored(_uid(), source_id)
    n_accepted = intake_svc.cleanup_accepted(_uid(), source_id)
    if n_ignored and n_accepted:
        flash(_("candidate.cleaned_both", ignored=n_ignored, accepted=n_accepted))
    elif n_ignored:
        flash(_("candidate.cleaned_ignored", count=n_ignored))
    elif n_accepted:
        flash(_("candidate.cleaned_accepted", count=n_accepted))
    else:
        flash(_("candidate.nothing_to_clean"))
    return redirect(url_for("intake.candidates", source_id=source_id))
