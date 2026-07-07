from __future__ import annotations

import re
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


class ContentQualityError(PdfParseError):
    """Raised when extracted text fails the quality check."""


_IS_CJK = {"zh", "ja"}
_CJK_PUNCT = "。，！？；：、"
_REPLACEMENT_CHAR = "�"


def validate_content_quality(text: str, language_code: str) -> None:
    stripped = text.strip()
    if not stripped:
        raise ContentQualityError("PDF 提取文本全空，可能是扫描件或图片型 PDF")
    replacement_ratio = stripped.count(_REPLACEMENT_CHAR) / max(len(stripped), 1)
    if replacement_ratio > 0.05:
        raise ContentQualityError(
            f"PDF 提取文本乱码比例过高（{replacement_ratio:.0%}），可能是编码不兼容或非文本型 PDF"
        )
    if len(stripped) < 50:
        raise ContentQualityError(f"PDF 提取文本仅 {len(stripped)} 字符，内容过短")
    if language_code in _IS_CJK and not any(ch in stripped for ch in _CJK_PUNCT):
        raise ContentQualityError(
            "PDF 提取文本中缺少中文标点（。，！？等），可能不是中文/日文文档"
        )


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
                pages.append(_reflow_paragraphs(text).strip())
    except (PdfReadError, KeyError, TypeError, ValueError) as exc:
        raise PdfParseError(f"无法从 PDF '{filename}' 提取文本") from exc
    return pages


def _reflow_paragraphs(text: str) -> str:
    """把 PDF 版式行重排成自然段。

    PDF 文本抽取出来的硬换行是版式行（页面宽度折行），不是语义段落。
    本函数：
    - 统一换行符。
    - 按 blank-line（≥2 个换行 / 全空白行）切成段。
    - 段内单换行合并成空格；处理行尾断词连字符（拉丁字母词）。
    - 段间用 ``\\n\\n`` 重新拼接。
    返回重排后的纯文本，offset 仍按单一字符串计算，下游不变。
    """
    if not text:
        return ""
    # 统一换行
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    # 按「连续空白行」切段（一个以上空行算段界）
    paragraphs: list[str] = []
    for block in re.split(r"\n\s*\n", text):
        block = block.strip()
        if not block:
            continue
        # 段内逐行合并
        lines = [ln.strip() for ln in block.split("\n")]
        merged = ""
        for ln in lines:
            if not ln:
                continue
            if merged:
                # 断词连字符：merged 以「字母-」结尾、ln 以字母开头 → 去连字符拼接
                if len(merged) >= 2 and merged[-1] == "-" and merged[-2].isalpha() and ln[:1].isalpha():
                    merged = merged[:-1] + ln
                else:
                    merged = merged + " " + ln
            else:
                merged = ln
        if merged:
            paragraphs.append(merged)
    return "\n\n".join(paragraphs)


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
