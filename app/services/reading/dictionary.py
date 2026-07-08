from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

try:
    import lemminflect  # noqa: F401
    _HAS_LEMMINFLECT = True
except ImportError:
    _HAS_LEMMINFLECT = False


SUPPORTED_LANGUAGES = frozenset({"zh", "en", "ja", "fr"})
LOWERCASE_LANGUAGES = frozenset({"en", "fr"})
_CJK_SPACE_RE = re.compile(
    r"([\u3040-\u30ff\u3400-\u9fff\uf900-\ufaff])"
    r"[ \t\u00a0\u3000]+"
    r"([\u3040-\u30ff\u3400-\u9fff\uf900-\ufaff])"
)

# Simple suffix-stripping rules for English lemmatization fallback.
# Order matters: longer suffixes first to avoid partial matches.
_SUFFIX_RULES: list[tuple[str, str]] = [
    ("nning", ""),
    ("nned", ""),
    ("iest", "y"),
    ("iness", "y"),
    ("ities", "ity"),
    ("fully", "ful"),
    ("ally", "al"),
    ("ves", "f"),
    ("ies", "y"),
    ("ied", "y"),
    ("ings", ""),
    ("ing", ""),
    ("est", ""),
    ("est", "e"),
    ("er", ""),
    ("er", "e"),
    ("ed", ""),
    ("ed", "e"),
    ("'s", ""),
    ("s'", ""),
    ("s", ""),
    ("ly", ""),
    ("ment", ""),
    ("tion", "te"),
    ("sion", "de"),
    ("or", "our"),
    ("ise", "ize"),
]


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
        self._entry_cache: dict[str, dict[str, Any]] = {}

    def lookup(self, language_code: str, term: str) -> DictionaryResult:
        if language_code not in SUPPORTED_LANGUAGES:
            raise UnsupportedLanguage(f"Unsupported dictionary language: {language_code}")

        normalized_term = self._normalize(language_code, term)
        entries = self._load_entries(language_code)

        if entries:
            # Try exact match first, then lemmatized forms for English
            candidates = [normalized_term]
            if language_code in LOWERCASE_LANGUAGES:
                candidates.extend(self._lemmatize(term))

            for c in candidates:
                e = entries.get(c)
                if isinstance(e, dict):
                    return self._result(term, c, language_code, e)

        # Online fallback for all supported languages
        online = self._fetch_online(language_code, term)
        if online is not None:
            return online

        return self._not_found(language_code, term, normalized_term)

    def _result(self, term, normalized_term, language_code, entry) -> DictionaryResult:
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
            confidence=self._coerce_confidence(entry.get("confidence", 0.0)),
            found=True,
        )

    def _lemmatize(self, term: str) -> list[str]:
        """Return candidate lemmas for an English word.

        Tries lemminflect (rule-based, no corpus) first, falls back to
        simple suffix stripping.
        """
        candidates = []
        stripped = term.strip().lower()

        if _HAS_LEMMINFLECT:
            for pos in ("NOUN", "VERB", "ADJ", "ADV"):
                lemmas = lemminflect.getLemma(stripped, pos)
                if lemmas:
                    for lm in lemmas:
                        if lm != stripped and lm not in candidates:
                            candidates.append(lm)

        # Always append suffix-stripped forms as fallback
        for suffix, replacement in _SUFFIX_RULES:
            if stripped.endswith(suffix) and len(stripped) > len(suffix) + 2:
                base = stripped[: -len(suffix)] + replacement
                if base != stripped and base not in candidates:
                    candidates.append(base)

        return candidates

    def _fetch_online(self, language_code: str, term: str) -> DictionaryResult | None:
        """Dispatch to language-specific online fallback. Returns None if
        no API is available for the language (caller should fall back to
        ``_not_found``)."""
        # TODO: re-enable after local dict validation
        if False and language_code == "en":
            return self._online_en(term)
        if False and language_code == "ja":
            return self._online_ja(term)
        return None

    def _online_en(self, term: str) -> DictionaryResult:
        """Free Dictionary API."""
        import urllib.request
        import urllib.error

        normalized = term.strip().lower()
        url = f"https://api.dictionaryapi.dev/api/v2/entries/en/{normalized}"

        try:
            req = urllib.request.Request(url, headers={"User-Agent": "RemeMate/1.0"})
            with urllib.request.urlopen(req, timeout=5) as resp:
                data = json.loads(resp.read().decode("utf-8"))
        except (urllib.error.URLError, urllib.error.HTTPError,
                json.JSONDecodeError, OSError, TimeoutError):
            return self._not_found("en", term, normalized)

        if not isinstance(data, list) or not data:
            return self._not_found("en", term, normalized)

        entry = data[0]
        if not isinstance(entry, dict):
            return self._not_found("en", term, normalized)

        meanings: list[str] = []
        examples: list[str] = []
        pos_set: set[str] = set()

        for m in entry.get("meanings") or []:
            pos = m.get("partOfSpeech", "")
            if pos:
                pos_set.add(pos)
            for d in m.get("definitions") or []:
                definition = (d.get("definition") or "").strip()
                if definition:
                    meanings.append(definition)
                example = (d.get("example") or "").strip()
                if example and example not in examples:
                    examples.append(example)

        if not meanings:
            return self._not_found("en", term, normalized)

        return DictionaryResult(
            term=term, normalized_term=normalized, language_code="en",
            part_of_speech=", ".join(sorted(pos_set)[:4]) if pos_set else None,
            meanings=meanings[:10], examples=examples[:5],
            source="Free Dictionary API", confidence=0.5, found=True,
        )

    def _online_fr(self, term: str) -> DictionaryResult:
        """Wiktionary REST API for French."""
        import urllib.request
        import urllib.error
        import urllib.parse

        normalized = term.strip().lower()
        quoted = urllib.parse.quote(normalized)
        url = f"https://fr.wiktionary.org/api/rest_v1/page/definition/{quoted}"

        try:
            req = urllib.request.Request(url, headers={"User-Agent": "RemeMate/1.0"})
            with urllib.request.urlopen(req, timeout=5) as resp:
                data = json.loads(resp.read().decode("utf-8"))
        except (urllib.error.URLError, urllib.error.HTTPError,
                json.JSONDecodeError, OSError, TimeoutError):
            return self._not_found("fr", term, normalized)

        if not isinstance(data, dict):
            return self._not_found("fr", term, normalized)

        # Wiktionary response: {"fr": [{"partOfSpeech": "nom", "definitions": [...]}]}
        lang_data = data.get("fr")
        if not isinstance(lang_data, list) or not lang_data:
            return self._not_found("fr", term, normalized)

        meanings: list[str] = []
        pos_set: set[str] = set()
        for entry in lang_data:
            pos = entry.get("partOfSpeech", "")
            if pos:
                pos_set.add(pos)
            for d in entry.get("definitions") or []:
                definition = (d.get("definition") or "").strip()
                if definition:
                    meanings.append(definition)

        if not meanings:
            return self._not_found("fr", term, normalized)

        return DictionaryResult(
            term=term, normalized_term=normalized, language_code="fr",
            part_of_speech=", ".join(sorted(pos_set)[:4]) if pos_set else None,
            meanings=meanings[:10],
            source="Wiktionary API", confidence=0.5, found=True,
        )

    def _online_ja(self, term: str) -> DictionaryResult:
        """Jisho.org API for Japanese."""
        import urllib.request
        import urllib.error
        import urllib.parse

        normalized = term.strip()
        qs = urllib.parse.urlencode({"keyword": normalized})
        url = f"https://jisho.org/api/v1/search/words?{qs}"

        try:
            req = urllib.request.Request(url, headers={"User-Agent": "RemeMate/1.0"})
            with urllib.request.urlopen(req, timeout=5) as resp:
                data = json.loads(resp.read().decode("utf-8"))
        except (urllib.error.URLError, urllib.error.HTTPError,
                json.JSONDecodeError, OSError, TimeoutError):
            return self._not_found("ja", term, normalized)

        if not isinstance(data, dict):
            return self._not_found("ja", term, normalized)

        results = data.get("data")
        if not isinstance(results, list) or not results:
            return self._not_found("ja", term, normalized)

        meanings: list[str] = []
        pos_set: set[str] = set()
        for entry in results[:3]:  # take up to 3 matching entries
            for s in entry.get("senses") or []:
                for pos in (s.get("parts_of_speech") or []):
                    pos_set.add(pos)
                for d in (s.get("english_definitions") or []):
                    d = d.strip()
                    if d and d not in meanings:
                        meanings.append(d)

        if not meanings:
            return self._not_found("ja", term, normalized)

        return DictionaryResult(
            term=term, normalized_term=normalized, language_code="ja",
            part_of_speech=", ".join(sorted(pos_set)[:4]) if pos_set else None,
            meanings=meanings[:10],
            source="Jisho.org API", confidence=0.5, found=True,
        )

    # Unicode format/invisible characters that can sneak in from PDF/EPUB text
    _INVISIBLE_RE = re.compile(
        r"[­​-‏  ⁠﻿￹-￼]"
    )

    def _normalize(self, language_code: str, term: str) -> str:
        normalized = self._INVISIBLE_RE.sub("", term).strip()
        if language_code in {"zh", "ja"}:
            normalized = _CJK_SPACE_RE.sub(r"\1\2", normalized)
        if language_code in LOWERCASE_LANGUAGES:
            return normalized.lower()
        return normalized

    def _load_entries(self, language_code: str) -> dict[str, Any]:
        if language_code in self._entry_cache:
            return self._entry_cache[language_code]
        entries_path = self.data_dir / language_code / "entries.json"
        if not entries_path.exists():
            entries = {}
        else:
            try:
                with entries_path.open("r", encoding="utf-8") as handle:
                    entries = json.load(handle)
            except (OSError, UnicodeDecodeError, json.JSONDecodeError):
                entries = {}
        if not isinstance(entries, dict):
            entries = {}
        self._entry_cache[language_code] = entries
        return entries

    def _coerce_confidence(self, value: Any) -> float:
        try:
            return float(value)
        except (TypeError, ValueError):
            return 0.0

    def _not_found(self, language_code: str, term: str, normalized_term: str) -> DictionaryResult:
        return DictionaryResult(
            term=term,
            normalized_term=normalized_term,
            language_code=language_code,
            found=False,
        )
