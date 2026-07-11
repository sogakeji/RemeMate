"""Unit boundaries for manual packet-item term splitting."""
import pytest

from app.services import packets


def test_terms_are_trimmed_and_case_insensitively_deduplicated():
    assert packets._normalize_adoption_terms(
        "  Bonjour  \nbonjour\n\nAu revoir\n",
    ) == ["Bonjour", "Au revoir"]


def test_terms_use_database_lower_semantics_for_non_ascii_text():
    assert packets._normalize_adoption_terms("Straße\nSTRASSE") == [
        "Straße", "STRASSE",
    ]


def test_terms_reject_more_than_batch_limit():
    value = "\n".join(f"term-{index}" for index in range(21))

    with pytest.raises(ValueError, match="一次最多加入 20 个"):
        packets._normalize_adoption_terms(value)


def test_each_term_has_its_own_length_limit():
    with pytest.raises(ValueError, match="每个候选词"):
        packets._normalize_adoption_terms("x" * 201)


def test_ai_suggestions_are_bounded_cleaned_and_deduplicated():
    payload = {
        "terms": ["  赞同  ", "赞同", "自然表达", "x" * 81, 42, ""],
    }

    assert packets.normalize_term_suggestions(payload) == ["赞同", "自然表达"]


def test_ai_suggestions_reject_missing_or_empty_term_list():
    assert packets.normalize_term_suggestions({"items": ["赞同"]}) == []
    assert packets.normalize_term_suggestions({"terms": []}) == []
    assert packets.normalize_term_suggestions("赞同") == []


def test_ai_suggestions_stop_at_the_smaller_product_limit():
    payload = {"terms": [f"term-{index}" for index in range(12)]}

    assert packets.normalize_term_suggestions(payload) == [
        f"term-{index}" for index in range(8)
    ]
