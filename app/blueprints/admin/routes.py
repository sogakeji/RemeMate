"""管理员闭测运营页：邀请账号创建与账号概览。"""
from functools import wraps

from flask import abort, flash, redirect, render_template, request, url_for
from flask_login import current_user, login_required

from app.models.user import User
from app.services import provisioning


from . import bp


def admin_required(view):
    @wraps(view)
    @login_required
    def wrapped(*args, **kwargs):
        if current_user.role != "admin":
            abort(403)
        return view(*args, **kwargs)
    return wrapped


@bp.route("/", methods=["GET", "POST"])
@admin_required
def index():
    created = None
    if request.method == "POST":
        email = request.form.get("email", "").strip()
        name = request.form.get("name", "").strip()
        password = (request.form.get("password") or "").strip() or None
        if not email or not name:
            flash("邮箱和昵称必填")
            return redirect(url_for("admin.index"))
        try:
            uid, password = provisioning.create_user_with_defaults(
                email, name, password=password,
            )
        except provisioning.UserExistsError:
            flash("邮箱已存在")
            return redirect(url_for("admin.index"))
        except ValueError as e:
            flash(str(e))
            return redirect(url_for("admin.index"))
        created = {
            "id": uid,
            "email": provisioning.normalize_email(email),
            "password": password,
        }

    users = (User.query
             .order_by(User.created_at.desc(), User.id.desc())
             .limit(20)
             .all())
    return render_template(
        "admin/index.html",
        created=created,
        users=users,
    )
