"""Reading shelf and read-only document routes."""
import re
from contextlib import contextmanager

import pytest

from app.extensions import db
from flask import g
from app.services.reading import service as reading_svc
from tests.helpers import provision_user, login

PW = "pw12345678"


@contextmanager
def _rls_context(app, user_id):
    with app.test_request_context("/"):
        g.rls_uid = user_id
        try:
            yield
        finally:
            db.session.remove()


def _user(app, email):
    return provision_user(app, email, PW)


def _login(client, email):
    return login(client, email, PW)


def _csrf(client, path="/"):
    page = client.get(path).get_data(as_text=True)
    match = re.search(r'name="csrf_token"[^>]*value="([^"]+)"', page)
    return match.group(1) if match else None


def _create_doc(app, user_id, **overrides):
    """Create a reading document using the service layer with RLS context."""
    payload = {
        "language_code": "en",
        "title": "Test Document",
        "source_filename": "test.pdf",
        "content_text": "Hello world. This is a test document. Enjoy reading.",
        "content_hash": None,
        "page_count": 1,
    }
    payload.update(overrides)
    with _rls_context(app, user_id):
        doc = reading_svc.create_document(user_id, **payload)
        doc_id = doc.id
    return doc_id


class TestReadingRoutesLoginRequired:
    def test_shelf_requires_login(self, client):
        resp = client.get("/reading")
        assert resp.status_code == 302
        assert "/login" in resp.headers.get("Location", "")

    def test_new_requires_login(self, client):
        resp = client.get("/reading/new")
        assert resp.status_code == 302
        assert "/login" in resp.headers.get("Location", "")

    def test_show_requires_login(self, client):
        resp = client.get("/reading/1")
        assert resp.status_code == 302
        assert "/login" in resp.headers.get("Location", "")

    def test_delete_requires_login(self, client):
        resp = client.post("/reading/1/delete")
        assert resp.status_code == 302
        assert "/login" in resp.headers.get("Location", "")


class TestReadingShelf:
    def test_shelf_lists_user_documents(self, app, client):
        uid = _user(app, "shelf-a@t.com")
        _login(client, "shelf-a@t.com")
        _create_doc(app, uid, content_hash="shelf-hash-a")

        page = client.get("/reading").get_data(as_text=True)

        assert "Test Document" in page
        assert "/reading/new" in page

    def test_shelf_only_shows_current_user_docs(self, app, client):
        """User B's shelf does not show User A's documents."""
        uid_a = _user(app, "shelf-owner@t.com")
        _user(app, "shelf-other@t.com")
        _create_doc(app, uid_a, content_hash="shelf-isolation-hash")

        _login(client, "shelf-other@t.com")
        page = client.get("/reading").get_data(as_text=True)

        assert "Test Document" not in page

    def test_shelf_empty_state(self, app, client):
        _user(app, "shelf-empty@t.com")
        _login(client, "shelf-empty@t.com")

        page = client.get("/reading").get_data(as_text=True)

        assert "还没有阅读材料" in page or "空空如也" in page or "reading" in page.lower()


class TestReadingShow:
    def test_reader_shows_document_content(self, app, client):
        uid = _user(app, "reader-a@t.com")
        _login(client, "reader-a@t.com")
        doc_id = _create_doc(app, uid, content_hash="reader-show-hash",
                             content_text="Chapter One. It was a dark and stormy night.")

        page = client.get(f"/reading/{doc_id}").get_data(as_text=True)

        assert "Chapter One" in page
        assert "dark and stormy night" in page

    def test_user_b_gets_404_for_user_a_document(self, app, client):
        uid_a = _user(app, "show-owner@t.com")
        _user(app, "show-other@t.com")
        doc_id = _create_doc(app, uid_a, content_hash="show-isolation-hash")

        _login(client, "show-other@t.com")
        resp = client.get(f"/reading/{doc_id}")

        assert resp.status_code == 404

    def test_nonexistent_document_returns_404(self, app, client):
        _user(app, "show-404@t.com")
        _login(client, "show-404@t.com")

        resp = client.get("/reading/99999")

        assert resp.status_code == 404


class TestReadingDelete:
    def test_delete_removes_document(self, app, client):
        uid = _user(app, "delete-owner@t.com")
        _login(client, "delete-owner@t.com")
        doc_id = _create_doc(app, uid, content_hash="delete-hash")

        csrf = _csrf(client, "/reading")
        resp = client.post(f"/reading/{doc_id}/delete",
                           data={"csrf_token": csrf})

        assert resp.status_code == 302
        assert resp.headers.get("Location", "").endswith("/reading")

        with _rls_context(app, uid):
            assert reading_svc.get_document(uid, doc_id) is None

    def test_user_b_cannot_delete_user_a_document(self, app, client):
        uid_a = _user(app, "delete-a@t.com")
        _user(app, "delete-b@t.com")
        doc_id = _create_doc(app, uid_a, content_hash="delete-cross-hash")

        _login(client, "delete-b@t.com")
        csrf = _csrf(client, "/reading")
        resp = client.post(f"/reading/{doc_id}/delete",
                           data={"csrf_token": csrf})

        assert resp.status_code == 404

    def test_delete_nonexistent_document_returns_404(self, app, client):
        _user(app, "delete-404@t.com")
        _login(client, "delete-404@t.com")

        csrf = _csrf(client, "/reading")
        resp = client.post("/reading/99999/delete",
                           data={"csrf_token": csrf})

        assert resp.status_code == 404
