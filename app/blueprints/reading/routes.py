"""阅读书架 + 阅读器只读页面。

Task 7 范围：书架列表、上传占位页、阅读器只读展示、删除文档。
无上传处理、无查词卡片、无 JS。
"""
from flask import Blueprint, render_template, redirect, url_for, request, flash, abort
from flask_login import login_required, current_user

from app.services.reading import service as reading_svc

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
    """上传新阅读材料页面（占位：Task 8 实现 POST 上传）。"""
    return render_template("reading/new.html")


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
