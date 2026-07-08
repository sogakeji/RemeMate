import pytest
from pypdf import PdfWriter
from pypdf.errors import PdfReadError
from pypdf.generic import DecodedStreamObject, DictionaryObject, NameObject

import app.services.reading.parsers as parsers
from app.services.reading.parsers import (
    ContentQualityError,
    EmptyPdfText,
    PdfParseError,
    PdfTooLarge,
    parse_pdf_bytes,
    parse_pdf_bytes_multi,
    validate_content_quality,
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


# ---- validate_content_quality ----


def test_quality_empty_text_raises():
    with pytest.raises(ContentQualityError, match="全空"):
        validate_content_quality("   ", "zh")


def test_quality_garbled_text_raises():
    # >5% replacement chars should trigger the garbled check (>50 chars required)
    garbled = "Hello World. " * 5 + "�" * 6  # ~80 chars, ~7% replacement
    with pytest.raises(ContentQualityError, match="乱码"):
        validate_content_quality(garbled, "en")


def test_quality_too_short_raises():
    with pytest.raises(ContentQualityError, match="过短"):
        validate_content_quality("Hi.", "en")


def test_quality_cjk_no_punctuation_raises():
    # Chinese text without any CJK punctuation
    text = "这是一段没有标点符号的中文文本" * 5
    assert len(text) >= 50
    with pytest.raises(ContentQualityError, match="缺少中文标点"):
        validate_content_quality(text, "zh")


def test_quality_cjk_with_punctuation_passes():
    text = "这是一段有标点的中文文本。" * 5
    validate_content_quality(text, "zh")  # does not raise


def test_quality_english_passes():
    text = "This is a valid English paragraph with proper content. " * 5
    validate_content_quality(text, "en")  # does not raise


def test_quality_japanese_with_punctuation_passes():
    text = "これは日本語のテキストです。ちゃんと句読点もあります。" * 5
    validate_content_quality(text, "ja")  # does not raise


def _make_pdf_bytes_lines(*, lines: list[str], title: str | None = None) -> bytes:
    """Build a PDF whose page text contains explicit newlines (line-wrapped layout).

    pypdf's `add_blank_page` + content stream only renders one line per page,
    so to simulate multi-line page text we put each line on its own page and
    let the extractor join them with `\n\n`. That's not ideal, but for the
    reflow test we instead call `_reflow_paragraphs` directly on a synthetic
    string with embedded newlines.
    """
    # Not used by reflow tests; they call _reflow_paragraphs directly.
    return _make_pdf_bytes(texts=["\n".join(lines)], title=title)


def test_reflow_merges_wrapped_lines_into_paragraph():
    from app.services.reading.parsers import _reflow_paragraphs

    raw = "The quick brown\nfox jumps over\nthe lazy dog.\n\nSecond para here."
    out = _reflow_paragraphs(raw)
    assert "The quick brown fox jumps over the lazy dog." in out
    assert "Second para here." in out
    # 段间仍是 \n\n
    assert "\n\n" in out


def test_reflow_joins_cjk_wrapped_lines_without_space_for_chinese_and_japanese():
    from app.services.reading.parsers import _reflow_paragraphs

    zh = _reflow_paragraphs("我喜欢学\n习中文。魔\n鬼来了。", language_code="zh")
    ja = _reflow_paragraphs("日本\n語を読\nむ。", language_code="ja")

    assert zh == "我喜欢学习中文。魔鬼来了。"
    assert ja == "日本語を読む。"


def test_reflow_keeps_spaces_for_non_cjk_languages():
    from app.services.reading.parsers import _reflow_paragraphs

    out = _reflow_paragraphs("The quick\nbrown fox.", language_code="en")

    assert out == "The quick brown fox."


def test_reflow_handles_hyphenated_line_break():
    from app.services.reading.parsers import _reflow_paragraphs

    raw = "exam-\nple word"
    out = _reflow_paragraphs(raw)
    assert "example word" in out
    assert "exam-\n" not in out


def test_reflow_strips_trailing_blank_lines():
    from app.services.reading.parsers import _reflow_paragraphs

    out = _reflow_paragraphs("hello\n\n\n\nworld")
    assert out.startswith("hello")
    assert out.endswith("world")
    assert "hello\n\nworld" == out


def test_reflow_normalizes_crlf():
    from app.services.reading.parsers import _reflow_paragraphs

    out = _reflow_paragraphs("line one\r\nline two\r\rpara two")
    assert "line one line two" in out
    assert "para two" in out


def test_reflow_empty_returns_empty():
    from app.services.reading.parsers import _reflow_paragraphs

    assert _reflow_paragraphs("") == ""
    assert _reflow_paragraphs("   \n  \n  ") == ""
