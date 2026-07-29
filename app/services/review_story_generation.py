"""Provider-facing generation contract for private review stories."""
from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
import json
import re
from typing import Any
import unicodedata

from app.services import llm
from app.services.review_stories import (
    DailyReviewStorySummary,
    ReviewStoryTermSnapshot,
)


_LANGUAGE_NAMES = {
    "fr": "French",
    "en": "English",
    "ja": "Japanese",
    "de": "German",
    "es": "Spanish",
    "ru": "Russian",
    "zh": "Chinese",
}
_COMMON_APOSTROPHES = str.maketrans(
    {"’": "'", "‘": "'", "ʼ": "'", "＇": "'"}
)
_WHITESPACE = re.compile(r"\s+")
_HAN = re.compile(r"[\u3400-\u9fff]")
_JAPANESE = re.compile(r"[\u3040-\u30ff\u3400-\u9fff]")
_CYRILLIC = re.compile(r"[\u0400-\u04ff]")
_LATIN_CHAR = re.compile(r"[A-Za-z\u00c0-\u024f]")
_HTML_TAG = re.compile(r"<[^>]+>")
_MARKDOWN = re.compile(
    r"(?:\*\*|__|`|\[[^\]]+\]\([^)]+\)|(?:^|\n)\s{0,3}(?:#{1,6}\s|[-*+]\s|\d+\.\s))"
)


class ReviewStoryContractError(ValueError):
    """Stable provider-result failure exposed to the RS2 orchestrator."""

    def __init__(self, code: str):
        super().__init__(code)
        self.code = code


@dataclass(frozen=True)
class ReviewStoryText:
    target: str
    translation: str


@dataclass(frozen=True)
class ReviewStoryTermAnchor:
    key: str
    target_form: str
    translation_form: str


@dataclass(frozen=True)
class ReviewStorySentence:
    target: str
    translation: str
    terms: tuple[ReviewStoryTermAnchor, ...]


@dataclass(frozen=True)
class ValidatedReviewStory:
    title: ReviewStoryText
    sentences: tuple[ReviewStorySentence, ...]


@dataclass(frozen=True)
class ReviewStoryAttemptResult:
    story: ValidatedReviewStory | None
    error_code: str | None
    prompt_tokens: int
    completion_tokens: int
    provider: str | None
    model: str | None


def build_review_story_messages(
    *,
    target_language: str,
    feedback_language: str,
    terms: tuple[ReviewStoryTermSnapshot, ...],
) -> tuple[dict[str, str], dict[str, str]]:
    """Build the deterministic, provider-safe review-story request."""
    if not 3 <= len(terms) <= 5:
        raise ValueError("review story requires 3 to 5 terms")
    expected_keys = [f"t{i}" for i in range(1, len(terms) + 1)]
    actual_keys = [term.key for term in terms]
    if actual_keys != expected_keys:
        raise ValueError("review story term keys must be consecutive")

    target_name = _LANGUAGE_NAMES[target_language]
    feedback_name = _LANGUAGE_NAMES[feedback_language]
    payload = json.dumps(
        [term.as_provider_dict() for term in terms],
        ensure_ascii=False,
        separators=(",", ":"),
    )
    output_schema = json.dumps(
        {
            "title": {"target": "...", "translation": "..."},
            "sentences": [
                {
                    "target": "...",
                    "translation": "...",
                    "terms": [
                        {
                            "key": "t1",
                            "target_form": "...",
                            "translation_form": "...",
                        }
                    ],
                }
            ],
        },
        separators=(",", ":"),
    )
    return (
        {
            "role": "system",
            "content": (
                f"You write short {target_name} stories for language learners "
                f"with {feedback_name} translations."
            ),
        },
        {
            "role": "user",
            "content": (
                f"Write one coherent everyday story in {target_name} with 4 to 6 "
                f"short sentences and a {feedback_name} translation for each. "
                "Outside the required terms, use simple, natural, high-frequency "
                "language. Avoid rare idioms and complex nested sentences. "
                "Return JSON only, with no Markdown or extra fields. Use each "
                "input key exactly once in a terms anchor. target_form must be "
                "the natural inflected form present in its target sentence; "
                "translation_form must be the corresponding phrase present in "
                "the translated sentence.\n"
                f"OUTPUT_SCHEMA_JSON={output_schema}\n"
                f"INPUT_TERMS_JSON={payload}"
            ),
        },
    )


def generate_review_story_once(
    summary: DailyReviewStorySummary,
) -> ReviewStoryAttemptResult:
    """Make exactly one logical provider attempt with no database side effects."""
    terms = tuple(target.snapshot for target in summary.targets)
    messages = build_review_story_messages(
        target_language=summary.target_language,
        feedback_language=summary.feedback_language,
        terms=terms,
    )
    try:
        provider_result = llm.chat(messages, task="general", json_mode=True)
    except llm.AllProvidersDown:
        return ReviewStoryAttemptResult(
            story=None,
            error_code="provider_unavailable",
            prompt_tokens=0,
            completion_tokens=0,
            provider=None,
            model=None,
        )

    try:
        story = validate_review_story_result(
            provider_result.content,
            target_language=summary.target_language,
            feedback_language=summary.feedback_language,
            expected_keys=tuple(term.key for term in terms),
        )
    except ReviewStoryContractError as exc:
        return ReviewStoryAttemptResult(
            story=None,
            error_code=exc.code,
            prompt_tokens=provider_result.prompt_tokens,
            completion_tokens=provider_result.completion_tokens,
            provider=provider_result.provider,
            model=provider_result.model,
        )
    return ReviewStoryAttemptResult(
        story=story,
        error_code=None,
        prompt_tokens=provider_result.prompt_tokens,
        completion_tokens=provider_result.completion_tokens,
        provider=provider_result.provider,
        model=provider_result.model,
    )


