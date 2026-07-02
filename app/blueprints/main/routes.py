"""首页 = 当天主词卡（第一性原理：来背词，第一眼暴露词）+ 设置最小版。

- 首页就是复习页本身（仪表盘大字不进首页；独立 /review 作日常入口已砍）。
- 当前语言决定首页刷哪个语言的词、切换器在首页切换它；未设语言时空态引导去设置。
- /settings 最小版只做「正在学哪种语言」选择（= set_current_language 闭环建词表）。
  Bark/播客/per-user key 等阶段八再补。
"""
from urllib.parse import urlsplit

from flask import (Blueprint, render_template, redirect, url_for, flash,
                   request, session)
from flask_login import login_required, current_user

from app.services import words as words_svc

bp = Blueprint("main", __name__)


def _is_safe_next(target: str) -> bool:
    if not target:
        return False
    normalized = target.replace("\\", "/")
    if not normalized.startswith("/") or normalized.startswith("//"):
        return False
    parts = urlsplit(normalized)
    return not parts.scheme and not parts.netloc


def _has_previous_review_word(user_id, language_code, current_word=None):
    prev_id = session.get("review_previous_word_id")
    if not prev_id or not language_code:
        return False
    prev = words_svc.get_word(user_id, prev_id)
    if prev is None or prev.word_list.language_code != language_code:
        return False
    return current_word is None or prev.id != current_word.id


@bp.route("/")
@login_required
def index():
    lang = words_svc.get_current_language(current_user.id)
    word = None
    if lang is not None:
        due = words_svc.get_due_words(current_user.id, limit=1, language_code=lang)
        word = due[0] if due else None
    return render_template("main/index.html", user=current_user, word=word,
                           current_language=lang,
                           lang_choices=words_svc._LANGUAGE_NAMES,
                           previous_available=_has_previous_review_word(
                               current_user.id, lang, word),
                           stats=words_svc.get_stats(current_user.id))


@bp.post("/language/switch")
@login_required
def switch_language():
    """全局语言切换器：切当前语言后留在当前页面。"""
    code = request.form.get("language_code", "").strip()
    nxt = request.form.get("next")
    if code not in words_svc._LANGUAGE_NAMES:
        flash("未知语言")
        return redirect(nxt if _is_safe_next(nxt) else url_for("main.index"))
    words_svc.set_current_language(current_user.id, code)
    return redirect(nxt if _is_safe_next(nxt) else url_for("main.index"))


@bp.get("/settings")
@login_required
def settings():
    """设置页：在学语言集合多选（偏好清单），不是单选当前主攻。

    首页切换器「当前主攻」单选走 /language/switch；这里管的是「在学哪几种语言」
    集合。current_language 由 set_learning_languages 收敛到集合内（删当前主攻后
    自动收成集合首个/清空）。见 words.set_learning_languages 不变量。
    """
    return render_template("main/settings.html",
                           learning=words_svc.get_learning_languages(current_user.id),
                           lang_choices=words_svc._LANGUAGE_NAMES,
                           feedback_language=words_svc.get_feedback_language(current_user.id),
                           feedback_choices=words_svc._FEEDBACK_LANGUAGE_NAMES)


@bp.post("/settings")
@login_required
def save_settings():
    codes = request.form.getlist("languages")
    feedback_language = request.form.get("feedback_language", "zh").strip()
    try:
        words_svc.set_feedback_language(current_user.id, feedback_language)
    except ValueError:
        flash("未知反馈语言")
        return redirect(url_for("main.settings"))
    words_svc.set_learning_languages(current_user.id, codes)
    flash("已保存语言设置")
    return redirect(url_for("main.settings"))
