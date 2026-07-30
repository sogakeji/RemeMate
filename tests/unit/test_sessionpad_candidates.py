"""SessionPad term + context normalization contracts."""
import pytest

from app.services import sessionpad_candidates as candidates


def test_ai_context_must_map_to_a_continuous_source_excerpt():
    source = (
        "Les personnes agees\n"
        "prennent   des cours de danse chaque semaine."
    )
    payload = {
        "candidates": [{
            "term": "prendre des cours",
            "context": "personnes agees prennent des cours de danse",
        }],
    }

    assert candidates.normalize_ai_suggestions(payload, source) == [
        candidates.CandidateDraft(
            term="prendre des cours",
            context=(
                "personnes agees\n"
                "prennent   des cours de danse"
            ),
            provenance="source_quote",
        ),
    ]


def test_ai_context_that_cannot_be_located_is_dropped_not_invented():
    payload = {
        "candidates": [{
            "term": "prendre des cours",
            "context": "une phrase inventee",
        }],
    }

    assert candidates.normalize_ai_suggestions(
        payload,
        "Elle prend des cours de danse.",
    ) == [
        candidates.CandidateDraft(
            term="prendre des cours",
            context=None,
            provenance=None,
        ),
    ]


def test_duplicate_ai_term_keeps_first_display_and_first_valid_context():
    payload = {
        "candidates": [
            {"term": " Prendre des cours ", "context": "not in source"},
            {
                "term": "prendre des cours",
                "context": "prend des cours de danse",
            },
            {
                "term": "PRENDRE DES COURS",
                "context": "Elle prend des cours",
            },
        ],
    }

    assert candidates.normalize_ai_suggestions(
        payload,
        "Elle prend des cours de danse.",
    ) == [
        candidates.CandidateDraft(
            term="Prendre des cours",
            context="prend des cours de danse",
            provenance="source_quote",
        ),
    ]


def test_manual_candidates_share_contract_and_are_user_edited():
    rows = [
        {"term": "  prendre des cours  ", "context": "  mon contexte  "},
        {"term": "PRENDRE DES COURS", "context": ""},
        {"term": "se reposer", "context": None},
    ]

    assert candidates.normalize_manual_candidates(rows) == [
        candidates.CandidateDraft(
            term="prendre des cours",
            context="mon contexte",
            provenance="user_edited",
        ),
        candidates.CandidateDraft(
            term="se reposer",
            context=None,
            provenance=None,
        ),
    ]


def test_manual_contract_rejects_invalid_shape_and_limits():
    with pytest.raises(ValueError, match="20"):
        candidates.normalize_manual_candidates([
            {"term": f"term-{index}", "context": None}
            for index in range(21)
        ])
    with pytest.raises(ValueError, match="80"):
        candidates.normalize_manual_candidates([
            {"term": "x" * 81, "context": None},
        ])
    with pytest.raises(ValueError, match="300"):
        candidates.normalize_manual_candidates([
            {"term": "term", "context": "x" * 301},
        ])
    with pytest.raises(ValueError, match="at least one"):
        candidates.normalize_manual_candidates([])


def test_ai_contract_is_bounded_and_drops_invalid_items():
    payload = {
        "candidates": [
            {"term": "", "context": None},
            {"term": "x" * 81, "context": None},
            {"term": 42, "context": None},
            *[
                {"term": f"term-{index}", "context": None}
                for index in range(10)
            ],
        ],
    }

    result = candidates.normalize_ai_suggestions(payload, "source")

    assert [draft.term for draft in result] == [
        f"term-{index}" for index in range(8)
    ]


def test_editing_ai_context_changes_provenance_to_user_edited():
    source = "Elle prend des cours de danse."
    rows = [{
        "term": "prendre des cours",
        "context": "Mon propre contexte.",
        "origin": "source_quote",
        "original_context": source,
    }]

    assert candidates.normalize_submitted_candidates(rows, source) == [
        candidates.CandidateDraft(
            term="prendre des cours",
            context="Mon propre contexte.",
            provenance="user_edited",
        ),
    ]