def validate_review_story_result(
    raw_content: str,
    *,
    target_language: str,
    feedback_language: str,
    expected_keys: tuple[str, ...],
) -> ValidatedReviewStory:
    """Parse one provider result into the public immutable story shape."""
    if len(raw_content) > 12_000:
        raise ReviewStoryContractError("result_too_large")
    try:
        data: dict[str, Any] = json.loads(raw_content)
    except (json.JSONDecodeError, TypeError) as exc:
        raise ReviewStoryContractError("invalid_json") from exc

    if not isinstance(data, dict) or set(data) != {"title", "sentences"}:
        raise ReviewStoryContractError("invalid_schema")
    title_data = data["title"]
    sentences_data = data["sentences"]
    if not isinstance(title_data, dict) or set(title_data) != {
        "target", "translation",
    }:
        raise ReviewStoryContractError("invalid_schema")
    if not _valid_text(title_data["target"], max_length=120):
        raise ReviewStoryContractError("invalid_schema")
    if not _valid_text(title_data["translation"], max_length=120):
        raise ReviewStoryContractError("invalid_schema")
    if not isinstance(sentences_data, list) or not 4 <= len(sentences_data) <= 6:
        raise ReviewStoryContractError("invalid_schema")
    for sentence in sentences_data:
        if not isinstance(sentence, dict) or set(sentence) != {
            "target", "translation", "terms",
        }:
            raise ReviewStoryContractError("invalid_schema")
        if not _valid_text(sentence["target"]) or not _valid_text(
            sentence["translation"]
        ):
            raise ReviewStoryContractError("invalid_schema")
        if not _valid_anchors(sentence["terms"]):
            raise ReviewStoryContractError("invalid_schema")
        normalized_target = _normalize_visible_text(sentence["target"])
        normalized_translation = _normalize_visible_text(sentence["translation"])
        for anchor in sentence["terms"]:
            if (
                _normalize_visible_text(anchor["target_form"]) not in normalized_target
                or _normalize_visible_text(anchor["translation_form"])
                not in normalized_translation
            ):
                raise ReviewStoryContractError("term_anchor_mismatch")

    actual_keys = [
        anchor["key"]
        for sentence in sentences_data
        for anchor in sentence["terms"]
    ]
    if Counter(actual_keys) != Counter(expected_keys) or len(actual_keys) != len(
        expected_keys
    ):
        raise ReviewStoryContractError("missing_or_duplicate_term")

    target_text = " ".join(
        [title_data["target"]]
        + [sentence["target"] for sentence in sentences_data]
    )
    translation_text = " ".join(
        [title_data["translation"]]
        + [sentence["translation"] for sentence in sentences_data]
    )
    visible_texts = [target_text, translation_text]
    visible_texts.extend(
        anchor[field]
        for sentence in sentences_data
        for anchor in sentence["terms"]
        for field in ("target_form", "translation_form")
    )
    if any(
        _HTML_TAG.search(value) or _MARKDOWN.search(value)
        for value in visible_texts
    ):
        raise ReviewStoryContractError("invalid_schema")

    if not _matches_writing_system(target_text, target_language):
        raise ReviewStoryContractError("invalid_schema")
    if not _matches_writing_system(translation_text, feedback_language):
        raise ReviewStoryContractError("invalid_schema")

    title = ReviewStoryText(
        target=data["title"]["target"],
        translation=data["title"]["translation"],
    )
    sentences = tuple(
        ReviewStorySentence(
            target=sentence["target"],
            translation=sentence["translation"],
            terms=tuple(
                ReviewStoryTermAnchor(
                    key=anchor["key"],
                    target_form=anchor["target_form"],
                    translation_form=anchor["translation_form"],
                )
                for anchor in sentence["terms"]
            ),
        )
        for sentence in data["sentences"]
    )
    return ValidatedReviewStory(title=title, sentences=sentences)


def _valid_text(value: Any, *, max_length: int | None = None) -> bool:
    if not isinstance(value, str) or not value.strip():
        return False
    return max_length is None or len(value) <= max_length


def _valid_anchors(value: Any) -> bool:
    if not isinstance(value, list):
        return False
    for anchor in value:
        if not isinstance(anchor, dict) or set(anchor) != {
            "key", "target_form", "translation_form",
        }:
            return False
        if not all(
            _valid_text(anchor[field])
            for field in ("key", "target_form", "translation_form")
        ):
            return False
    return True


def _normalize_visible_text(value: str) -> str:
    normalized = unicodedata.normalize("NFKC", value)
    normalized = normalized.translate(_COMMON_APOSTROPHES).casefold()
    return _WHITESPACE.sub(" ", normalized).strip()


def _matches_writing_system(value: str, language: str) -> bool:
    if language == "zh":
        return bool(_HAN.search(value))
    if language == "ja":
        return bool(_JAPANESE.search(value))
    if language == "ru":
        return bool(_CYRILLIC.search(value))
    if language not in {"fr", "en", "de", "es"}:
        return False
    letters = [character for character in value if character.isalpha()]
    if not letters:
        return False
    latin_count = sum(bool(_LATIN_CHAR.fullmatch(char)) for char in letters)
    return latin_count / len(letters) >= 0.6
