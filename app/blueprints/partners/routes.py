"""Private language-partner pages."""
from flask import Blueprint, abort, flash, redirect, render_template, request, url_for
from flask_login import current_user, login_required

from app.services import partners as partners_svc
from app.services.words import _LANGUAGE_NAMES


bp = Blueprint("partners", __name__)


def _uid() -> int:
    return current_user.id


def _form_values() -> dict:
    return {
        "display_name": request.form.get("display_name", ""),
        "native_language_code": request.form.get("native_language_code", ""),
        "learning_language_code": request.form.get(
            "learning_language_code", ""),
        "private_note": request.form.get("private_note", ""),
    }


@bp.get("/partners")
@login_required
def index():
    return render_template(
        "partners/index.html",
        partners=partners_svc.list_partners(_uid()),
        language_names=_LANGUAGE_NAMES,
    )


@bp.get("/partners/new")
@login_required
def new():
    return render_template(
        "partners/form.html", partner=None, language_names=_LANGUAGE_NAMES,
    )


@bp.post("/partners")
@login_required
def create():
    values = _form_values()
    try:
        partner = partners_svc.create_partner(_uid(), **values)
    except ValueError as exc:
        flash(str(exc))
        return render_template(
            "partners/form.html", partner=None, form_values=values,
            language_names=_LANGUAGE_NAMES,
        ), 400
    flash("已添加语言伙伴")
    return redirect(url_for("partners.show", partner_id=partner.id))


@bp.get("/partners/<int:partner_id>")
@login_required
def show(partner_id):
    partner = partners_svc.get_partner(_uid(), partner_id)
    if partner is None:
        abort(404)
    return render_template(
        "partners/detail.html", partner=partner,
        language_names=_LANGUAGE_NAMES,
    )


@bp.get("/partners/<int:partner_id>/edit")
@login_required
def edit(partner_id):
    partner = partners_svc.get_partner(_uid(), partner_id)
    if partner is None:
        abort(404)
    return render_template(
        "partners/form.html", partner=partner, language_names=_LANGUAGE_NAMES,
    )


@bp.post("/partners/<int:partner_id>")
@login_required
def update(partner_id):
    values = _form_values()
    try:
        partner = partners_svc.update_partner(_uid(), partner_id, **values)
    except ValueError as exc:
        partner = partners_svc.get_partner(_uid(), partner_id)
        if partner is None:
            abort(404)
        flash(str(exc))
        return render_template(
            "partners/form.html", partner=partner, form_values=values,
            language_names=_LANGUAGE_NAMES,
        ), 400
    if partner is None:
        abort(404)
    flash("已更新语言伙伴")
    return redirect(url_for("partners.show", partner_id=partner.id))
