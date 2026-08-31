from flask import abort, current_app, jsonify, redirect, render_template, request, url_for
from flask_login import current_user, login_required

from app.services import practice as practice_svc

from app.blueprints.practice import bp


def _voice_locale(language_code):
    return practice_svc.voice_locale(language_code)


@bp.before_request
def enforce_beta_gate():
    if not current_app.config.get("PRACTICE_ENABLED", False):
        abort(404)


@bp.get("/practice")
@login_required
def index():
    language_code, question_count = practice_svc.get_start_state(current_user.id)
    return render_template(
        "practice/start.html",
        question_count=question_count,
        language_code=language_code,
        voice_locale=_voice_locale(language_code),
    )


@bp.post("/practice/start")
@login_required
def start():
    raw_voice_available = request.form.get("voice_available")
    voice_available = None
    if raw_voice_available in {"1", "true", "on"}:
        voice_available = True
    elif raw_voice_available in {"0", "false", "off"}:
        voice_available = False
    try:
        practice_session = practice_svc.start_session(
            current_user.id,
            voice_available=voice_available,
        )
    except practice_svc.VoiceUnavailableError:
        abort(409)
    if practice_session is None:
        return redirect(url_for("practice.index"), code=303)
    return redirect(
        url_for("practice.session_view", session_id=practice_session.id),
        code=303,
    )


@bp.post("/practice/voice-unavailable")
@login_required
def voice_unavailable():
    blocked = practice_svc.record_voice_unavailable(
        current_user.id,
    )
    if blocked is None:
        abort(409)
    return jsonify(
        status=blocked.status,
        session_id=blocked.id,
        session_url=url_for(
            "practice.session_view", session_id=blocked.id,
        ),
    )


@bp.get("/practice/<int:session_id>")
@login_required
def session_view(session_id):
    practice_session = practice_svc.get_session(current_user.id, session_id)
    if practice_session is None or not practice_session.items:
        abort(404)
    if practice_session.status == "completed":
        return render_template(
            "practice/complete.html",
            practice_session=practice_session,
            voice_locale=_voice_locale(practice_session.language_code),
        )
    if practice_session.status in {"abandoned", "blocked"}:
        abort(404)
    item = practice_session.items[practice_session.current_position]
    if item.submitted_at is not None:
        return render_template(
            "practice/feedback.html",
            practice_session=practice_session,
            item=item,
            voice_locale=_voice_locale(practice_session.language_code),
        )
    before, after = practice_svc.prompt_parts(
        item.sentence, item.target, practice_session.language_code,
    )
    return render_template(
        "practice/question.html",
        practice_session=practice_session,
        item=item,
        prompt_before=before,
        prompt_after=after,
        voice_locale=_voice_locale(practice_session.language_code),
    )


@bp.post("/practice/<int:session_id>/items/<int:item_id>/answer")
@login_required
def submit(session_id, item_id):
    answer = request.form.get("answer", "")
    try:
        result = practice_svc.submit_answer(
            current_user.id,
            session_id,
            item_id,
            answer,
            request.form.get("answer_duration_ms"),
        )
    except practice_svc.EmptyAnswerError:
        abort(400)
    except practice_svc.OutOfOrderAnswerError:
        abort(409)
    if result is None:
        abort(404)
    practice_session, item = result
    return render_template(
        "practice/feedback.html",
        practice_session=practice_session,
        item=item,
        voice_locale=_voice_locale(practice_session.language_code),
    )


@bp.get("/practice/<int:session_id>/continue")
@login_required
def continue_via_get(session_id):
    practice_session = practice_svc.get_session(current_user.id, session_id)
    if practice_session is None or not practice_session.items:
        abort(404)
    return redirect(
        url_for("practice.session_view", session_id=session_id),
        code=303,
    )


@bp.post("/practice/<int:session_id>/continue")
@login_required
def continue_session(session_id):
    practice_session = practice_svc.continue_session(
        current_user.id, session_id,
    )
    if practice_session is None:
        abort(404)
    return redirect(
        url_for("practice.session_view", session_id=session_id),
        code=303,
    )


@bp.post("/practice/<int:session_id>/items/<int:item_id>/replay")
@login_required
def replay(session_id, item_id):
    if not practice_svc.record_replay(current_user.id, session_id, item_id):
        abort(404)
    return ("", 204)


@bp.post("/practice/<int:session_id>/abandon")
@login_required
def abandon(session_id):
    if not practice_svc.abandon_session(current_user.id, session_id):
        abort(404)
    return ("", 204)
