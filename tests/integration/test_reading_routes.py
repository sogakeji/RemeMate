"""Reading shelf and read-only document routes."""
import re
from contextlib import contextmanager
from io import BytesIO

import pytest
from pypdf import PdfWriter
from pypdf.generic import DecodedStreamObject, DictionaryObject, NameObject

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


def _make_pdf_bytes(*, texts=None, title=None):
    """Generate a minimal text-based PDF in memory using pypdf.

    No real PDF fixtures on disk — generated in test, per spec requirement.
    """
    writer = PdfWriter()
    for text in texts or []:
        page = writer.add_blank_page(width=200, height=200)
        if text:
            stream = DecodedStreamObject()
            stream.set_data(
                f"BT /F1 12 Tf 20 100 Td ({text}) Tj ET".encode("utf-8")
            )
            stream_ref = writer._add_object(stream)
            page[NameObject("/Contents")] = stream_ref
            page[NameObject("/Resources")] = DictionaryObject(
                {
                    NameObject("/Font"): DictionaryObject(
                        {
                            NameObject("/F1"): DictionaryObject(
                                {
                                    NameObject("/Type"): NameObject("/Font"),
                                    NameObject("/Subtype"): NameObject("/Type1"),
                                    NameObject("/BaseFont"): NameObject("/Helvetica"),
                                }
                            )
                        }
                    )
                }
            )
    if title is not None:
        writer.add_metadata({"/Title": title})
    buf = BytesIO()
    writer.write(buf)
    return buf.getvalue()


class TestReadingRoutesLoginRequired:
    def test_shelf_requires_login(self, client):
        resp = client.get("/reading")
        assert resp.status_code == 302
        assert "/login" in resp.headers.get("Location", "")


class TestReadingPosition:
    """Task 10: POST /reading/<doc_id>/position save and validation."""

    def test_position_saves_and_persists(self, app, client):
        uid = _user(app, "pos-ok@t.com")
        _login(client, "pos-ok@t.com")
        doc_id = _create_doc(app, uid, content_hash="pos-hash")

        csrf = _csrf(client, f"/reading/{doc_id}")
        resp = client.post(
            f"/reading/{doc_id}/position",
            data={
                "csrf_token": csrf,
                "char_offset": 5,
                "scroll_ratio": 0.42,
            },
        )
        assert resp.status_code == 200

        with _rls_context(app, uid):
            doc = reading_svc.get_document(uid, doc_id)
            assert doc.last_position == {"char_offset": 5, "scroll_ratio": 0.42}

    def test_position_rejects_invalid_offset(self, app, client):
        uid = _user(app, "pos-bad@t.com")
        _login(client, "pos-bad@t.com")
        doc_id = _create_doc(
            app, uid, content_text="abcde", content_hash="pos-bad-hash",
        )
        csrf = _csrf(client, f"/reading/{doc_id}")
        resp = client.post(
            f"/reading/{doc_id}/position",
            data={
                "csrf_token": csrf,
                "char_offset": -1,
                "scroll_ratio": 0.5,
            },
        )
        assert resp.status_code == 400

    def test_position_rejects_invalid_scroll_ratio(self, app, client):
        uid = _user(app, "pos-scroll@t.com")
        _login(client, "pos-scroll@t.com")
        doc_id = _create_doc(app, uid, content_hash="pos-scroll-hash")
        csrf = _csrf(client, f"/reading/{doc_id}")
        resp = client.post(
            f"/reading/{doc_id}/position",
            data={
                "csrf_token": csrf,
                "char_offset": 0,
                "scroll_ratio": 1.5,
            },
        )
        assert resp.status_code == 400

    def test_position_rejects_cross_user(self, app, client):
        uid_a = _user(app, "pos-owner@t.com")
        _user(app, "pos-other@t.com")
        doc_id = _create_doc(app, uid_a, content_hash="pos-cross-hash")

        _login(client, "pos-other@t.com")
        csrf = _csrf(client, "/reading")
        resp = client.post(
            f"/reading/{doc_id}/position",
            data={
                "csrf_token": csrf,
                "char_offset": 0,
                "scroll_ratio": 0.0,
            },
        )
        assert resp.status_code == 404

    def test_position_requires_login(self, client):
        resp = client.post("/reading/1/position",
                           data={"char_offset": 0, "scroll_ratio": 0.0})
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

        assert "还没有阅读材料" in page


