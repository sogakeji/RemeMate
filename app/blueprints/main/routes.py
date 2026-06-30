"""首页 = 当天主词卡（第一性原理：来背词，第一眼暴露词）+ 设置最小版。

- 首页就是复习页本身（仪表盘大字不进首页；独立 /review 作日常入口已砍）。
- 当前语言决定首页刷哪个语言的词、切换器在首页切换它；未设语言时空态引导去设置。
- /settings 最小版只做「正在学哪种语言」选择（= set_current_language 闭环建词表）。
  Bark/播客/per-user key 等阶段八再补。
"""
from flask import (Blueprint, render_template, redirect, url_for, flash,
                   request)
from flask_login import login_required, current_user

from app.services import words as words_svc
from app.blueprints.words.forms import LanguageChoiceForm

bp = Blueprint("main", __name__)


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
                           stats=words_svc.get_stats(current_user.id))


@bp.post("/language/switch")
@login_required
def switch_language():
    """首页语言切换器：切当前语言（set_current_language 闭环建词表）。"""
    code = request.form.get("language_code", "").strip()
    if code not in words_svc._LANGUAGE_NAMES:
        flash("未知语言")
        return redirect(url_for("main.index"))
    words_svc.set_current_language(current_user.id, code)
    return redirect(url_for("main.index"))


@bp.get("/settings")
@login_required
def settings():
    form = LanguageChoiceForm()
    form.language_code.data = words_svc.get_current_language(current_user.id) or "fr"
    return render_template("main/settings.html", form=form,
                           lang_choices=words_svc._LANGUAGE_NAMES)


@bp.post("/settings")
@login_required
def save_settings():
    form = LanguageChoiceForm()
    if form.validate_on_submit():
        words_svc.set_current_language(current_user.id, form.language_code.data)
        flash("已设当前语言")
    return redirect(url_for("main.settings"))