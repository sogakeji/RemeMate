"""词库管理 + SRS 复习 + 统计。

路由只取参数、调 service、渲染；业务逻辑在 services/words.py（见模块边界规则）。
"""
import json

from flask import (Blueprint, render_template, request, abort, jsonify,
                   redirect, url_for, flash, session, current_app)
from flask_login import login_required, current_user
from sqlalchemy import create_engine

from app.i18n import localized_language_names, translate as _
from app.services import words as words_svc
from app.services import llm as llm_svc
from app.services import review_links
from app.blueprints.words.forms import LanguageChoiceForm

bp = Blueprint("words", __name__)


def _uid():
    return current_user.id


# ---- 加词中心（单一入口：手工多词义 + AI 三端点；导入/抽词并入此页入口） ----

_POS_CHOICES = ["", "n.", "v.", "adj.", "adv.", "prep.", "conj.",
                "pron.", "interj.", "num.", "art.", "phr."]


def _clean_definitions_from_form():
    rows = zip(
        request.form.getlist("part_of_speech"),
        request.form.getlist("meaning"),
        request.form.getlist("example"),
        request.form.getlist("note"),
    )
    cleaned = []
    for pos, meaning, example, note in rows:
        item = {
            "part_of_speech": (pos or "").strip(),
            "meaning": (meaning or "").strip(),
            "example": (example or "").strip(),
            "note": (note or "").strip(),
        }
        if any(item.values()):
            cleaned.append(item)
    return cleaned


def _previous_review_word():
    prev_id = session.get("review_previous_word_id")
    if not prev_id:
        return None
    prev = words_svc.get_word(_uid(), prev_id)
    lang = words_svc.get_current_language(_uid())
    if prev is None or prev.word_list.language_code != lang:
        return None
    return prev


def _previous_available(current_word=None):
    prev = _previous_review_word()
    return bool(prev and (current_word is None or prev.id != current_word.id))


def _current_review_word():
    lang = words_svc.get_current_language(_uid())
    due = words_svc.get_due_words(_uid(), limit=1, language_code=lang) if lang else []
    return due[0] if due else None


@bp.get("/words/add")
@login_required
def add_center():
    form = LanguageChoiceForm()
    language_names = localized_language_names()
    form.language_code.choices = [
        (code, language_names.get(code, label))
        for code, label in form.language_code.choices
    ]
    # 默认选当前语言（用户切了语言，进加词中心就该是该语言；仍可下拉切其它语言加多语言）
    cur = words_svc.get_current_language(_uid())
    if cur:
        form.language_code.data = cur
    return render_template("words/add.html", form=form, pos_choices=_POS_CHOICES,
                           lang_map=language_names,
                           ai_enabled=bool(llm_svc.get_chain("general")))


@bp.post("/words/add")
@login_required
def add_submit():
    """JSON 多词义提交：{language_code, word, definitions:[{part_of_speech,meaning,example,note}, ...]}.

    绑定该语言的隐式词表（不存在则建），word 挂多条 Definition。CSRF 走 HTMX
    全局 X-CSRFToken 头（fetch 同理带）。
    """
    data = request.get_json(silent=True) or {}
    lang = data.get("language_code", "").strip()
    word = (data.get("word") or "").strip()
    defs = data.get("definitions") or []
    if lang not in words_svc._LANGUAGE_NAMES:
        return jsonify({"error": _("manual.select_language")}), 400
    if not word or len(word) > 200:
        return jsonify({"error": _("manual.word_invalid")}), 400
    if not defs or not isinstance(defs, list):
        return jsonify({"error": _("manual.definition_required")}), 400
    # 清洗：允许空字段，但要求每条至少有词性或释义
    cleaned = []
    for d in defs:
        if not isinstance(d, dict):
            continue
        pos = (d.get("part_of_speech") or "").strip()
        meaning = (d.get("meaning") or "").strip()
        example = (d.get("example") or "").strip()
        note = (d.get("note") or "").strip()
        if not pos and not meaning:
            continue
        cleaned.append({"part_of_speech": pos or None, "meaning": meaning or None,
                         "example": example or None, "note": note or None})
    if not cleaned:
        return jsonify({"error": _("manual.definition_content_required")}), 400

    # 加词到某语言也代表用户正在学该语言，和首页切语言保持同一收敛口径。
    words_svc.set_current_language(_uid(), lang)
    wl = words_svc.get_or_create_language_list(_uid(), lang)
    w = words_svc.add_word(_uid(), wl.id, word, definitions=cleaned)
    if w is None:
        return jsonify({"error": _("manual.add_failed")}), 500
    return jsonify({"ok": True, "word_id": w.id, "word": word,
                    "list_id": wl.id})


