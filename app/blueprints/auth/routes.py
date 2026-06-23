"""登录 / 登出。

安全要点（见 docs/arch/auth-flow.md）：
- 失败不区分「用户不存在」与「密码错误」（防枚举）。
- 连续失败 5 次锁定 15 分钟（locked_until）。
- next 必须是同域相对路径（防开放重定向）。
- CSRF 由 Flask-WTF 的 FlaskForm 自动校验。
"""
from datetime import datetime, timedelta
from urllib.parse import urlparse

from flask import Blueprint, render_template, redirect, url_for, request, flash
from flask_login import login_user, logout_user, login_required, current_user
from werkzeug.security import check_password_hash

from app.extensions import db
from app.models.user import User
from app.blueprints.auth.forms import LoginForm

bp = Blueprint("auth", __name__)

MAX_ATTEMPTS = 5
LOCK_MINUTES = 15
_GENERIC_ERROR = "邮箱或密码错误"


def _is_safe_next(target: str) -> bool:
    if not target:
        return False
    u = urlparse(target)
    return not u.scheme and not u.netloc and target.startswith("/")


@bp.route("/login", methods=["GET", "POST"])
def login():
    if current_user.is_authenticated:
        return redirect(url_for("main.index"))

    form = LoginForm()
    if form.validate_on_submit():
        user = User.query.filter_by(email=form.email.data, is_active=True).first()

        # 锁定中：统一提示，不泄露账号是否存在
        if user and user.locked_until and user.locked_until > datetime.utcnow():
            flash("账号已锁定，请稍后再试")
            return render_template("auth/login.html", form=form)

        if user and check_password_hash(user.password_hash, form.password.data):
            user.login_attempts = 0
            user.locked_until = None
            db.session.commit()
            login_user(user)
            nxt = request.args.get("next")
            return redirect(nxt if _is_safe_next(nxt) else url_for("main.index"))

        # 失败：存在的账号累计失败数；不存在的不泄露
        if user:
            user.login_attempts = (user.login_attempts or 0) + 1
            if user.login_attempts >= MAX_ATTEMPTS:
                user.locked_until = datetime.utcnow() + timedelta(minutes=LOCK_MINUTES)
                user.login_attempts = 0
            db.session.commit()
        flash(_GENERIC_ERROR)

    return render_template("auth/login.html", form=form)


@bp.route("/logout")
@login_required
def logout():
    logout_user()
    return redirect(url_for("auth.login"))