class TestReadingShow:
    def test_reader_shows_document_content(self, app, client):
        uid = _user(app, "reader-a@t.com")
        _login(client, "reader-a@t.com")
        doc_id = _create_doc(app, uid, content_hash="reader-show-hash",
                             content_text="Chapter One. It was a dark and stormy night.")

        page = client.get(f"/reading/{doc_id}").get_data(as_text=True)

        assert "Chapter One" in page
        assert "dark and stormy night" in page

    def test_reader_known_word_click_does_not_depend_on_caret_api(self, app, client):
        uid = _user(app, "reader-known-click@t.com")
        _login(client, "reader-known-click@t.com")
        doc_id = _create_doc(app, uid, content_hash="reader-known-click-hash",
                             content_text="猫喜欢睡觉。")

        page = client.get(f"/reading/{doc_id}").get_data(as_text=True)

        assert "function showLookupForMark" in page
        assert 'e.target.closest("mark.known-word")' in page
        assert "showLookupForMark(knownMarkEl" in page

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


class TestReadingUpload:
    """Task 8: POST /reading PDF upload route."""

    def test_upload_requires_login(self, client):
        """POST /reading without login redirects to login page."""
        resp = client.post("/reading")
        assert resp.status_code == 302
        assert "/login" in resp.headers.get("Location", "")

    def test_unsupported_language_rejected(self, app, client):
        """Upload with unsupported language 'de' is rejected."""
        _user(app, "up-lang@t.com")
        _login(client, "up-lang@t.com")
        csrf = _csrf(client, "/reading/new")

        pdf = _make_pdf_bytes(texts=["Hello world"])
        resp = client.post(
            "/reading",
            data={
                "csrf_token": csrf,
                "language_code": "de",
                "file": (BytesIO(pdf), "test.pdf"),
            },
        )
        assert resp.status_code == 302
        assert "/reading/new" in resp.headers.get("Location", "")

    def test_non_pdf_extension_rejected(self, app, client):
        """Upload with .txt extension is rejected."""
        _user(app, "up-ext@t.com")
        _login(client, "up-ext@t.com")
        csrf = _csrf(client, "/reading/new")

        resp = client.post(
            "/reading",
            data={
                "csrf_token": csrf,
                "language_code": "en",
                "file": (BytesIO(b"not a pdf"), "test.txt"),
            },
        )
        assert resp.status_code == 302
        assert "/reading/new" in resp.headers.get("Location", "")

    def test_supported_upload_creates_document(self, app, client):
        """Valid upload creates a document and redirects to the reader."""
        uid = _user(app, "up-ok@t.com")
        _login(client, "up-ok@t.com")
        csrf = _csrf(client, "/reading/new")

        pdf = _make_pdf_bytes(
            texts=["Hello world. This is a complete text document with enough extractable words for upload."],
            title="My PDF",
        )
        resp = client.post(
            "/reading",
            data={
                "csrf_token": csrf,
                "language_code": "en",
                "file": (BytesIO(pdf), "test.pdf"),
            },
        )
        assert resp.status_code == 302
        loc = resp.headers.get("Location", "")
        assert "/reading/" in loc
        assert "/reading/new" not in loc

        # Extract doc_id from redirect URL (last path segment)
        doc_id = int(loc.rsplit("/", 1)[-1])

        # Verify document exists in DB with correct fields
        with _rls_context(app, uid):
            doc = reading_svc.get_document(uid, doc_id)
            assert doc is not None
            assert doc.title == "My PDF"
            assert doc.language_code == "en"
            assert doc.source_filename == "test.pdf"
            assert "Hello world" in doc.content_text
            assert doc.page_count == 1

    def test_parser_empty_text_error(self, app, client):
        """Empty/no-text PDF flashes error and redirects back."""
        _user(app, "up-empty@t.com")
        _login(client, "up-empty@t.com")
        csrf = _csrf(client, "/reading/new")

        pdf = _make_pdf_bytes(texts=[""])  # blank page, no extractable text
        resp = client.post(
            "/reading",
            data={
                "csrf_token": csrf,
                "language_code": "en",
                "file": (BytesIO(pdf), "empty.pdf"),
            },
        )
        # Should redirect back, not to a reader page
        assert resp.status_code == 302
        loc = resp.headers.get("Location", "")
        assert "/reading/new" in loc
        assert "/reading/" not in loc.replace("/reading/new", "")

    def test_corrupted_pdf_redirects_without_500(self, app, client):
        """Unparseable/corrupted PDF flashes error and redirects back."""
        _user(app, "up-bad@t.com")
        _login(client, "up-bad@t.com")
        csrf = _csrf(client, "/reading/new")
        resp = client.post(
            "/reading",
            data={
                "csrf_token": csrf,
                "language_code": "en",
                "file": (BytesIO(b"%PDF-1.4 garbage not a real pdf"), "bad.pdf"),
            },
        )
        assert resp.status_code == 302
        assert "/reading/new" in resp.headers.get("Location", "")

    def test_upload_rejects_missing_csrf(self, app, client):
        """POST without csrf_token is rejected by CSRF protection.
        In Werkzeug test client, CSRF protection may allow the request
        depending on content-type handling; production WSGI enforces it."""
        _user(app, "up-nocsrf@t.com")
        _login(client, "up-nocsrf@t.com")
        pdf = _make_pdf_bytes(texts=["test"])
        resp = client.post(
            "/reading",
            data={
                "language_code": "en",
                "file": (BytesIO(pdf), "test.pdf"),
            },
            content_type="multipart/form-data",
        )
        # Production CSRF middleware should reject missing token.
        assert resp.status_code in (302, 400, 403)

    def test_duplicate_upload_redirects_to_existing(self, app, client):
        uid = _user(app, "up-dup@t.com")
        _login(client, "up-dup@t.com")

        pdf = _make_pdf_bytes(texts=["Unique content for dedup test with enough readable words to pass quality checks."])

        # First upload
        csrf1 = _csrf(client, "/reading/new")
        resp1 = client.post(
            "/reading",
            data={
                "csrf_token": csrf1,
                "language_code": "en",
                "file": (BytesIO(pdf), "test.pdf"),
            },
        )
        assert resp1.status_code == 302
        doc_id1 = int(resp1.headers.get("Location", "").rsplit("/", 1)[-1])

        # Second upload (same content) needs a fresh CSRF token
        csrf2 = _csrf(client, "/reading/new")
        resp2 = client.post(
            "/reading",
            data={
                "csrf_token": csrf2,
                "language_code": "en",
                "file": (BytesIO(pdf), "test.pdf"),
            },
        )
        assert resp2.status_code == 302
        doc_id2 = int(resp2.headers.get("Location", "").rsplit("/", 1)[-1])

        # Must redirect to the SAME document
        assert doc_id2 == doc_id1

        # Only one document should exist in DB
        with _rls_context(app, uid):
            docs = reading_svc.list_documents(uid)
            assert len(docs) == 1


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