@bp.post("/words/ai-fill")
@login_required
def ai_fill():
    """AI 一键填充：{word, language_code} → {definitions:[...]} 或 {error}。"""
    data = request.get_json(silent=True) or {}
    word = (data.get("word") or "").strip()
    lang = data.get("language_code", "").strip()
    if not word:
        return jsonify({"error": _("manual.enter_word")}), 400
    if lang not in words_svc._LANGUAGE_NAMES:
        return jsonify({"error": _("manual.select_language")}), 400
    info = llm_svc.generate_full_word_info(
        word,
        language=words_svc._language_name(lang),
        feedback_language=words_svc._feedback_language_name(
            words_svc.get_feedback_language(_uid())),
    )
    if info.get("error"):
        return jsonify({"error": _("manual.ai_unavailable")})
    return jsonify(info)


@bp.post("/words/generate-example")
@login_required
def generate_example():
    """生成例句：{word, part_of_speech, meaning, language_code} → {example} 或 {error}。"""
    data = request.get_json(silent=True) or {}
    word = (data.get("word") or "").strip()
    pos = (data.get("part_of_speech") or "").strip()
    meaning = (data.get("meaning") or "").strip()
    lang = data.get("language_code", "").strip()
    if not word or not meaning:
        return jsonify({"error": _("manual.required")}), 400
    if lang not in words_svc._LANGUAGE_NAMES:
        return jsonify({"error": _("manual.select_language")}), 400
    out = llm_svc.generate_example(word, pos, meaning,
                                   language=words_svc._language_name(lang),
                                   feedback_language=words_svc._feedback_language_name(
                                       words_svc.get_feedback_language(_uid())))
    if out is None:
        return jsonify({"error": _("manual.ai_unavailable")}), 503
    return jsonify({"example": out})


@bp.post("/words/generate-note")
@login_required
def generate_note():
    """生成笔记：{word, part_of_speech, meaning, language_code} → {note} 或 {error}。"""
    data = request.get_json(silent=True) or {}
    word = (data.get("word") or "").strip()
    pos = (data.get("part_of_speech") or "").strip()
    meaning = (data.get("meaning") or "").strip()
    lang = data.get("language_code", "").strip()
    if not word or not meaning:
        return jsonify({"error": _("manual.required")}), 400
    if lang not in words_svc._LANGUAGE_NAMES:
        return jsonify({"error": _("manual.select_language")}), 400
    out = llm_svc.generate_note(word, pos, meaning,
                                language=words_svc._language_name(lang),
                                feedback_language=words_svc._feedback_language_name(
                                    words_svc.get_feedback_language(_uid())))
    if out is None:
        return jsonify({"error": _("manual.ai_unavailable")}), 503
    return jsonify({"note": out})


@bp.get("/words/<int:word_id>/edit")
@login_required
def edit_word(word_id):
    word = words_svc.get_word(_uid(), word_id)
    if word is None:
        abort(404)
    return render_template("words/edit.html", word=word, pos_choices=_POS_CHOICES)


@bp.post("/words/<int:word_id>/edit")
@login_required
def update_word(word_id):
    word = words_svc.get_word(_uid(), word_id)
    if word is None:
        abort(404)
    new_word = (request.form.get("word") or "").strip()
    definitions = _clean_definitions_from_form()
    if not new_word:
        flash(_("word.empty_error"))
        return render_template("words/edit.html", word=word, pos_choices=_POS_CHOICES), 400
    if not definitions:
        flash(_("word.definition_error"))
        return render_template("words/edit.html", word=word, pos_choices=_POS_CHOICES), 400
    try:
        updated = words_svc.update_word(_uid(), word_id, new_word, definitions)
    except ValueError:
        flash(_("manual.add_failed"))
        return render_template("words/edit.html", word=word, pos_choices=_POS_CHOICES), 400
    if updated is None:
        abort(404)
    flash(_("word.updated"))
    return redirect(url_for("words.lists"))


@bp.post("/words/<int:word_id>/toggle-marked")
@login_required
def toggle_marked(word_id):
    word = words_svc.toggle_marked(_uid(), word_id)
    if word is None:
        abort(404)
    if request.headers.get("HX-Request"):
        return render_template("review/_card.html", word=word)
    return redirect(url_for("words.lists"))


