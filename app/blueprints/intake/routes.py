"""输入管道：CSV / 文本抽词 / 快速加词 + 候选词审核 + commit。

CSV/extract 走 SSE：上传/提交先建 source（快，不烧 token），再由前端 EventSource
连 /process 流式分批处理。前置上限超限直接提示，不进 LLM。
"""
import json

from flask import (Blueprint, render_template, redirect, url_for, request,
                   flash, abort, Response, stream_with_context)
from flask_login import login_required, current_user

from app.services import intake as intake_svc
from app.services import quota as quota_svc
from app.services.words import get_word_lists

bp = Blueprint("intake", __name__)


def _uid():
    return current_user.id


def _lists_for_picker():
    # get_word_lists 返回 (wl, count) 元组；这里只要 wl
    return [wl for wl, _ in get_word_lists(_uid())]


# ---- CSV ----

@bp.get("/intake/import")
@login_required
def import_page():
    return render_template("intake/import.html", lists=_lists_for_picker(),
                           quota=quota_svc.import_quota_status(_uid()))


@bp.post("/intake/import")
@login_required
def import_csv():
    word_list_id = request.form.get("word_list_id", type=int)
    file = request.files.get("file")
    if not word_list_id or file is None or not file.filename:
        flash("请选择词表并上传 CSV")
        return redirect(url_for("intake.import_page"))
    try:
        source = intake_svc.prepare_csv(
            _uid(), word_list_id, request.form.get("language_code", "fr"),
            file.read(), file.filename)
    except (intake_svc.CsvTooLarge, intake_svc.CsvFormatError) as e:
        flash(str(e))
        return redirect(url_for("intake.import_page"))
    if source is None:
        abort(404)
    return redirect(url_for("intake.processing", source_id=source.id))


# ---- 文本抽词 ----

@bp.get("/intake/extract")
@login_required
def extract_page():
    return render_template("intake/extract.html", lists=_lists_for_picker(),
                           quota=quota_svc.import_quota_status(_uid()),
                           max_chars=intake_svc.INTAKE_MAX_EXTRACT_CHARS)


@bp.post("/intake/extract")
@login_required
def extract():
    word_list_id = request.form.get("word_list_id", type=int)
    if not word_list_id:
        flash("请选择词表")
        return redirect(url_for("intake.extract_page"))
    try:
        source = intake_svc.prepare_extract(
            _uid(), word_list_id, request.form.get("language_code", "fr"),
            request.form.get("text", ""))
    except intake_svc.DocumentTooLong as e:
        flash(str(e))
        return redirect(url_for("intake.extract_page"))
    except intake_svc.CsvFormatError as e:
        flash(str(e))
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
            yield f"event: {event['type']}\ndata: {json.dumps(event, ensure_ascii=False)}\n\n"

    return Response(gen(), mimetype="text/event-stream",
                    headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})


# ---- 快速加词 ----

@bp.get("/intake/quick-add")
@login_required
def quick_add_page():
    return render_template("intake/quick_add.html", lists=_lists_for_picker(),
                           quota=quota_svc.import_quota_status(_uid()))


@bp.post("/intake/quick-add")
@login_required
def quick_add():
    word_list_id = request.form.get("word_list_id", type=int)
    if not word_list_id:
        flash("请选择词表")
        return redirect(url_for("intake.quick_add_page"))
    try:
        source, _ = intake_svc.quick_add(
            _uid(), word_list_id, request.form.get("language_code", "fr"),
            request.form.get("word", ""), request.form.get("meaning"))
    except quota_svc.ImportQuotaExceeded as e:
        flash(f"今日导入额度已用完（{e.used}/{e.limit}）")
        return redirect(url_for("intake.quick_add_page"))
    except intake_svc.CsvFormatError as e:
        flash(str(e))
        return redirect(url_for("intake.quick_add_page"))
    if source is None:
        abort(404)
    return redirect(url_for("intake.candidates", source_id=source.id))


# ---- 候选词审核 ----

@bp.get("/intake/<int:source_id>/candidates")
@login_required
def candidates(source_id):
    source, cands = intake_svc.list_candidates(_uid(), source_id)
    if source is None:
        abort(404)
    return render_template("intake/candidates.html", source=source, candidates=cands)


@bp.post("/intake/candidates/<int:candidate_id>/accept")
@login_required
def accept(candidate_id):
    edits = {f: request.form.get(f) for f in
             ("word", "part_of_speech", "meaning", "example") if f in request.form}
    if not intake_svc.accept_candidate(_uid(), candidate_id, edits or None):
        abort(404)
    return render_template("intake/_candidate_done.html", action="已接受")


@bp.post("/intake/candidates/<int:candidate_id>/ignore")
@login_required
def ignore(candidate_id):
    if not intake_svc.ignore_candidate(_uid(), candidate_id):
        abort(404)
    return render_template("intake/_candidate_done.html", action="已忽略")


@bp.post("/intake/<int:source_id>/bulk-accept")
@login_required
def bulk_accept(source_id):
    intake_svc.bulk_accept(_uid(), source_id)
    return redirect(url_for("intake.candidates", source_id=source_id))


@bp.post("/intake/<int:source_id>/commit")
@login_required
def commit(source_id):
    source = intake_svc.get_source(_uid(), source_id)
    if source is None:
        abort(404)
    n = intake_svc.commit_intake_source(_uid(), source_id)
    flash(f"已入库 {n} 个词")
    return redirect(url_for("words.detail", list_id=source.word_list_id))