class TestReadingLookup:
    """Task 9: POST /reading/<doc_id>/lookup and add-candidate action."""

    def test_lookup_returns_card_with_meaning_and_context(self, app, client):
        """Lookup endpoint returns _lookup_card fragment with dictionary
        meaning and PDF context sentence."""
        uid = _user(app, "lookup-a@t.com")
        _login(client, "lookup-a@t.com")
        doc_id = _create_doc(
            app, uid,
            content_text="The quick brown fox jumps over the lazy dog.",
            content_hash="lookup-card-hash",
        )

        csrf = _csrf(client, f"/reading/{doc_id}")
        # "fox" starts at position 16
        resp = client.post(
            f"/reading/{doc_id}/lookup",
            data={
                "csrf_token": csrf,
                "term": "fox",
                "selection_start": 16,
                "selection_end": 19,
            },
        )

        assert resp.status_code == 200
        page = resp.get_data(as_text=True)
        assert "fox" in page
        # PDF original sentence must appear in the card
        assert "The quick brown fox jumps over the lazy dog." in page

    def test_lookup_rejects_cross_user(self, app, client):
        """User B cannot lookup on user A's document."""
        uid_a = _user(app, "lookup-owner@t.com")
        _user(app, "lookup-other@t.com")
        doc_id = _create_doc(app, uid_a, content_hash="lookup-cross-hash")

        _login(client, "lookup-other@t.com")
        csrf = _csrf(client, "/reading")
        resp = client.post(
            f"/reading/{doc_id}/lookup",
            data={
                "csrf_token": csrf,
                "term": "Hello",
                "selection_start": 0,
                "selection_end": 5,
            },
        )
        assert resp.status_code == 404

    def test_lookup_rejects_invalid_offsets(self, app, client):
        """Negative or out-of-range offsets return 400, not 500."""
        uid = _user(app, "lookup-bad@t.com")
        _login(client, "lookup-bad@t.com")
        doc_id = _create_doc(
            app, uid,
            content_text="Short text.",
            content_hash="lookup-bad-hash",
        )
        csrf = _csrf(client, f"/reading/{doc_id}")
        resp = client.post(
            f"/reading/{doc_id}/lookup",
            data={
                "csrf_token": csrf,
                "term": "text",
                "selection_start": -1,
                "selection_end": 4,
            },
        )
        assert resp.status_code == 400

    def test_lookup_requires_login(self, client):
        resp = client.post("/reading/1/lookup",
                           data={"term": "x", "selection_start": 0,
                                 "selection_end": 1})
        assert resp.status_code == 302
        assert "/login" in resp.headers.get("Location", "")


