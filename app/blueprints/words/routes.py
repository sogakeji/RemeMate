"""词库管理 + SRS 复习 + 统计。

路由只取参数、调 service、渲染；业务逻辑在 services/words.py（见模块边界规则）。
"""
import json

from flask import Blueprint, render_template, request, abort, jsonify
from flask_login import login_required, current_user

from app.services import words as words_svc
from app.services import llm as llm_svc
from app.blueprints.words.forms import LanguageChoiceForm

bp = Blueprint("words", __name__)


def _uid():
    return current_user.id


# ---- 加词中心（单一入口：手工多词义 + AI 三端点；导入/抽词并入此页入口） ----

_POS_CHOICES = ["", "n.", "v.", "adj.", "adv.", "prep.", "conj.",
                "pron.", "interj.", "num.", "art.", "phr."]


@bp.get("/words/add")
@login_required
def add_center():
    form = LanguageChoiceForm()
    # 默认选当前语言（用户切了语言，进加词中心就该是该语言；仍可下拉切其它语言加多语言）
    cur = words_svc.get_current_language(_uid())
    if cur:
        form.language_code.data = cur
    return render_template("words/add.html", form=form, pos_choices=_POS_CHOICES,
                           lang_map=words_svc._LANGUAGE_NAMES,
                           ai_enabled=bool(llm_svc.get_chain("general")))


@bp.post("/words/add")
@login_required
def add_submit():
    """JSON 多词义提交：{language_code, word, definitions:[{part_of_speech,meaning,example,note}, ...]}.

    绑定该语言的隐式词表（不存在则建），word 挂多条 Definition。CSRF 走 HTMX
    全局 X-CSRFToken 头（fetch 同理带）。
    """
    data = request.get_json(silent=True) or {}
    lang = data.get("language_code", "").strip()
    word = (data.get("word") or "").strip()
    defs = data.get("definitions") or []
    if lang not in words_svc._LANGUAGE_NAMES:
        return jsonify({"error": "请选择语言"}), 400
    if not word or len(word) > 200:
        return jsonify({"error": "请输入词（≤200 字）"}), 400
    if not defs or not isinstance(defs, list):
        return jsonify({"error": "至少填一条释义"}), 400
    # 清洗：允许空字段，但要求每条至少有词性或释义
    cleaned = []
    for d in defs:
        if not isinstance(d, dict):
            continue
        pos = (d.get("part_of_speech") or "").strip()
        meaning = (d.get("meaning") or "").strip()
        example = (d.get("example") or "").strip()
        note = (d.get("note") or "").strip()
        if not pos and not meaning:
            continue
        cleaned.append({"part_of_speech": pos or None, "meaning": meaning or None,
                         "example": example or None, "note": note or None})
    if not cleaned:
        return jsonify({"error": "至少填一条带词性或释义的项"}), 400

    wl = words_svc.get_or_create_language_list(_uid(), lang)
    w = words_svc.add_word(_uid(), wl.id, word, definitions=cleaned)
    if w is None:
        return jsonify({"error": "加词失败"}), 500
    return jsonify({"ok": True, "word_id": w.id, "word": word,
                    "list_id": wl.id})


@bp.post("/words/ai-fill")
@login_required
def ai_fill():
    """AI 一键填充：{word, language_code} → {definitions:[...]} 或 {error}。"""
    data = request.get_json(silent=True) or {}
    word = (data.get("word") or "").strip()
    lang = data.get("language_code", "").strip()
    if not word:
        return jsonify({"error": "请输入词"}), 400
    if lang not in words_svc._LANGUAGE_NAMES:
        return jsonify({"error": "请选择语言"}), 400
    info = llm_svc.generate_full_word_info(
        word, language=words_svc._language_name(lang))
    return jsonify(info)        # 成功带 definitions；失败带 error


@bp.post("/words/generate-example")
@login_required
def generate_example():
    """生成例句：{word, part_of_speech, meaning, language_code} → {example} 或 {error}。"""
    data = request.get_json(silent=True) or {}
    word = (data.get("word") or "").strip()
    pos = (data.get("part_of_speech") or "").strip()
    meaning = (data.get("meaning") or "").strip()
    lang = data.get("language_code", "").strip()
    if not word or not meaning:
        return jsonify({"error": "词与释义都要填"}), 400
    if lang not in words_svc._LANGUAGE_NAMES:
        return jsonify({"error": "请选择语言"}), 400
    out = llm_svc.generate_example(word, pos, meaning,
                                   language=words_svc._language_name(lang))
    if out is None:
        return jsonify({"error": "AI 暂不可用，稍后再试"}), 503
    return jsonify({"example": out})


@bp.post("/words/generate-note")
@login_required
def generate_note():
    """生成笔记：{word, part_of_speech, meaning, language_code} → {note} 或 {error}。"""
    data = request.get_json(silent=True) or {}
    word = (data.get("word") or "").strip()
    pos = (data.get("part_of_speech") or "").strip()
    meaning = (data.get("meaning") or "").strip()
    lang = data.get("language_code", "").strip()
    if not word or not meaning:
        return jsonify({"error": "词与释义都要填"}), 400
    if lang not in words_svc._LANGUAGE_NAMES:
        return jsonify({"error": "请选择语言"}), 400
    out = llm_svc.generate_note(word, pos, meaning,
                                language=words_svc._language_name(lang))
    if out is None:
        return jsonify({"error": "AI 暂不可用，稍后再试"}), 503
    return jsonify({"note": out})


# ---- 词库 / 词表 / 复习 / 统计（既有） ----

@bp.get("/words")
@login_required
def lists():
    lang, ws = words_svc.get_words_for_current_language(_uid())
    return render_template("words/list.html", words=ws,
                           current_language=lang,
                           lang_name=words_svc._language_name(lang) if lang else None)


@bp.get("/words/<int:list_id>")
@login_required
def detail(list_id):
    wl = words_svc.get_word_list(_uid(), list_id, eager=True)
    if wl is None:
        abort(404)
    return render_template("words/detail.html", wl=wl)


@bp.route("/review")
@login_required
def review():
    due = words_svc.get_due_words(_uid(), limit=1)
    return render_template("review/review.html", word=due[0] if due else None)


@bp.route("/review/<int:word_id>/grade", methods=["POST"])
@login_required
def grade(word_id):
    button = request.form.get("button", "")
    try:
        result = words_svc.review_word(_uid(), word_id, button)
    except ValueError:
        abort(400)                      # 非法/缺失 button（M1）
    if result is None:
        abort(404)
    nxt = words_svc.get_due_words(_uid(), limit=1)
    # HTMX：返回下一张卡片片段（无则完成提示）
    return render_template("review/_card.html", word=nxt[0] if nxt else None)


@bp.route("/stats")
@login_required
def stats():
    # 统计按当前语言看板（与首页/词库/加词闭环一致）：total/due/list 都按当前语言切，
    # reviewed_today/heatmap 跨语言合计（复习历史不按语言切更稳）。
    lang = words_svc.get_current_language(_uid())
    return render_template("words/stats.html",
                           stats=words_svc.get_stats(_uid(), language_code=lang),
                           current_language=lang,
                           lang_name=words_svc._language_name(lang) if lang else None)
