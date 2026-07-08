from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class ContextSentence:
    sentence: str
    start: int
    end: int
    offset_matched: bool


_PAIRED_OPEN = {"(": ")", "[": "]", "{": "}", "“": "”", "‘": "’", "«": "»"}


def split_sentences(text: str, language_code: str) -> list[dict[str, Any]]:
    """把文本按句子边界切分，返回带 start/end 的句子列表。

    用于渲染阅读器逐句卡片，保留和 content_text 一致的 offset，
    点词查词时 offset 语义不变。
    """
    if not text:
        return []
    boundaries = _boundaries_for(language_code)
    sentences: list[dict[str, Any]] = []
    start = 0
    i = 0
    n = len(text)
    # Track paired delimiter depth so we don't split inside (parens) etc.
    open_stack: list[str] = []
    while i < n:
        ch = text[i]
        # Track paired delimiter nesting
        if ch in _PAIRED_OPEN:
            open_stack.append(ch)
        elif open_stack and ch == _PAIRED_OPEN[open_stack[-1]]:
            open_stack.pop()
        if ch in boundaries and not open_stack:
            end = i + 1
            # Gobble consecutive boundary characters into this sentence
            # so that "..." or "!!" don't fragment into tiny sentences.
            while end < n and text[end] in boundaries:
                end += 1
            s = _trim_sentence(text, start, end)
            if s:
                sentences.append({"text": s, "start": start, "end": end})
            start = end
            while start < n and text[start] in " \n":
                start += 1
            i = start
        elif ch == "\n" and i + 1 < n and text[i + 1] == "\n":
            if not open_stack and start < i:
                s = _trim_sentence(text, start, i)
                if s:
                    sentences.append({"text": s, "start": start, "end": i})
            i += 2
            start = i
            while start < n and text[start] in " \n":
                start += 1
            i = start
        else:
            i += 1
    # Trailing text after last boundary
    if start < n:
        s = _trim_sentence(text, start, n)
        if s:
            sentences.append({"text": s, "start": start, "end": n})
    return _merge_tiny_sentences(sentences)


def _merge_tiny_sentences(
    sentences: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """合并纯标点的微小句子到相邻句，避免单个 '.' 或 '..' 独立成卡片。"""
    if not sentences:
        return sentences
    # Define "tiny": sentence text contains only punctuation/whitespace
    def _is_tiny(t: str) -> bool:
        stripped = t.strip()
        if not stripped:
            return True
        return all(ch in ".,;:!?\"'()[]{}“”‘’…、。，．！？；："
                   for ch in stripped)

    merged: list[dict[str, Any]] = []
    for s in sentences:
        if _is_tiny(s["text"]):
            if merged:
                # Attach to previous sentence
                prev = merged[-1]
                prev["text"] = prev["text"] + s["text"]
                prev["end"] = s["end"]
            else:
                # First sentence is tiny — keep it alone (unlikely)
                merged.append(s)
        else:
            merged.append(s)
    return merged


def _trim_sentence(text: str, start: int, end: int) -> str:
    return text[start:end].strip()


def extract_context_sentence(
    text: str,
    selection_start: int,
    selection_end: int,
    language_code: str,
    *,
    expected_term: str | None = None,
    max_chars: int = 400,
) -> ContextSentence:
    offset_matched = _selection_matches(text, selection_start, selection_end, expected_term)
    target_start, target_end = selection_start, selection_end

    if expected_term and not offset_matched:
        match_start = _find_in_window(text, selection_start, selection_end, expected_term)
        if match_start is not None:
            target_start = match_start
            target_end = match_start + len(expected_term)

    sentence_start, sentence_end = _sentence_bounds(text, target_start, target_end, language_code)
    sentence_start, sentence_end = _truncate_bounds(
        sentence_start,
        sentence_end,
        target_start,
        target_end,
        max_chars,
    )

    return ContextSentence(
        sentence=text[sentence_start:sentence_end].strip(),
        start=sentence_start,
        end=sentence_end,
        offset_matched=offset_matched,
    )


def _selection_matches(
    text: str,
    selection_start: int,
    selection_end: int,
    expected_term: str | None,
) -> bool:
    if not 0 <= selection_start <= selection_end <= len(text):
        return False
    if expected_term is None:
        return True
    return text[selection_start:selection_end] == expected_term


def _find_in_window(
    text: str,
    selection_start: int,
    selection_end: int,
    expected_term: str,
) -> int | None:
    window_start = max(0, selection_start - 200)
    window_end = min(len(text), selection_end + 200)
    # Find the occurrence closest to the selection start, not the first
    # one in the window.  Otherwise repeated terms later in the document
    # would resolve to the earliest match and surface the wrong sentence.
    best_index = None
    best_distance = None
    search_from = window_start
    while True:
        index = text.find(expected_term, search_from, window_end)
        if index == -1:
            break
        distance = abs(index - selection_start)
        if best_distance is None or distance < best_distance:
            best_distance = distance
            best_index = index
        search_from = index + 1
    return best_index


def _sentence_bounds(
    text: str,
    target_start: int,
    target_end: int,
    language_code: str,
) -> tuple[int, int]:
    boundaries = _boundaries_for(language_code)
    start = max(0, min(target_start, len(text)))
    end_anchor = max(start, min(target_end, len(text)))

    # Walk backward to find sentence start.
    # Stop at terminal punctuation or a \n\n paragraph break.
    while start > 0:
        if text[start - 1] in boundaries:
            break
        if text[start - 1] == "\n" and start >= 2 and text[start - 2] == "\n":
            # We are at a \n\n boundary; stop here (don't include the \n)
            break
        start -= 1
    while start < len(text) and text[start].isspace():
        start += 1

    # Walk forward to find sentence end.
    # Stop at terminal punctuation or a \n\n paragraph break.
    end = end_anchor
    while end < len(text):
        if text[end] in boundaries:
            end += 1  # include the punctuation
            break
        if text[end] == "\n" and end + 1 < len(text) and text[end + 1] == "\n":
            # \n\n paragraph break; stop here (don't include the \n)
            break
        end += 1

    return start, end


def _boundaries_for(language_code: str) -> str:
    """Sentence boundary characters.

    Note: we deliberately exclude ``\n`` from the boundary set.  After
    ``_reflow_paragraphs`` the only newlines in content_text are the
    ``\n\n`` paragraph separators.  If ``\n`` were a boundary,
    ``_sentence_bounds`` would stop at the first ``\n`` of a ``\n\n``
    pair and truncate the sentence before the period.  Paragraph breaks
    are still respected because a period (or other terminal punctuation)
    almost always precedes the ``\n\n``.
    """
    if language_code in {"zh", "ja"}:
        # Include comma and semicolon as boundaries: Chinese PDF text
        # often lacks terminal periods but uses these to separate clauses.
        return "。！？，；"
    return ".!?"


def _truncate_bounds(
    sentence_start: int,
    sentence_end: int,
    target_start: int,
    target_end: int,
    max_chars: int,
) -> tuple[int, int]:
    if max_chars <= 0 or sentence_end - sentence_start <= max_chars:
        return sentence_start, sentence_end

    target_length = target_end - target_start
    if target_length >= max_chars:
        return target_start, target_end

    remaining = max_chars - target_length
    before = remaining // 2
    after = remaining - before

    start = max(sentence_start, target_start - before)
    end = min(sentence_end, target_end + after)

    if end - start < max_chars and start == sentence_start:
        end = min(sentence_end, start + max_chars)
    if end - start < max_chars and end == sentence_end:
        start = max(sentence_start, end - max_chars)

    return start, end
