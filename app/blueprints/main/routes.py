"""首页 = 当天主词卡（第一性原理：来背词，第一眼暴露词）。

仪表盘大字「待复习数」不进首页（看数字去 /stats）；首页就是复习页本身。
独立 /review 作日常入口已砍（语义并入首页），grade 端点 words.grade 保留不动。
"""
from flask import Blueprint, render_template
from flask_login import login_required, current_user

from app.services import words as words_svc

bp = Blueprint("main", __name__)


@bp.route("/")
@login_required
def index():
    due = words_svc.get_due_words(current_user.id, limit=1)
    word = due[0] if due else None
    # 主词卡复用 review/_card.html（同一片段含 hx 三按钮打 words.grade）。
    # 首页统计仍传 stats（页内小字概览），但主区域是词卡不是大字仪表盘。
    return render_template("main/index.html", user=current_user,
                           word=word, stats=words_svc.get_stats(current_user.id))