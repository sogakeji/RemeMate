"""登录 / 登出。

安全要点（见 docs/arch/auth-flow.md）：
- 失败不区分「用户不存在」与「密码错误」（防枚举）。
- 连续失败 5 次锁定 15 分钟（locked_until）。
- next 必须是同域相对路径（防开放重定向）。
- CSRF 由 Flask-WTF 的 FlaskForm 自动校验。
"""
from datetime import timedelta
from urllib.parse import urlsplit

from flask import (Blueprint, abort, current_app, render_template, redirect,
                   url_for, request, flash)
from flask_login import login_user, logout_user, login_required, current_user
from werkzeug.security import check_password_hash, generate_password_hash

from app.extensions import db
from app.i18n import translate as _
from app.models.user import User
from app.blueprints.auth.forms import (
    ForgotPasswordForm,
    LoginForm,
    PasswordResetForm,
    PasswordSetupForm,
    RegisterForm,
)
from app.services.account_access import (
    InitialPasswordUnavailableError,
    InvalidChallengeError,
    PasswordPolicyError,
    request_password_reset,
    request_registration,
    reset_password,
    set_initial_password,
    verify_registration,
)
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


@bp.route("/register", methods=["GET", "POST"])
def register():
    if not current_app.config["OPEN_REGISTRATION_ENABLED"]:
        abort(404)

    form = RegisterForm()
    if form.validate_on_submit():
        request_registration(form.email.data, request.remote_addr or "")
        flash(_("auth.registration.request_received"))
        return redirect(url_for("auth.login"), code=303)

    return render_template("auth/register.html", form=form)


@bp.route("/forgot-password", methods=["GET", "POST"])
def forgot_password():
    form = ForgotPasswordForm()
    if form.validate_on_submit():
        request_password_reset(form.email.data, request.remote_addr or "")
        flash(_("auth.password_reset.request_received"))
        return redirect(url_for("auth.login"), code=303)
    return render_template("auth/forgot_password.html", form=form)


@bp.route("/reset-password/<token>", methods=["GET", "POST"])
def reset_password_route(token):
    form = PasswordResetForm()
    if form.validate_on_submit():
        try:
            user_id = reset_password(token, form.password.data)
        except PasswordPolicyError:
            form.password.errors.append(_("auth.password_reset.too_short"))
            return render_template("auth/reset_password.html", form=form)
        except InvalidChallengeError:
            flash(_("auth.password_reset.invalid_token"))
            return redirect(url_for("auth.login"), code=303)

        user = db.session.get(User, user_id)
        if user is None:
            flash(_("auth.password_reset.invalid_token"))
            return redirect(url_for("auth.login"), code=303)
        if not current_user.is_authenticated or current_user.id == user_id:
            login_user(user)
        flash(_("auth.password_reset.saved"))
        return redirect(url_for("main.index"), code=303)

    return render_template("auth/reset_password.html", form=form)


@bp.get("/verify-email/<token>")
def verify_email(token):
    if current_user.is_authenticated:
        flash(_("auth.registration.logout_first"))
        return redirect(url_for("main.index"), code=303)

    try:
        account = verify_registration(token)
    except InvalidChallengeError:
        flash(_("auth.registration.invalid_token"))
        return redirect(url_for("auth.login"), code=303)

    user = db.session.get(User, account.user_id)
    if user is None:
        flash(_("auth.registration.invalid_token"))
        return redirect(url_for("auth.login"), code=303)
    login_user(user)
    flash(_("auth.registration.verified"))
    return redirect(url_for("auth.set_password"), code=303)


@bp.route("/set-password", methods=["GET", "POST"])
@login_required
def set_password():
    form = PasswordSetupForm()
    if form.validate_on_submit():
        try:
            set_initial_password(current_user.id, form.password.data)
        except PasswordPolicyError:
            form.password.errors.append(_("auth.password_setup.too_short"))
            return render_template("auth/set_password.html", form=form)
        except InitialPasswordUnavailableError:
            flash(_("auth.password_setup.unavailable"))
            return redirect(url_for("auth.set_password"), code=303)
        flash(_("auth.password_setup.saved"))
        return redirect(url_for("main.index"), code=303)

    return render_template("auth/set_password.html", form=form)


@bp.route("/logout")
@login_required
def logout():
    logout_user()
    return redirect(url_for("auth.login"))