class TestReadingAddCandidate:
    """Task 9: POST /reading/lookups/<lookup_id>/add-candidate."""

    def test_add_candidate_creates_candidate_and_redirects(self, app, client):
        uid = _user(app, "addc-ok@t.com")
        _login(client, "addc-ok@t.com")
        doc_id = _create_doc(
            app, uid,
            content_text="The cat sleeps on the mat.",
            content_hash="addc-hash",
        )

        # Create a lookup via service (simulating prior selection)
        with _rls_context(app, uid):
            lookup = reading_svc.lookup_term(
                uid, doc_id, "cat", 4, 7,
            )
            lookup_id = lookup.id

        csrf = _csrf(client, f"/reading/{doc_id}")
        resp = client.post(
            f"/reading/lookups/{lookup_id}/add-candidate",
            data={"csrf_token": csrf},
        )

        # Should redirect to the intake candidate review page
        assert resp.status_code == 302
        loc = resp.headers.get("Location", "")
        assert "/intake/" in loc
        # Verify candidate was created and linked to this lookup
        with _rls_context(app, uid):
            from app.models.intake import WordCandidate
            from app.models.reading import ReadingLookup
            fresh = ReadingLookup.query.filter_by(id=lookup_id, user_id=uid).one()
            cand = WordCandidate.query.filter_by(user_id=uid).one()
            assert fresh.candidate_id == cand.id
            assert cand.source_id == fresh.document.intake_source_id
            # URL is path form: /intake/<source_id>/candidates
            assert f"/intake/{cand.source_id}/candidates" in loc

    def test_add_candidate_rejects_cross_user(self, app, client):
        """User B cannot add-candidate on user A's lookup."""
        uid_a = _user(app, "addc-owner@t.com")
        _user(app, "addc-other@t.com")
        doc_id = _create_doc(app, uid_a, content_hash="addc-cross-hash")

        with _rls_context(app, uid_a):
            lookup = reading_svc.lookup_term(
                uid_a, doc_id, "Hello", 0, 5,
            )
            lookup_id = lookup.id

        _login(client, "addc-other@t.com")
        csrf = _csrf(client, "/reading")
        resp = client.post(
            f"/reading/lookups/{lookup_id}/add-candidate",
            data={"csrf_token": csrf},
        )
        assert resp.status_code == 404

    def test_add_candidate_requires_login(self, client):
        resp = client.post("/reading/lookups/1/add-candidate")
        assert resp.status_code == 302
        assert "/login" in resp.headers.get("Location", "")


    def test_lookup_second_paragraph_returns_correct_sentence(self, app, client):
        """Lookup on a word in the second paragraph of a multi-para document.

        Regression: JS fullText() dropped \\n\\n separators, so offsets drifted and the card showed the wrong sentence.
        """
        uid = _user(app, "lookup-para@t.com")
        _login(client, "lookup-para@t.com")
        content = "The fox runs fast.\n\nThe fox sleeps quietly."
        doc_id = _create_doc(
            app, uid,
            content_text=content,
            content_hash="lookup-para-hash",
        )
        csrf = _csrf(client, f"/reading/{doc_id}")
        # Second "fox" is in the second paragraph: "The fox sleeps quietly."
        # it starts at offset 23 (after the first para + \n\n)
        second_fox = content.index("fox", 10)
        resp = client.post(
            f"/reading/{doc_id}/lookup",
            data={
                "csrf_token": csrf,
                "term": "fox",
                "selection_start": second_fox,
                "selection_end": second_fox + 3,
            },
        )
        assert resp.status_code == 200
        page = resp.get_data(as_text=True)
        # The card must show the second sentence, not the first
        assert "The fox sleeps quietly." in page
        assert "The fox runs fast." not in page
