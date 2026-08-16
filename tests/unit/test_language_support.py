import pytest

from app.i18n import SUPPORTED_UI_LOCALES, _catalog
from app.services.reading.dictionary import SUPPORTED_LANGUAGES
from app.services.review_stories import (
    SUPPORTED_FEEDBACK_LANGUAGES,
    SUPPORTED_TARGET_LANGUAGES,
)
from app.services.writing import SentenceLanguageMismatch, _validate_sentence_language
from app.services.words import _LANGUAGE_NAMES


def test_language_support_is_scoped_by_feature():
    assert SUPPORTED_UI_LOCALES == ("zh", "en")
    assert tuple(_LANGUAGE_NAMES) == ("zh", "en", "fr", "ja", "ko", "es")
    assert not {"de", "ru"} & set(_LANGUAGE_NAMES)
    assert SUPPORTED_TARGET_LANGUAGES == frozenset({"zh", "en", "fr", "ja", "ko", "es"})
    assert SUPPORTED_FEEDBACK_LANGUAGES == frozenset({"zh", "en", "fr", "ja", "ko", "es"})
    assert SUPPORTED_LANGUAGES == frozenset({"zh", "en", "fr", "ja"})


def test_ui_catalog_exposes_korean_language_name():
    assert _catalog("zh")["language.ko"] == "韩语"
    assert _catalog("en")["language.ko"] == "Korean"


def test_ai_writing_accepts_korean_and_rejects_latin_only_input():
    _validate_sentence_language("오늘은 학교에 갑니다.", "ko")
    with pytest.raises(SentenceLanguageMismatch):
        _validate_sentence_language("I go to school today.", "ko")
