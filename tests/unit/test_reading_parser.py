import pytest
from pypdf import PdfWriter
from pypdf.errors import PdfReadError
from pypdf.generic import DecodedStreamObject, DictionaryObject, NameObject

import app.services.reading.parsers as parsers
from app.services.reading.parsers import (
    EmptyPdfText,
    PdfParseError,
    PdfTooLarge,
    TooManyPages,
    parse_pdf_bytes,
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

    with pytest.raises(PdfTooLarge, match="exceeds maximum size"):
        parse_pdf_bytes(pdf_bytes, "large.pdf", max_bytes=len(pdf_bytes) - 1)


def test_page_limit_raises_too_many_pages():
    pdf_bytes = _make_pdf_bytes(texts=["Page one", "Page two"])

    with pytest.raises(TooManyPages, match="exceeds maximum pages"):
        parse_pdf_bytes(pdf_bytes, "many-pages.pdf", max_pages=1)


def test_char_limit_raises_pdf_too_large():
    pdf_bytes = _make_pdf_bytes(texts=["This text is too long"])

    with pytest.raises(PdfTooLarge, match="exceeds maximum text length"):
        parse_pdf_bytes(pdf_bytes, "too-long.pdf", max_chars=5)


def test_page_tree_parse_errors_raise_pdf_parse_error(monkeypatch):
    pdf_bytes = _make_pdf_bytes(texts=["Hello reader"])

    class BrokenReader:
        @property
        def pages(self):
            raise PdfReadError("broken page tree")

    monkeypatch.setattr(parsers, "PdfReader", lambda _: BrokenReader())

    with pytest.raises(PdfParseError, match="Could not parse PDF 'broken.pdf'"):
        parse_pdf_bytes(pdf_bytes, "broken.pdf")


