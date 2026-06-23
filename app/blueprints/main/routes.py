"""首页占位（阶段三扩展为 SRS 看板）。"""
from flask import Blueprint, render_template
from flask_login import login_required, current_user

bp = Blueprint("main", __name__)


@bp.route("/")
@login_required
def index():
    return render_template("main/index.html", user=current_user)
