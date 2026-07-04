import pytest

from app.services.reading.dictionary import Dictionary, UnsupportedLanguage


FIXTURE_DIR = "tests/fixtures/dictionaries"


def test_lookup_hits_chinese_fixture():
    dictionary = Dictionary(data_dir=FIXTURE_DIR)

    result = dictionary.lookup("zh", "学习")

    assert result.found is True
    assert result.term == "学习"
    assert result.normalized_term == "学习"
    assert result.language_code == "zh"
    assert result.part_of_speech == "noun"
    assert result.meanings == ["learning; study"]
    assert result.examples == ["我喜欢学习。"]
    assert result.source == "fixture:zh"
    assert result.confidence == 0.91
    assert result.as_json()["found"] is True


def test_lookup_hits_english_fixture_with_lowercase_normalization():
    dictionary = Dictionary(data_dir=FIXTURE_DIR)

    result = dictionary.lookup("en", "Apple")

    assert result.found is True
    assert result.term == "Apple"
    assert result.normalized_term == "apple"
    assert result.meanings == ["a round fruit with red, green, or yellow skin"]


def test_lookup_hits_japanese_fixture_adapter_path():
    dictionary = Dictionary(data_dir=FIXTURE_DIR)

    result = dictionary.lookup("ja", "日本語")

    assert result.found is True
    assert result.normalized_term == "日本語"
    assert result.meanings == ["Japanese language"]
    assert result.source == "fixture:ja"


def test_lookup_hits_french_fixture_with_lowercase_normalization():
    dictionary = Dictionary(data_dir=FIXTURE_DIR)

    result = dictionary.lookup("fr", "Bonjour")

    assert result.found is True
    assert result.term == "Bonjour"
    assert result.normalized_term == "bonjour"
    assert result.part_of_speech == "interjection"
    assert result.meanings == ["hello; good morning"]


def test_unsupported_language_raises_clear_exception():
    dictionary = Dictionary(data_dir=FIXTURE_DIR)

    with pytest.raises(UnsupportedLanguage, match="Unsupported dictionary language: de"):
        dictionary.lookup("de", "hallo")


def test_missing_dictionary_returns_not_found(tmp_path):
    dictionary = Dictionary(data_dir=tmp_path)

    result = dictionary.lookup("en", "apple")

    assert result.found is False
    assert result.term == "apple"
    assert result.normalized_term == "apple"
    assert result.language_code == "en"
    assert result.part_of_speech is None
    assert result.meanings == []
    assert result.examples == []
    assert result.source is None
    assert result.confidence == 0.0


def test_missing_term_returns_not_found():
    dictionary = Dictionary(data_dir=FIXTURE_DIR)

    result = dictionary.lookup("zh", "不存在")

    assert result.found is False
    assert result.normalized_term == "不存在"
    assert result.meanings == []