@bp.post("/words/<int:word_id>/delete")
@login_required
def delete_word(word_id):
    if not words_svc.delete_word(_uid(), word_id):
        abort(404)
    flash(_("word.deleted"))
    return redirect(url_for("words.lists"))


# ---- 词库 / 词表 / 复习 / 统计（既有） ----

@bp.get("/words")
@login_required
def lists():
    sort = request.args.get("sort", "due")
    if sort not in {"due", "recent", "lapses"}:
        sort = "due"
    marked_only = request.args.get("marked") == "1"
    lang, ws = words_svc.get_words_for_current_language(
        _uid(), sort=sort, marked_only=marked_only)
    return render_template("words/list.html", words=ws,
                           current_language=lang,
                           lang_name=localized_language_names().get(lang, lang) if lang else None,
                           current_sort=sort,
                           marked_only=marked_only)


@bp.get("/words/<int:list_id>")
@login_required
def detail(list_id):
    wl = words_svc.get_word_list(_uid(), list_id, eager=True)
    if wl is None:
        abort(404)
    return render_template("words/detail.html", wl=wl)


@bp.route("/review")
@login_required
def review():
    lang = words_svc.get_current_language(_uid())
    due = words_svc.get_due_words(_uid(), limit=1, language_code=lang) if lang else []
    word = due[0] if due else None
    return render_template("review/review.html", word=word,
                           previous_available=_previous_available(word))


@bp.get("/review/current")
@login_required
def current_review_card():
    word = _current_review_word()
    return render_template("review/_card.html", word=word,
                           previous_available=_previous_available(word))


@bp.get("/review/previous")
@login_required
def previous_review_card():
    word = _previous_review_word()
    if word is None:
        abort(404)
    return render_template("review/_card.html", word=word, is_previous=True)


@bp.route("/review/<int:word_id>/grade", methods=["POST"])
@login_required
def grade(word_id):
    button = request.form.get("button", "")
    try:
        result = words_svc.review_word(_uid(), word_id, button)
    except ValueError:
        abort(400)                      # 非法/缺失 button（M1）
    if result is None:
        abort(404)
    session["review_previous_word_id"] = result.id
    lang = words_svc.get_current_language(_uid()) or result.word_list.language_code
    nxt = words_svc.get_due_words(_uid(), limit=1, language_code=lang)
    # HTMX：返回下一张卡片片段（无则完成提示）
    word = nxt[0] if nxt else None
    return render_template("review/_card.html", word=word,
                           previous_available=_previous_available(word))


def _dispatch_engine():
    dispatch_url = current_app.config.get("DISPATCH_DATABASE_URL")
    if not dispatch_url:
        raise RuntimeError("DISPATCH_DATABASE_URL missing")
    return create_engine(dispatch_url, pool_pre_ping=True)


@bp.get("/bark/review/<token>")
def bark_review_page(token):
    """Public one-card review page opened from a signed Bark notification."""
    engine = _dispatch_engine()
    try:
        with engine.begin() as conn:
            word = review_links.get_review_link_word(
                conn, current_app.config["SECRET_KEY"], token)
    finally:
        engine.dispose()
    if word is None:
        return render_template("review/bark_token.html", word=None), 410
    return render_template("review/bark_token.html", word=word, token=token)


@bp.post("/bark/review/<token>/grade")
def bark_review_grade(token):
    button = request.form.get("button", "")
    engine = _dispatch_engine()
    try:
        with engine.begin() as conn:
            result = review_links.apply_review_link_grade(
                conn, current_app.config["SECRET_KEY"], token, button)
    except ValueError:
        abort(400)
    finally:
        engine.dispose()
    if result is None:
        return render_template("review/bark_token.html", word=None), 410
    return render_template("review/bark_token.html", word=result.word,
                           reviewed=True,
                           already_reviewed=result.already_reviewed)


@bp.route("/stats")
@login_required
def stats():
    # 统计按当前语言看板（与首页/词库/加词闭环一致）：total/due/list 都按当前语言切，
    # reviewed_today/heatmap 跨语言合计（复习历史不按语言切更稳）。
    lang = words_svc.get_current_language(_uid())
    return render_template("words/stats.html",
                           stats=words_svc.get_stats(_uid(), language_code=lang),
                           current_language=lang,
                           lang_name=localized_language_names().get(lang, lang) if lang else None)
