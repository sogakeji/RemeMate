"""Private language-partner and SessionPad recap pages."""
from datetime import datetime
from zoneinfo import ZoneInfo

from flask import (
    Blueprint, abort, current_app, flash, redirect, render_template, request,
    url_for,
)
from flask_login import current_user, login_required
from sqlalchemy import create_engine

from app.i18n import localized_language_names, translate as _
from app.services import partners as partners_svc
from app.services import partner_invites as invites_svc
from app.services import packets as packets_svc
from app.services import recap_summaries as summaries_svc
from app.services import recaps as recaps_svc
from app.services import words as words_svc
from app.services.words import _LANGUAGE_NAMES


bp = Blueprint("partners", __name__)


def _uid() -> int:
    return current_user.id


def _item_labels():
    return {
        kind: _(f"recap.kind.{kind}")
        for kind in recaps_svc.ITEM_LABELS
    }


def _item_choices():
    return {
        "for_me": (
            ("expression", _("recap.kind.expression")),
            ("natural_phrase", _("recap.kind.for_me.natural_phrase")),
            ("private_note", _("recap.kind.private_note")),
            ("next_time", _("recap.kind.for_me.next_time")),
        ),
        "for_partner": (
            ("expression", _("recap.kind.expression")),
            ("correction", _("recap.kind.correction")),
            ("natural_phrase", _("recap.kind.for_partner.natural_phrase")),
            ("next_time", _("recap.kind.for_partner.next_time")),
        ),
    }


def _item_prompts():
    return {
        side: {
            kind: _(f"recap.prompt.{side}.{kind}")
            for kind, _label in choices
        }
        for side, choices in _item_choices().items()
    }


def _service_error(exc: ValueError) -> str:
    message = str(exc)
    exact = {
        "伙伴昵称需为 1-100 个字符": "partner.error.invalid_name",
        "私人备注不能超过 2000 个字符": "partner.error.note_too_long",
        "不支持该语言": "partner.error.unsupported_language",
        "请输入有效的对方登录邮箱": "partner.error.invalid_email",
        "不能绑定自己的账号": "partner.error.self_link",
        "复盘标题不能超过 120 个字符": "recap.error.title_too_long",
        "请先为伙伴设置母语": "recap.error.need_native",
        "这类记录不能加入候选词": "recap.error.kind_not_adoptable",
        "加入候选词的内容不能超过 200 个字符": "recap.error.candidate_too_long",
        "记录类型不正确": "recap.error.invalid_type",
        "记录内容需为 1-2000 个字符": "recap.error.invalid_content",
        "请选择有效的交换日期": "recap.error.invalid_date",
        "请先记录至少一条可总结的学习内容": "recap.error.empty_summary",
        "复盘内容较多，请先整理后再生成总结": "recap.error.summary_too_long",
        "请先邀请伙伴绑定账号": "packet.error.link_first",
        "请先为伙伴设置正在学的语言": "packet.error.learning_first",
        "只能发送当前复盘中帮他记的内容": "packet.error.invalid_selection",
        "这份旧反馈没有语言信息，暂时不能加入候选词": "packet.error.old_no_language",
        "这份旧反馈没有语言信息，暂时不能提取词语": "packet.error.old_no_language_extract",
        "每个候选词需为 1-200 个字符": "packet.error.term_length",
        "请至少填写一个候选词或表达": "packet.error.term_required",
        "一次最多加入 20 个候选词": "packet.error.term_limit",
        "这类反馈不能加入候选词": "packet.error.kind_not_adoptable",
        "选择的反馈内容不正确": "packet.error.invalid_items",
        "请至少选择一条帮他记的内容": "packet.error.select_one",
        "一次最多发送 20 条内容": "packet.error.send_limit",
    }
    if message in exact:
        return _(exact[message])
    prefix = "请先在设置中把"
    suffix = "加入正在学"
    if message.startswith(prefix) and message.endswith(suffix):
        raw_name = message[len(prefix):-len(suffix)]
        code = next(
            (code for code, name in _LANGUAGE_NAMES.items() if name == raw_name),
            None,
        )
        language = localized_language_names().get(code, raw_name)
        return _("recap.error.add_learning", language=language)
    return message


