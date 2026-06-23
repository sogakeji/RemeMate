"""首页：今日复习入口 + 概览。"""
from flask import Blueprint, render_template
from flask_login import login_required, current_user

from app.services import words as words_svc

bp = Blueprint("main", __name__)


@bp.route("/")
@login_required
def index():
    return render_template("main/index.html", user=current_user,
                           stats=words_svc.get_stats(current_user.id))
