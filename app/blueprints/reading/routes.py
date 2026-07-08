"""阅读书架 + 阅读器只读页面。

Task 7 范围：书架列表、上传占位页、阅读器只读展示、删除文档。
Task 8 范围：PDF 上传路由。
Task 9 范围：查词弹卡 + 加入候选 action。
Task 10 范围：阅读位置保存 + 选词 JS。
"""
from flask import Blueprint, render_template, redirect, url_for, request, flash, abort
from flask_login import login_required, current_user

from app.extensions import db
from app.models.reading import ReadingDocument, ReadingLookup
from app.models.word import Word, WordList
from app.models.intake import WordCandidate
from app.services.reading import service as reading_svc
from app.services.reading import parsers as reading_parsers
from app.services.reading.parsers import EmptyPdfText, PdfParseError, ContentQualityError
from app.services.reading.dictionary import SUPPORTED_LANGUAGES

bp = Blueprint("reading", __name__)


from app.services import words as words_svc


def _uid():
    return current_user.id


@bp.get("/reading")
@login_required
def index():
    """书架：展示当前用户在当前语言下的阅读材料（按最近更新倒序）。"""
    lang = words_svc.get_current_language(_uid())
    documents = reading_svc.list_documents(_uid(), language_code=lang)

    # 为每本书查待审核候选词数
    source_ids = [d.intake_source_id for d in documents if d.intake_source_id]
    pending_counts = {}
    if source_ids:
        from sqlalchemy import func
        rows = (db.session.query(
                    WordCandidate.source_id,
                    func.count(WordCandidate.id))
                .filter(WordCandidate.source_id.in_(source_ids),
                        WordCandidate.status == "pending")
                .group_by(WordCandidate.source_id).all())
        pending_counts = {row[0]: row[1] for row in rows}

    return render_template("reading/index.html", documents=documents,
                           pending_counts=pending_counts)


@bp.get("/reading/new")
@login_required
def new():
    """上传新阅读材料页面。语言选择器默认当前语言。"""
    lang = words_svc.get_current_language(_uid()) or ""
    return render_template("reading/new.html", current_lang=lang)


@bp.post("/reading")
@login_required
def create():
    """上传 PDF 阅读材料。

    验证语言、文件扩展名，调用 parser 提取文本，创建或去重文档。
    """
    language_code = request.form.get("language_code", "").strip()
    if language_code not in SUPPORTED_LANGUAGES:
        flash("当前版本只支持中文、英文、日文、法文")
        return redirect(url_for("reading.new"))

    file = request.files.get("file")
    if not file or not file.filename:
        flash("请选择文件")
        return redirect(url_for("reading.new"))

    if not file.filename.lower().endswith(".pdf"):
        flash("当前版本只支持文本型 PDF")
        return redirect(url_for("reading.new"))

    file_bytes = file.read()

    try:
        chunks = reading_parsers.parse_pdf_bytes_multi(
            file_bytes, file.filename, language_code=language_code)
    except EmptyPdfText:
        flash("这个 PDF 可能是扫描件，当前版本暂不支持 OCR")
        return redirect(url_for("reading.new"))
    except PdfParseError as e:
        flash(str(e))
        return redirect(url_for("reading.new"))

    if len(chunks) > 1:
        flash(f"PDF 共 {len(chunks)} 部分，已自动切分为 {len(chunks)} 篇阅读材料")

    docs = []
    for parsed in chunks:
        try:
            reading_parsers.validate_content_quality(parsed.text, language_code)
        except ContentQualityError as e:
            flash(str(e))
            continue

        doc = reading_svc.create_document(
            _uid(),
            language_code=language_code,
            title=parsed.title,
            source_filename=file.filename,
            content_text=parsed.text,
            content_hash=None,
            page_count=parsed.page_count,
        )
        if doc not in docs:
            docs.append(doc)

    if not docs:
        flash("所有部分均未通过内容质量检查，请确认 PDF 为文本型文档")
        return redirect(url_for("reading.new"))
    if len(docs) == 1:
        return redirect(url_for("reading.show", doc_id=docs[0].id))
    return redirect(url_for("reading.index"))


