"""Private language-partner and SessionPad recap pages."""
from datetime import datetime
from zoneinfo import ZoneInfo

from flask import Blueprint, abort, flash, redirect, render_template, request, url_for
from flask_login import current_user, login_required

from app.services import partners as partners_svc
from app.services import recaps as recaps_svc
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


def _recap_side(value: str | None = None) -> str:
    side = (value or request.args.get("side") or "for_me").strip()
    return side if side in recaps_svc.ITEM_CHOICES else "for_me"


def _recap_kind(side: str, value: str | None = None) -> str:
    choices = recaps_svc.ITEM_CHOICE_LABELS[side]
    kind = (value or request.args.get("kind") or "").strip()
    return kind if kind in choices else next(iter(choices))


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
        recaps=recaps_svc.list_recaps(_uid(), partner_id),
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


@bp.get("/partners/<int:partner_id>/recaps/new")
@login_required
def new_recap(partner_id):
    partner = partners_svc.get_partner(_uid(), partner_id)
    if partner is None:
        abort(404)
    return render_template(
        "partners/recap_form.html", partner=partner,
        default_date=datetime.now(
            ZoneInfo(current_user.timezone or "Asia/Shanghai")
        ).date().isoformat(),
    )


@bp.post("/partners/<int:partner_id>/recaps")
@login_required
def create_recap(partner_id):
    values = {
        "session_date": request.form.get("session_date", ""),
        "title": request.form.get("title", ""),
    }
    try:
        recap = recaps_svc.create_recap(_uid(), partner_id, **values)
    except ValueError as exc:
        partner = partners_svc.get_partner(_uid(), partner_id)
        if partner is None:
            abort(404)
        flash(str(exc))
        return render_template(
            "partners/recap_form.html", partner=partner,
            form_values=values, default_date=values["session_date"],
        ), 400
    if recap is None:
        abort(404)
    flash("已创建复盘信纸")
    return redirect(url_for(
        "partners.show_recap", partner_id=partner_id, recap_id=recap.id,
    ))


@bp.get("/partners/<int:partner_id>/recaps/<int:recap_id>")
@login_required
def show_recap(partner_id, recap_id):
    partner = partners_svc.get_partner(_uid(), partner_id)
    recap = recaps_svc.get_recap(_uid(), partner_id, recap_id)
    items = recaps_svc.list_items(_uid(), partner_id, recap_id)
    if partner is None or recap is None or items is None:
        abort(404)
    active_side = _recap_side()
    return render_template(
        "partners/recap_detail.html", partner=partner, recap=recap,
        items=items, item_choices=recaps_svc.ITEM_CHOICES,
        item_choice_labels=recaps_svc.ITEM_CHOICE_LABELS,
        item_labels=recaps_svc.ITEM_LABELS,
        item_prompts=recaps_svc.ITEM_PROMPTS,
        candidate_kinds=recaps_svc.CANDIDATE_KINDS,
        candidate_source_ids=recaps_svc.candidate_source_ids(_uid(), items),
        active_side=active_side,
        active_kind=_recap_kind(active_side),
    )


@bp.post("/partners/<int:partner_id>/recaps/<int:recap_id>/items")
@login_required
def add_recap_item(partner_id, recap_id):
    try:
        item = recaps_svc.add_item(
            _uid(), partner_id, recap_id,
            side=request.form.get("side", ""),
            kind=request.form.get("kind", ""),
            content=request.form.get("content", ""),
        )
    except ValueError as exc:
        flash(str(exc))
        return redirect(url_for(
            "partners.show_recap", partner_id=partner_id, recap_id=recap_id,
            side=_recap_side(request.form.get("side")),
        ))
    if item is None:
        abort(404)
    return redirect(url_for(
        "partners.show_recap", partner_id=partner_id, recap_id=recap_id,
        side=item.side, kind=item.kind,
    ))


@bp.post(
    "/partners/<int:partner_id>/recaps/<int:recap_id>/items/<int:item_id>",
)
@login_required
def update_recap_item(partner_id, recap_id, item_id):
    try:
        item = recaps_svc.update_item(
            _uid(), partner_id, recap_id, item_id,
            kind=request.form.get("kind", ""),
            content=request.form.get("content", ""),
        )
    except ValueError as exc:
        flash(str(exc))
        return redirect(url_for(
            "partners.show_recap", partner_id=partner_id, recap_id=recap_id,
            side=_recap_side(request.form.get("side")),
        ))
    if item is None:
        abort(404)
    return redirect(url_for(
        "partners.show_recap", partner_id=partner_id, recap_id=recap_id,
        side=item.side, kind=item.kind,
    ))


@bp.post(
    "/partners/<int:partner_id>/recaps/<int:recap_id>/items/"
    "<int:item_id>/add-candidate",
)
@login_required
def add_recap_item_candidate(partner_id, recap_id, item_id):
    try:
        result = recaps_svc.add_item_to_candidates(
            _uid(), partner_id, recap_id, item_id,
        )
    except ValueError as exc:
        flash(str(exc))
        return redirect(url_for(
            "partners.show_recap",
            partner_id=partner_id,
            recap_id=recap_id,
            side="for_me",
        ))
    if result is None:
        abort(404)
    if result["state"] == "existing-word":
        flash("这条内容已经在生词本中")
        return redirect(url_for(
            "partners.show_recap",
            partner_id=partner_id,
            recap_id=recap_id,
            side="for_me",
        ))
    if result["state"] == "created":
        flash("已加入候选词，请确认后入库")
    return redirect(url_for(
        "intake.candidates", source_id=result["source_id"],
    ))


@bp.post(
    "/partners/<int:partner_id>/recaps/<int:recap_id>/items/"
    "<int:item_id>/delete",
)
@login_required
def delete_recap_item(partner_id, recap_id, item_id):
    location = recaps_svc.delete_item(_uid(), partner_id, recap_id, item_id)
    if location is None:
        abort(404)
    side, kind = location
    return redirect(url_for(
        "partners.show_recap", partner_id=partner_id, recap_id=recap_id,
        side=side, kind=kind,
    ))
