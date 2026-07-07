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
from werkzeug.security import check_password_hash, generate_password_hash

from app.extensions import db
from app.services import words as words_svc
from app.services import tasks as tasks_svc

bp = Blueprint("main", __name__)


def _safe_next_target(target: str) -> str | None:
    if not target:
        return None
    normalized = target.replace("\\", "/")
    parts = urlsplit(normalized)
    if parts.scheme or parts.netloc:
        if parts.netloc != request.host:
            return None
        path = parts.path or "/"
        if not path.startswith("/"):
            return None
        return path + (f"?{parts.query}" if parts.query else "")
    if not normalized.startswith("/") or normalized.startswith("//"):
        return None
    return normalized


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
                           stats=words_svc.get_stats(current_user.id),
                           task_card=tasks_svc.get_today_task_card(current_user.id))


@bp.post("/language/switch")
@login_required
def switch_language():
    """全局语言切换器：切当前语言后留在当前页面。"""
    code = request.form.get("language_code", "").strip()
    nxt = (_safe_next_target(request.form.get("next"))
           or _safe_next_target(request.referrer)
           or url_for("main.index"))
    if code not in words_svc._LANGUAGE_NAMES:
        flash("未知语言")
        return redirect(nxt)
    words_svc.set_current_language(current_user.id, code)
    return redirect(nxt)


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
                           feedback_choices=words_svc._FEEDBACK_LANGUAGE_NAMES,
                           timezone=words_svc.get_timezone(current_user.id),
                           timezone_choices=words_svc._TIMEZONE_CHOICES,
                           notification_settings=words_svc.get_notification_settings(
                               current_user.id))


def _save_settings_from_form():
    codes = request.form.getlist("languages")
    feedback_language = request.form.get("feedback_language", "zh").strip()
    timezone_form_present = "timezone" in request.form
    notification_form_present = "bark_url" in request.form
    words_svc.set_feedback_language(current_user.id, feedback_language)
    if timezone_form_present:
        words_svc.set_timezone(current_user.id,
                               request.form.get("timezone", "").strip())
    if notification_form_present:
        words_svc.set_notification_settings(
            current_user.id,
            request.form.get("bark_url", ""),
            notify_review_reminder=(
                request.form.get("notify_review_reminder") == "on"),
            notify_daily_summary=(
                request.form.get("notify_daily_summary") == "on"),
            notify_intake_done=(
                request.form.get("notify_intake_done") == "on"),
        )
    words_svc.set_learning_languages(current_user.id, codes)


@bp.post("/settings")
@login_required
def save_settings():
    try:
        _save_settings_from_form()
    except ValueError:
        flash("设置内容不正确，请检查后再保存")
        return redirect(url_for("main.settings"))
    flash("已保存设置")
    return redirect(url_for("main.settings"))


@bp.post("/settings/account")
@login_required
def save_account_settings():
    display_name = (request.form.get("display_name") or "").strip()
    current_password = request.form.get("current_password") or ""
    new_password = request.form.get("new_password") or ""
    confirm_password = request.form.get("confirm_password") or ""
    changing_password = any([current_password, new_password, confirm_password])

    if not display_name or len(display_name) > 100:
        flash("昵称需为 1-100 个字符")
        return redirect(url_for("main.settings"))
    current_user.display_name = display_name

    if changing_password:
        if not check_password_hash(current_user.password_hash, current_password):
            flash("当前密码不正确")
            return redirect(url_for("main.settings"))
        if len(new_password) < 8 or len(new_password) > 128:
            flash("新密码需为 8-128 个字符")
            return redirect(url_for("main.settings"))
        if new_password != confirm_password:
            flash("两次输入的新密码不一致")
            return redirect(url_for("main.settings"))
        current_user.password_hash = generate_password_hash(new_password)
        current_user.login_attempts = 0
        current_user.locked_until = None

    db.session.commit()
    flash("已保存账号设置")
    return redirect(url_for("main.settings"))


@bp.post("/settings/bark/test")
@login_required
def test_bark_settings():
    try:
        _save_settings_from_form()
        words_svc.send_bark_test_notification(current_user.id)
    except ValueError as exc:
        flash(str(exc) or "Bark 测试推送发送失败")
        return redirect(url_for("main.settings"))
    flash("Bark 测试推送已发送")
    return redirect(url_for("main.settings"))
