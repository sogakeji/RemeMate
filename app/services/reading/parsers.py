from __future__ import annotations

from dataclasses import dataclass
from io import BytesIO
from pathlib import Path

from pypdf import PdfReader
from pypdf.errors import PdfReadError


DEFAULT_MAX_BYTES = 25 * 1024 * 1024
DEFAULT_MAX_PAGES = 500
DEFAULT_MAX_CHARS = 300_000


class PdfParseError(ValueError):
    """Raised when a PDF cannot be parsed as a text-based document."""


class PdfTooLarge(PdfParseError):
    """Raised when the PDF bytes exceed configured limits."""


class TooManyPages(PdfParseError):
    """Raised when a PDF exceeds the configured page limit (only for non-split mode)."""


class EmptyPdfText(PdfParseError):
    """Raised when a PDF contains no extractable text."""


@dataclass(frozen=True)
class ParsedDocument:
    title: str
    text: str
    page_count: int


def parse_pdf_bytes(
    file_bytes: bytes,
    filename: str,
    *,
    max_bytes: int = DEFAULT_MAX_BYTES,
    max_chars: int = DEFAULT_MAX_CHARS,
) -> ParsedDocument:
    """Parse a text-based PDF, returning a single ParsedDocument.

    Raises PdfTooLarge if the extracted text exceeds max_chars.
    For large PDFs where you want automatic splitting, use parse_pdf_bytes_multi.
    """
    reader = _open_pdf(file_bytes, filename, max_bytes=max_bytes)
    title = _document_title(reader, filename)
    pages = _extract_pages(reader, filename)
    chunks = list(_split_pages(pages, max_chars=max_chars, filename=filename))
    if not chunks:
        raise EmptyPdfText(f"PDF '{filename}' contains no extractable text")
    if len(chunks) > 1:
        raise PdfTooLarge(
            f"PDF '{filename}' 文本超过 {max_chars} 字符（{len(chunks)} 段），"
            f"系统会自动切分为多篇阅读材料。请重试上传。"
        )
    return ParsedDocument(title=title, text=chunks[0], page_count=len(pages))


def parse_pdf_bytes_multi(
    file_bytes: bytes,
    filename: str,
    *,
    max_bytes: int = DEFAULT_MAX_BYTES,
    max_chars: int = DEFAULT_MAX_CHARS,
) -> list[ParsedDocument]:
    """Parse a text-based PDF, splitting into multiple chunks if it exceeds max_chars.

    Each chunk respects page boundaries — pages are never split in half.
    Returns a list of ParsedDocument with titles like 'Title (Part 1/3)'.
    """
    reader = _open_pdf(file_bytes, filename, max_bytes=max_bytes)
    title = _document_title(reader, filename)
    pages = _extract_pages(reader, filename)
    chunks = list(_split_pages(pages, max_chars=max_chars, filename=filename))
    if not chunks:
        raise EmptyPdfText(f"PDF '{filename}' contains no extractable text")

    if len(chunks) == 1:
        return [ParsedDocument(title=title, text=chunks[0], page_count=len(pages))]

    total = len(chunks)
    return [
        ParsedDocument(
            title=f"{title} (第 {i + 1}/{total} 部分)",
            text=chunk,
            page_count=len(pages),  # original page count, not chunk page count
        )
        for i, chunk in enumerate(chunks)
    ]


def _open_pdf(file_bytes, filename, *, max_bytes=DEFAULT_MAX_BYTES):
    if len(file_bytes) > max_bytes:
        raise PdfTooLarge(
            f"PDF '{filename}' 超过 {max_bytes // 1024 // 1024}MB，请拆分上传"
        )
    try:
        return PdfReader(BytesIO(file_bytes))
    except (PdfReadError, OSError, ValueError) as exc:
        raise PdfParseError(f"无法解析 PDF '{filename}'") from exc


def _extract_pages(reader, filename):
    pages = []
    try:
        for page in reader.pages:
            text = page.extract_text() or ""
            if text.strip():
                pages.append(text.strip())
    except (PdfReadError, KeyError, TypeError, ValueError) as exc:
        raise PdfParseError(f"无法从 PDF '{filename}' 提取文本") from exc
    return pages


def _split_pages(pages, *, max_chars, filename):
    """Yield text chunks, respecting page boundaries and max_chars."""
    chunk = ""
    for page_text in pages:
        if chunk and len(chunk) + len(page_text) + 2 > max_chars:
            yield chunk.strip()
            chunk = page_text
        else:
            chunk = (chunk + "\n\n" + page_text) if chunk else page_text
    if chunk.strip():
        yield chunk.strip()


def _document_title(reader: PdfReader, filename: str) -> str:
    title = None
    try:
        title = reader.metadata.title if reader.metadata else None
    except (PdfReadError, ValueError):
        title = None

    if title and title.strip():
        return title.strip()
    return Path(filename).stem or filename
