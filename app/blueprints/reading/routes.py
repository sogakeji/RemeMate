"""阅读书架 + 阅读器只读页面。

Task 7 范围：书架列表、上传占位页、阅读器只读展示、删除文档。
Task 8 范围：PDF 上传路由。
Task 9 范围：查词弹卡 + 加入候选 action。
"""
from flask import Blueprint, render_template, redirect, url_for, request, flash, abort
from flask_login import login_required, current_user
from sqlalchemy.exc import IntegrityError

from app.extensions import db
from app.models.reading import ReadingDocument, ReadingLookup
from app.services.reading import service as reading_svc
from app.services.reading import parsers as reading_parsers
from app.services.reading.parsers import EmptyPdfText, PdfParseError

bp = Blueprint("reading", __name__)


def _uid():
    return current_user.id


@bp.get("/reading")
@login_required
def index():
    """书架：展示当前用户的所有阅读材料（按最近更新倒序）。"""
    documents = reading_svc.list_documents(_uid())
    return render_template("reading/index.html", documents=documents)


@bp.get("/reading/new")
@login_required
def new():
    """上传新阅读材料页面。"""
    return render_template("reading/new.html")


@bp.post("/reading")
@login_required
def create():
    """上传 PDF 阅读材料。

    验证语言、文件扩展名，调用 parser 提取文本，创建或去重文档。
    """
    language_code = request.form.get("language_code", "").strip()
    if language_code not in ("zh", "en", "ja", "fr"):
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
        parsed = reading_parsers.parse_pdf_bytes(file_bytes, file.filename)
    except EmptyPdfText:
        flash("这个 PDF 可能是扫描件，当前版本暂不支持 OCR")
        return redirect(url_for("reading.new"))
    except PdfParseError as e:
        flash(str(e))
        return redirect(url_for("reading.new"))

    try:
        doc = reading_svc.create_document(
            _uid(),
            language_code=language_code,
            title=parsed.title,
            source_filename=file.filename,
            content_text=parsed.text,
            content_hash=None,          # let service own the hash
            page_count=parsed.page_count,
        )
    except IntegrityError:
        db.session.rollback()
        existing = ReadingDocument.query.filter_by(
            user_id=_uid(), content_hash=reading_svc._content_hash(parsed.text)
        ).first()
        if existing:
            flash("该 PDF 已上传")
            return redirect(url_for("reading.show", doc_id=existing.id))
        flash("上传失败，请稍后重试")
        return redirect(url_for("reading.new"))

    return redirect(url_for("reading.show", doc_id=doc.id))


@bp.get("/reading/<int:doc_id>")
@login_required
def show(doc_id):
    """阅读器：展示文档纯文本内容。"""
    document = reading_svc.get_document(_uid(), doc_id)
    if document is None:
        abort(404)
    return render_template("reading/show.html", document=document)


@bp.post("/reading/<int:doc_id>/delete")
@login_required
def delete(doc_id):
    """删除阅读材料（及关联的 lookup）。"""
    deleted = reading_svc.delete_document(_uid(), doc_id)
    if not deleted:
        abort(404)
    flash("阅读材料已删除")
    return redirect(url_for("reading.index"))


def _int_form(field, *, default=None):
    """Parse an int form field; return default if missing/invalid."""
    raw = request.form.get(field)
    if raw is None or raw == "":
        return default
    try:
        return int(raw)
    except (TypeError, ValueError):
        return None


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
    selection_start = _int_form("selection_start")
    selection_end = _int_form("selection_end")
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
    """加入学习：把 lookup 转成 WordCandidate，跳到候选审核页。

    幂等：重复调用返回同一 source 的候选审核页。
    """
    try:
        result = reading_svc.add_lookup_to_candidate(_uid(), lookup_id)
    except reading_svc.ReadingNotFound:
        abort(404)

    state = result.get("state")
    source_id = result.get("source_id")

    if state == "existing-word":
        flash("词库中已存在该词")
        # source_id 可能未创建（existing-word 短路在 source 创建之前），
        # 用 lookup 的 document 反查 source。
        lookup_row = ReadingLookup.query.filter_by(
            id=lookup_id, user_id=_uid()
        ).first()
        if lookup_row is not None and lookup_row.document.intake_source_id:
            return redirect(url_for("intake.candidates",
                                    source_id=lookup_row.document.intake_source_id))
        return redirect(url_for("reading.index"))

    if state == "already-candidate":
        flash("已加入候选，可在候选页审核")
    else:
        flash("已加入候选，可在候选页审核")

    if source_id is None:
        # already-candidate 路径不一定返回 source_id；从 candidate 反查。
        from app.models.intake import WordCandidate
        cand = WordCandidate.query.filter_by(
            id=result.get("candidate_id"), user_id=_uid()
        ).first()
        if cand is not None:
            source_id = cand.source_id

    if source_id is None:
        return redirect(url_for("reading.index"))
    return redirect(url_for("intake.candidates", source_id=source_id))