def _dispatch_engine():
    dispatch_url = current_app.config.get("DISPATCH_DATABASE_URL")
    if not dispatch_url:
        raise RuntimeError("DISPATCH_DATABASE_URL missing")
    return create_engine(dispatch_url, pool_pre_ping=True)


def _render_partner_detail(partner):
    recaps = recaps_svc.list_recaps(_uid(), partner.id)
    return render_template(
        "partners/detail.html",
        partner=partner,
        recaps=recaps,
        recap_delivery_statuses=packets_svc.recap_delivery_statuses(
            _uid(), [recap.id for recap in recaps],
        ),
        delivery_labels={
            "pending": _("packet.delivery.pending"),
            "thanked": _("packet.delivery.thanked"),
        },
        language_names=localized_language_names(),
    )


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


def _render_packet_adopt_form(
    packet_id: int,
    item,
    *,
    terms: str,
    suggestion_message: str,
):
    return render_template(
        "partners/_packet_adopt_form.html",
        packet_id=packet_id,
        item=item,
        source_id=packets_svc.adoption_source_ids(_uid(), [item]).get(item.id),
        terms=terms,
        suggestion_message=suggestion_message,
        form_open=True,
    )


@bp.get("/partners")
@login_required
def index():
    return render_template(
        "partners/index.html",
        partners=partners_svc.list_partners(_uid()),
        language_names=localized_language_names(),
    )


@bp.get("/partners/new")
@login_required
def new():
    return render_template(
        "partners/form.html", partner=None,
        language_names=localized_language_names(),
    )


@bp.post("/partners")
@login_required
def create():
    values = _form_values()
    try:
        partner = partners_svc.create_partner(_uid(), **values)
    except ValueError as exc:
        flash(_service_error(exc))
        return render_template(
            "partners/form.html", partner=None, form_values=values,
            language_names=localized_language_names(),
        ), 400
    flash(_("partner.saved"))
    return redirect(url_for("partners.show", partner_id=partner.id))


@bp.get("/partners/<int:partner_id>")
@login_required
def show(partner_id):
    partner = partners_svc.get_partner(_uid(), partner_id)
    if partner is None:
        abort(404)
    return _render_partner_detail(partner)


@bp.post("/partners/<int:partner_id>/invite")
@login_required
def create_invite(partner_id):
    partner = partners_svc.get_partner(_uid(), partner_id)
    if partner is None:
        abort(404)
    if partner.linked_user_id is not None:
        flash(_("partner.already_bound"))
        return redirect(url_for("partners.show", partner_id=partner_id))

    try:
        email = invites_svc.normalize_recipient_email(
            request.form.get("recipient_email"),
        )
    except ValueError as exc:
        flash(_service_error(exc))
        return _render_partner_detail(partner), 400
    if email == current_user.email.strip().lower():
        flash(_("partner.invite_self"))
        return _render_partner_detail(partner), 400

    token = invites_svc.make_partner_invite_token(
        current_app.config["SECRET_KEY"], _uid(), partner_id, email,
    )
    if not partners_svc.set_pending_invite(
        _uid(), partner_id, invites_svc.partner_invite_token_hash(token),
    ):
        flash(_("partner.already_bound"))
        return redirect(url_for("partners.show", partner_id=partner_id))
    base_url = current_app.config.get("PUBLIC_BASE_URL") or request.host_url
    invite_url = invites_svc.partner_invite_url(base_url, token)
    return render_template(
        "partners/invite_created.html",
        partner=partner,
        invite_url=invite_url,
    )


@bp.route("/partners/invitations/<token>", methods=["GET", "POST"])
@login_required
def invitation(token):
    engine = _dispatch_engine()
    try:
        if request.method == "POST":
            try:
                with engine.begin() as conn:
                    result = invites_svc.accept_partner_invite(
                        conn,
                        current_app.config["SECRET_KEY"],
                        token,
                        _uid(),
                        current_user.email,
                    )
            except ValueError as exc:
                return render_template(
                    "partners/invitation.html", error=_service_error(exc),
                ), 400
            if result is None:
                return render_template(
                    "partners/invitation.html", unavailable=True,
                ), 410
            return redirect(url_for(
                "partners.confirm_reciprocal",
                owner_user_id=result.owner_user_id,
            ))

        with engine.begin() as conn:
            preview = invites_svc.preview_partner_invite(
                conn,
                current_app.config["SECRET_KEY"],
                token,
                current_user.email,
            )
    finally:
        engine.dispose()
    if preview is None:
        return render_template(
            "partners/invitation.html", unavailable=True,
        ), 410
    return render_template(
        "partners/invitation.html", invite=preview, token=token,
    )