@bp.get("/reading/<int:doc_id>")
@login_required
def show(doc_id):
    """阅读器：展示文档纯文本内容。"""
    document = reading_svc.get_document(_uid(), doc_id)
    if document is None:
        abort(404)
    known_words = [
        row[0] for row in
        Word.query.join(WordList).filter(
            WordList.user_id == _uid(),
            WordList.language_code == document.language_code,
        ).with_entities(Word.word).all()
    ]
    return render_template("reading/show.html", document=document,
                           known_words=known_words)


@bp.post("/reading/<int:doc_id>/delete")
@login_required
def delete(doc_id):
    """删除阅读材料（及关联的 lookup）。"""
    deleted = reading_svc.delete_document(_uid(), doc_id)
    if not deleted:
        abort(404)
    flash("阅读材料已删除")
    return redirect(url_for("reading.index"))


@bp.post("/reading/<int:doc_id>/position")
@login_required
def update_position(doc_id):
    """保存最后阅读位置。前端滚动时或离开页面前上报。"""
    document = reading_svc.get_document(_uid(), doc_id)
    if document is None:
        abort(404)
    char_offset = request.form.get("char_offset", type=int)
    scroll_ratio_raw = request.form.get("scroll_ratio")
    if char_offset is None or scroll_ratio_raw is None:
        abort(400, "missing char_offset or scroll_ratio")
    try:
        payload = {"char_offset": int(char_offset),
                   "scroll_ratio": float(scroll_ratio_raw)}
    except (TypeError, ValueError):
        abort(400, "invalid numeric values")
    try:
        reading_svc.update_last_position(_uid(), doc_id, payload)
    except ValueError as e:
        abort(400, str(e))
    return "", 200


@bp.post("/reading/<int:doc_id>/lookup")
@login_required
def lookup(doc_id):
    """查词：根据选中文本和位置查本地词典，返回 _lookup_card 片段。

    HTMX 友好：返回 HTML 片段，前端注入到选词位置旁的卡片容器。
    """
    document = reading_svc.get_document(_uid(), doc_id)
    if document is None:
        abort(404)

    term = (request.form.get("term") or "").strip()
    selection_start = request.form.get("selection_start", type=int)
    selection_end = request.form.get("selection_end", type=int)
    if not term or selection_start is None or selection_end is None:
        abort(400, "missing term or selection offsets")

    try:
        lookup_row = reading_svc.lookup_term(
            _uid(), doc_id, term, selection_start, selection_end,
        )
    except ValueError as e:
        abort(400, str(e))

    return render_template("reading/_lookup_card.html", lookup=lookup_row,
                           document=document)


@bp.post("/reading/lookups/<int:lookup_id>/add-candidate")
@login_required
def add_candidate(lookup_id):
    """加入学习：把 lookup 转成 WordCandidate。

    幂等：重复调用返回同一 source 的候选审核页。
    """
    try:
        result = reading_svc.add_lookup_to_candidate(_uid(), lookup_id)
    except reading_svc.ReadingNotFound:
        abort(404)

    state = result["state"]
    source_id = result.get("source_id")
    is_ajax = request.headers.get("X-Requested-With") == "XMLHttpRequest"

    if state == "existing-word":
        if is_ajax:
            return {"ok": False, "state": "existing-word", "message": "词库中已存在该词"}
        flash("词库中已存在该词")
        if source_id:
            return redirect(url_for("intake.candidates", source_id=source_id))
        return redirect(url_for("reading.index"))

    if is_ajax:
        return {
            "ok": True,
            "state": state,
            "term": result.get("term", ""),
            "source_id": source_id,
            "candidate_id": result.get("candidate_id"),
        }

    flash("已加入候选，可在候选页审核")
    if source_id:
        return redirect(url_for("intake.candidates", source_id=source_id))
    return redirect(url_for("reading.index"))
