from __future__ import annotations

from dataclasses import dataclass
from io import BytesIO
from pathlib import Path

from pypdf import PdfReader
from pypdf.errors import PdfReadError


DEFAULT_MAX_BYTES = 25 * 1024 * 1024
DEFAULT_MAX_PAGES = 500
DEFAULT_MAX_CHARS = 2_000_000


class PdfParseError(ValueError):
    """Raised when a PDF cannot be parsed as a text-based document."""


class PdfTooLarge(PdfParseError):
    """Raised when the PDF bytes or extracted text exceed configured limits."""


class TooManyPages(PdfParseError):
    """Raised when a PDF exceeds the configured page limit."""


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
    max_pages: int = DEFAULT_MAX_PAGES,
    max_chars: int = DEFAULT_MAX_CHARS,
) -> ParsedDocument:
    if len(file_bytes) > max_bytes:
        raise PdfTooLarge(f"PDF '{filename}' exceeds maximum size of {max_bytes} bytes")

    try:
        reader = PdfReader(BytesIO(file_bytes))
    except (PdfReadError, OSError, ValueError) as exc:
        raise PdfParseError(f"Could not parse PDF '{filename}'") from exc

    try:
        page_count = len(reader.pages)
    except (PdfReadError, KeyError, TypeError, ValueError, OSError) as exc:
        raise PdfParseError(f"Could not parse PDF '{filename}'") from exc

    if page_count > max_pages:
        raise TooManyPages(f"PDF '{filename}' has {page_count} pages and exceeds maximum pages of {max_pages}")

    page_texts: list[str] = []
    total_chars = 0
    try:
        for page in reader.pages:
            page_text = page.extract_text() or ""
            if page_text.strip():
                page_texts.append(page_text.strip())
                total_chars += len(page_text.strip())
                if total_chars > max_chars:
                    raise PdfTooLarge(
                        f"PDF '{filename}' exceeds maximum text length of {max_chars} characters"
                    )
    except PdfTooLarge:
        raise
    except (PdfReadError, KeyError, TypeError, ValueError) as exc:
        raise PdfParseError(f"Could not extract text from PDF '{filename}'") from exc

    text = "\n\n".join(page_texts).strip()
    if not text:
        raise EmptyPdfText(f"PDF '{filename}' contains no extractable text")

    return ParsedDocument(
        title=_document_title(reader, filename),
        text=text,
        page_count=page_count,
    )


def _document_title(reader: PdfReader, filename: str) -> str:
    title = None
    try:
        title = reader.metadata.title if reader.metadata else None
    except (PdfReadError, ValueError):
        title = None

    if title and title.strip():
        return title.strip()
    return Path(filename).stem or filename
