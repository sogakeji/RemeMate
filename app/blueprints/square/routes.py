"""句子广场。"""
from flask import Blueprint, redirect, render_template, request, url_for
from flask_login import current_user, login_required

from app.services import square as square_svc
from app.services import words as words_svc

bp = Blueprint("square", __name__, url_prefix="/square")


@bp.get("")
@login_required
def index():
    selected = request.args.get("lang") or words_svc.get_current_language(current_user.id)
    if selected == "all":
        selected = None
    if selected is not None and selected not in words_svc._LANGUAGE_NAMES:
        selected = None
    content_type = request.args.get("kind") or request.args.get("type") or "all"
    if content_type not in {"all", "sentence", "diary"}:
        content_type = "all"
    entries = square_svc.list_public_entries(
        current_user.id, language_code=selected, content_type=content_type)
    return render_template(
        "square/index.html",
        entries=entries,
        selected_language=selected,
        selected_type=content_type,
        lang_choices=words_svc._LANGUAGE_NAMES,
    )


@bp.post("/<int:entry_id>/upvote")
@login_required
def upvote(entry_id):
    square_svc.upvote_entry(current_user.id, entry_id)
    lang = request.form.get("lang") or request.args.get("lang") or ""
    content_type = (request.form.get("kind") or request.form.get("type")
                    or request.args.get("kind") or request.args.get("type") or "")
    params = {}
    if lang:
        params["lang"] = lang
    if content_type:
        params["kind"] = content_type
    target = url_for("square.index", **params) if params else url_for("square.index")
    return redirect(target)
