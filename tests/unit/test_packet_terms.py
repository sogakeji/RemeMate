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
