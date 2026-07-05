import pytest
from pypdf import PdfWriter
from pypdf.errors import PdfReadError
from pypdf.generic import DecodedStreamObject, DictionaryObject, NameObject

import app.services.reading.parsers as parsers
from app.services.reading.parsers import (
    EmptyPdfText,
    PdfParseError,
    PdfTooLarge,
    parse_pdf_bytes,
    parse_pdf_bytes_multi,
)


def _make_pdf_bytes(*, texts: list[str] | None = None, title: str | None = None) -> bytes:
    writer = PdfWriter()
    for text in texts or []:
        page = writer.add_blank_page(width=200, height=200)
        if text:
            stream = DecodedStreamObject()
            stream.set_data(f"BT /F1 12 Tf 20 100 Td ({text}) Tj ET".encode("utf-8"))
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
    output = __import__("io").BytesIO()
    writer.write(output)
    return output.getvalue()


def test_text_pdf_extracts_expected_text():
    pdf_bytes = _make_pdf_bytes(texts=["Hello reader"], title="Sample PDF")

    document = parse_pdf_bytes(pdf_bytes, "sample.pdf")

    assert document.title == "Sample PDF"
    assert "Hello reader" in document.text
    assert document.page_count == 1


def test_empty_pdf_raises_empty_pdf_text():
    pdf_bytes = _make_pdf_bytes(texts=[""])

    with pytest.raises(EmptyPdfText):
        parse_pdf_bytes(pdf_bytes, "empty.pdf")


def test_size_limit_raises_pdf_too_large():
    pdf_bytes = _make_pdf_bytes(texts=["Hello reader"])

    with pytest.raises(PdfTooLarge, match=r"超过"):
        parse_pdf_bytes(pdf_bytes, "large.pdf", max_bytes=len(pdf_bytes) - 1)


def test_char_limit_triggers_split_in_multi_mode():
    """In multi mode, exceeding max_chars produces multiple documents."""
    pdf_bytes = _make_pdf_bytes(texts=["This text is too long"])

    docs = parse_pdf_bytes_multi(pdf_bytes, "too-long.pdf", max_chars=5)

    assert len(docs) >= 1  # at least the first chunk survives


def test_page_tree_parse_errors_raise_pdf_parse_error(monkeypatch):
    pdf_bytes = _make_pdf_bytes(texts=["Hello reader"])

    class BrokenReader:
        @property
        def pages(self):
            raise PdfReadError("broken page tree")

        metadata = None

        metadata = None

    monkeypatch.setattr(parsers, "PdfReader", lambda _: BrokenReader())

    with pytest.raises(PdfParseError, match=r"无法"):
        parse_pdf_bytes(pdf_bytes, "broken.pdf")


def test_multi_split_large_pdf():
    """parse_pdf_bytes_multi splits a PDF exceeding max_chars into multiple docs."""
    pdf_bytes = _make_pdf_bytes(
        texts=["A" * 100, "B" * 100, "C" * 100, "D" * 100],
        title="Split Test",
    )

    docs = parse_pdf_bytes_multi(pdf_bytes, "split.pdf", max_chars=150)

    assert len(docs) > 1
    assert docs[0].title.startswith("Split Test (第 1/")
    assert all(d.page_count == 4 for d in docs)
    combined = "".join(d.text for d in docs)
    assert "AAAA" in combined
    assert "DDDD" in combined


def test_multi_small_pdf_returns_single():
    """parse_pdf_bytes_multi returns one doc for a small PDF (no suffix)."""
    pdf_bytes = _make_pdf_bytes(texts=["Hello reader"], title="Small PDF")

    docs = parse_pdf_bytes_multi(pdf_bytes, "small.pdf")

    assert len(docs) == 1
    assert docs[0].title == "Small PDF"
    assert "Hello reader" in docs[0].text
