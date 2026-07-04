from dataclasses import dataclass


@dataclass(frozen=True)
class ContextSentence:
    sentence: str
    start: int
    end: int
    offset_matched: bool


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
    index = text.find(expected_term, window_start, window_end)
    if index == -1:
        return None
    return index


def _sentence_bounds(
    text: str,
    target_start: int,
    target_end: int,
    language_code: str,
) -> tuple[int, int]:
    boundaries = _boundaries_for(language_code)
    start = max(0, min(target_start, len(text)))
    end_anchor = max(start, min(target_end, len(text)))

    while start > 0 and text[start - 1] not in boundaries:
        start -= 1
    while start < len(text) and text[start].isspace():
        start += 1

    end = end_anchor
    while end < len(text) and text[end] not in boundaries:
        end += 1
    if end < len(text):
        end += 1

    return start, end


def _boundaries_for(language_code: str) -> str:
    if language_code in {"zh", "ja"}:
        return "。！？\n"
    return ".!?\n"


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
