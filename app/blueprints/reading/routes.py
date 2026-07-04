"""阅读书架 + 阅读器只读页面。

Task 7 范围：书架列表、上传占位页、阅读器只读展示、删除文档。
Task 8 范围：PDF 上传路由。
"""
import hashlib

from flask import Blueprint, render_template, redirect, url_for, request, flash, abort
from flask_login import login_required, current_user
from sqlalchemy.exc import IntegrityError

from app.extensions import db
from app.models.reading import ReadingDocument
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
    """上传新阅读材料页面（Task 8 实现 POST 上传）。"""
    return render_template("reading/new.html")


@bp.post("/reading")
@login_required
def create():
    """上传 PDF 阅读材料（Task 8）。

    验证语言、文件扩展名，调用 parser 提取文本，创建或去重文档。
    """
    # 1. Validate language
    language_code = request.form.get("language_code", "").strip()
    if language_code not in ("zh", "en", "ja", "fr"):
        flash("当前版本只支持中文、英文、日文、法文")
        return redirect(url_for("reading.new"))

    # 2. Validate file presence
    file = request.files.get("file")
    if not file or not file.filename:
        flash("请选择文件")
        return redirect(url_for("reading.new"))

    # 3. Validate file extension
    if not file.filename.lower().endswith(".pdf"):
        flash("当前版本只支持文本型 PDF")
        return redirect(url_for("reading.new"))

    file_bytes = file.read()

    # 4. Parse PDF
    try:
        parsed = reading_parsers.parse_pdf_bytes(file_bytes, file.filename)
    except EmptyPdfText:
        flash("这个 PDF 可能是扫描件，当前版本暂不支持 OCR")
        return redirect(url_for("reading.new"))
    except PdfParseError as e:
        flash(str(e))
        return redirect(url_for("reading.new"))

    # 5. Hash content for dedup
    content_hash = hashlib.sha256(parsed.text.encode("utf-8")).hexdigest()

    # 6. Create document or dedup
    try:
        doc = reading_svc.create_document(
            _uid(),
            language_code=language_code,
            title=parsed.title,
            source_filename=file.filename,
            content_text=parsed.text,
            content_hash=content_hash,
            page_count=parsed.page_count,
        )
    except IntegrityError:
        db.session.rollback()
        existing = ReadingDocument.query.filter_by(
            user_id=_uid(), content_hash=content_hash
        ).first()
        if existing:
            flash("该 PDF 已上传")
            return redirect(url_for("reading.show", doc_id=existing.id))
        raise

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
