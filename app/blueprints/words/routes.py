"""词库管理 + SRS 复习 + 统计。

路由只取参数、调 service、渲染；业务逻辑在 services/words.py（见模块边界规则）。
"""
from flask import (Blueprint, render_template, redirect, url_for, request,
                   flash, abort)
from flask_login import login_required, current_user

from app.services import words as words_svc
from app.blueprints.words.forms import NewListForm, AddWordForm

bp = Blueprint("words", __name__)


def _uid():
    return current_user.id


@bp.route("/words", methods=["GET", "POST"])
@login_required
def lists():
    form = NewListForm()
    if form.validate_on_submit():
        words_svc.create_word_list(_uid(), form.name.data, form.language_code.data)
        flash("词表已创建")
        return redirect(url_for("words.lists"))
    return render_template("words/list.html",
                           lists=words_svc.get_word_lists(_uid()), form=form)


@bp.route("/words/<int:list_id>", methods=["GET", "POST"])
@login_required
def detail(list_id):
    wl = words_svc.get_word_list(_uid(), list_id, eager=True)
    if wl is None:
        abort(404)
    form = AddWordForm()
    if form.validate_on_submit():
        words_svc.add_word(
            _uid(), list_id, form.word.data,
            meaning=form.meaning.data, part_of_speech=form.part_of_speech.data,
            example=form.example.data, note=form.note.data,
        )
        flash("已加词")
        return redirect(url_for("words.detail", list_id=list_id))
    return render_template("words/detail.html", wl=wl, form=form)


@bp.route("/words/<int:list_id>/delete", methods=["POST"])
@login_required
def delete(list_id):
    if not words_svc.delete_word_list(_uid(), list_id):
        abort(404)
    flash("词表已删除")
    return redirect(url_for("words.lists"))


@bp.route("/review")
@login_required
def review():
    due = words_svc.get_due_words(_uid(), limit=1)
    return render_template("review/review.html", word=due[0] if due else None)


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
    nxt = words_svc.get_due_words(_uid(), limit=1)
    # HTMX：返回下一张卡片片段（无则完成提示）
    return render_template("review/_card.html", word=nxt[0] if nxt else None)


@bp.route("/stats")
@login_required
def stats():
    return render_template("words/stats.html", stats=words_svc.get_stats(_uid()))