@bp.route(
    "/partners/reciprocal/<int:owner_user_id>", methods=["GET", "POST"],
)
@login_required
def confirm_reciprocal(owner_user_id):
    engine = _dispatch_engine()
    try:
        with engine.begin() as conn:
            if request.method == "POST":
                result = invites_svc.create_reciprocal_partner(
                    conn, _uid(), owner_user_id,
                )
                if result is None:
                    abort(404)
            else:
                preview = invites_svc.preview_reciprocal_partner(
                    conn, _uid(), owner_user_id,
                )
                if preview is None:
                    abort(404)
    finally:
        engine.dispose()

    if request.method == "POST":
        flash(
            _("partner.reciprocal_added")
            if result.state == "created"
            else _("partner.reciprocal_existing")
        )
        return redirect(url_for(
            "partners.show", partner_id=result.partner_id,
        ))
    return render_template(
        "partners/reciprocal_confirm.html",
        reciprocal=preview,
        language_names=localized_language_names(),
    )


@bp.get("/partners/<int:partner_id>/edit")
@login_required
def edit(partner_id):
    partner = partners_svc.get_partner(_uid(), partner_id)
    if partner is None:
        abort(404)
    return render_template(
        "partners/form.html", partner=partner,
        language_names=localized_language_names(),
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
        flash(_service_error(exc))
        return render_template(
            "partners/form.html", partner=partner, form_values=values,
            language_names=localized_language_names(),
        ), 400
    if partner is None:
        abort(404)
    flash(_("partner.updated"))
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
        flash(_service_error(exc))
        return render_template(
            "partners/recap_form.html", partner=partner,
            form_values=values, default_date=values["session_date"],
        ), 400
    if recap is None:
        abort(404)
    flash(_("recap.created"))
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
        items=items, item_choices=_item_choices(),
        item_choice_labels={
            side: dict(choices) for side, choices in _item_choices().items()
        },
        item_labels=_item_labels(),
        item_prompts=_item_prompts(),
        candidate_kinds=recaps_svc.CANDIDATE_KINDS,
        candidate_source_ids=recaps_svc.candidate_source_ids(_uid(), items),
        summary_state=summaries_svc.summary_state(recap, items),
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
        flash(_service_error(exc))
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
        flash(_service_error(exc))
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
        flash(_service_error(exc))
        return redirect(url_for(
            "partners.show_recap",
            partner_id=partner_id,
            recap_id=recap_id,
            side="for_me",
        ))
    if result is None:
        abort(404)
    if result["state"] == "existing-word":
        flash(_("recap.existing_word"))
        return redirect(url_for(
            "partners.show_recap",
            partner_id=partner_id,
            recap_id=recap_id,
            side="for_me",
        ))
    if result["state"] == "created":
        flash(_("recap.candidate_added"))
    return redirect(url_for(
        "intake.candidates", source_id=result["source_id"],
    ))


@bp.post(
    "/partners/<int:partner_id>/recaps/<int:recap_id>/summary",
)
@login_required
def generate_recap_summary(partner_id, recap_id):
    try:
        result = summaries_svc.generate_summary(
            _uid(), partner_id, recap_id,
            feedback_language_code=words_svc.get_feedback_language(_uid()),
        )
    except ValueError as exc:
        flash(_service_error(exc))
        return redirect(url_for(
            "partners.show_recap", partner_id=partner_id, recap_id=recap_id,
        ))
    except summaries_svc.SummaryUnavailable:
        flash(_("recap.summary_unavailable"))
        return redirect(url_for(
            "partners.show_recap", partner_id=partner_id, recap_id=recap_id,
        ))
    if result is None:
        abort(404)
    flash(
        _("recap.summary_generated")
        if result["state"] == "generated"
        else _("recap.summary_latest")
    )
    return redirect(url_for(
        "partners.show_recap", partner_id=partner_id, recap_id=recap_id,
    ))


@bp.post(
    "/partners/<int:partner_id>/recaps/<int:recap_id>/packets",
)
@login_required
def send_packet(partner_id, recap_id):
    try:
        result = packets_svc.create_packet(
            _uid(), partner_id, recap_id, request.form.getlist("item_ids"),
        )
    except ValueError as exc:
        flash(_service_error(exc))
        return redirect(url_for(
            "partners.show_recap",
            partner_id=partner_id,
            recap_id=recap_id,
            side="for_partner",
        ))
    if result is None:
        abort(404)
    if result["state"] == "created":
        flash(_("packet.sent_success"))
    else:
        flash(_("packet.sent_duplicate"))
    return redirect(url_for(
        "partners.show_packet", packet_id=result["packet"].id,
    ))


@bp.get("/partner-packets")
@login_required
def packet_inbox():
    return render_template(
        "partners/packet_inbox.html",
        packets=packets_svc.list_received_packets(_uid()),
    )


@bp.get("/partner-packets/<int:packet_id>")
@login_required
def show_packet(packet_id):
    packet = packets_svc.get_packet_for_user(_uid(), packet_id)
    if packet is None:
        abort(404)
    is_recipient = packet.recipient_user_id == _uid()
    return render_template(
        "partners/packet_detail.html",
        packet=packet,
        item_labels=_item_labels(),
        is_recipient=is_recipient,
        adoptable_kinds=packets_svc.ADOPTABLE_KINDS,
        adoption_source_ids=(
            packets_svc.adoption_source_ids(_uid(), packet.items)
            if is_recipient else {}
        ),
    )


@bp.post("/partner-packets/<int:packet_id>/thank")
@login_required
def thank_packet(packet_id):
    result = packets_svc.thank_packet(_uid(), packet_id)
    if result is None:
        abort(404)
    if result == "created":
        flash(_("packet.thank_sent"))
    return redirect(url_for("partners.show_packet", packet_id=packet_id))


@bp.post(
    "/partner-packets/<int:packet_id>/items/<int:item_id>/add-candidate",
)
@login_required
def adopt_packet_item(packet_id, item_id):
    try:
        result = packets_svc.add_received_item_to_candidates(
            _uid(), packet_id, item_id, request.form.get("terms", ""),
        )
    except ValueError as exc:
        flash(_service_error(exc))
        return redirect(url_for("partners.show_packet", packet_id=packet_id))
    if result is None:
        abort(404)
    if result["state"] == "existing-word":
        flash(_("packet.filled_existing"))
        return redirect(url_for("partners.show_packet", packet_id=packet_id))
    if result["created_count"]:
        message = _("packet.candidates_added", count=result["created_count"])
    else:
        message = _("packet.candidates_existing")
    if result["existing_word_count"]:
        message += _("packet.words_existing", count=result["existing_word_count"])
    flash(message)
    return redirect(url_for(
        "intake.candidates", source_id=result["source_id"],
    ))


@bp.post(
    "/partner-packets/<int:packet_id>/items/<int:item_id>/suggest-terms",
)
@login_required
def suggest_packet_item_terms(packet_id, item_id):
    try:
        result = packets_svc.suggest_received_item_terms(
            _uid(), packet_id, item_id,
        )
    except ValueError as exc:
        item = packets_svc.get_received_packet_item(_uid(), packet_id, item_id)
        if item is None:
            abort(404)
        return _render_packet_adopt_form(
            packet_id, item,
            terms=item.content,
            suggestion_message=_service_error(exc),
        )
    except packets_svc.TermSuggestionUnavailable:
        item = packets_svc.get_received_packet_item(_uid(), packet_id, item_id)
        if item is None:
            abort(404)
        return _render_packet_adopt_form(
            packet_id, item,
            terms=item.content,
            suggestion_message=_("packet.ai_unavailable"),
        )
    if result is None:
        abort(404)
    return _render_packet_adopt_form(
        packet_id, result["item"],
        terms="\n".join(result["terms"]),
        suggestion_message=_("packet.ai_suggested"),
    )


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
