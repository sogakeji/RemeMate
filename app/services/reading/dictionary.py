from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


SUPPORTED_LANGUAGES = frozenset({"zh", "en", "ja", "fr"})
LOWERCASE_LANGUAGES = frozenset({"en", "fr"})


class UnsupportedLanguage(ValueError):
    """Raised when dictionary lookup is requested for a non-MVP language."""


@dataclass(frozen=True)
class DictionaryResult:
    term: str
    normalized_term: str
    language_code: str
    part_of_speech: str | None = None
    meanings: list[str] = field(default_factory=list)
    examples: list[str] = field(default_factory=list)
    source: str | None = None
    confidence: float = 0.0
    found: bool = False

    def as_json(self) -> dict[str, Any]:
        return {
            "term": self.term,
            "normalized_term": self.normalized_term,
            "language_code": self.language_code,
            "part_of_speech": self.part_of_speech,
            "meanings": list(self.meanings),
            "examples": list(self.examples),
            "source": self.source,
            "confidence": self.confidence,
            "found": self.found,
        }


class Dictionary:
    def __init__(self, data_dir: str | os.PathLike[str] | None = None):
        self.data_dir = Path(data_dir or os.environ.get("DICTIONARY_DATA_DIR", "/srv/rememate-data/dictionaries"))

    def lookup(self, language_code: str, term: str) -> DictionaryResult:
        if language_code not in SUPPORTED_LANGUAGES:
            raise UnsupportedLanguage(f"Unsupported dictionary language: {language_code}")

        normalized_term = self._normalize(language_code, term)
        entries = self._load_entries(language_code)
        if not entries:
            return self._not_found(language_code, term, normalized_term)

        entry = entries.get(normalized_term)
        if not isinstance(entry, dict):
            return self._not_found(language_code, term, normalized_term)

        meanings = entry.get("meanings") or []
        examples = entry.get("examples") or []
        return DictionaryResult(
            term=term,
            normalized_term=normalized_term,
            language_code=language_code,
            part_of_speech=entry.get("part_of_speech"),
            meanings=list(meanings) if isinstance(meanings, list) else [],
            examples=list(examples) if isinstance(examples, list) else [],
            source=entry.get("source"),
            confidence=float(entry.get("confidence", 0.0)),
            found=True,
        )

    def _normalize(self, language_code: str, term: str) -> str:
        normalized = term.strip()
        if language_code in LOWERCASE_LANGUAGES:
            return normalized.lower()
        return normalized

    def _load_entries(self, language_code: str) -> dict[str, Any]:
        entries_path = self.data_dir / language_code / "entries.json"
        if not entries_path.exists():
            return {}
        with entries_path.open("r", encoding="utf-8") as handle:
            entries = json.load(handle)
        return entries if isinstance(entries, dict) else {}

    def _not_found(self, language_code: str, term: str, normalized_term: str) -> DictionaryResult:
        return DictionaryResult(
            term=term,
            normalized_term=normalized_term,
            language_code=language_code,
            found=False,
        )
