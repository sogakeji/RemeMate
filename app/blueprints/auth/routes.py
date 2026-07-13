"""登录 / 登出。

安全要点（见 docs/arch/auth-flow.md）：
- 失败不区分「用户不存在」与「密码错误」（防枚举）。
- 连续失败 5 次锁定 15 分钟（locked_until）。
- next 必须是同域相对路径（防开放重定向）。
- CSRF 由 Flask-WTF 的 FlaskForm 自动校验。
"""
from datetime import timedelta
from urllib.parse import urlsplit

from flask import Blueprint, render_template, redirect, url_for, request, flash
from flask_login import login_user, logout_user, login_required, current_user
from werkzeug.security import check_password_hash, generate_password_hash

from app.extensions import db
from app.i18n import translate as _
from app.models.user import User
from app.blueprints.auth.forms import LoginForm
from app.services.timeutil import utc_now

bp = Blueprint("auth", __name__)

MAX_ATTEMPTS = 5
LOCK_MINUTES = 15
# 固定 dummy hash：user 不存在时也跑一次哈希校验，抹平计时侧信道（防枚举）。
_DUMMY_HASH = generate_password_hash("rememate-timing-dummy")


def _is_safe_next(target: str) -> bool:
    # 只放行同域相对路径（M4）。Werkzeug 3 已移除 url_has_allowed_host_and_scheme，
    # 这里手写：先把反斜杠归一为斜杠（部分浏览器会这么规范化），再拒绝 // 和任何
    # scheme/netloc，挡掉 /\evil.com、//evil.com、http://evil 这类开放重定向绕过。
    if not target:
        return False
    normalized = target.replace("\\", "/")
    if not normalized.startswith("/") or normalized.startswith("//"):
        return False
    parts = urlsplit(normalized)
    return not parts.scheme and not parts.netloc


@bp.route("/login", methods=["GET", "POST"])
def login():
    if current_user.is_authenticated:
        return redirect(url_for("main.index"))

    form = LoginForm()
    if form.validate_on_submit():
        email = (form.email.data or "").strip().lower()      # 大小写无关（M5）
        user = User.query.filter_by(email=email, is_active=True).first()

        locked = bool(user and user.locked_until
                      and user.locked_until > utc_now())

        # 始终跑一次哈希校验（user 为 None 时校验 dummy），消除「存在与否」的计时差。
        pw_ok = check_password_hash(
            user.password_hash if user else _DUMMY_HASH,
            form.password.data,
        )

        if user and pw_ok and not locked:
            user.login_attempts = 0
            user.locked_until = None
            db.session.commit()
            login_user(user)
            nxt = request.args.get("next")
            return redirect(nxt if _is_safe_next(nxt) else url_for("main.index"))

        # 所有失败（不存在 / 密码错 / 锁定中）一律通用消息，不泄露账号状态。
        # 仅对「存在且未锁」的账号累计失败数并触发锁定。
        if user and not locked:
            user.login_attempts = (user.login_attempts or 0) + 1
            if user.login_attempts >= MAX_ATTEMPTS:
                user.locked_until = utc_now() + timedelta(minutes=LOCK_MINUTES)
                user.login_attempts = 0
            db.session.commit()
        flash(_("login.error"))

    return render_template("auth/login.html", form=form)


@bp.route("/logout")
@login_required
def logout():
    logout_user()
    return redirect(url_for("auth.login"))
