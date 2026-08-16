"""RS2-A generation contract tests."""
import copy
from datetime import date, datetime
import json

import pytest

from app.services import review_story_generation as generation
from app.services.llm import LLMResult
from app.services.review_stories import (
    DailyReviewStorySummary,
    ReviewStoryTarget,
    ReviewStoryTermSnapshot,
)
from app.services.review_story_generation import (
    build_review_story_messages,
    generate_review_story_once,
    ReviewStoryContractError,
    validate_review_story_result,
)


def test_build_messages_for_french_story_with_chinese_feedback():
    terms = (
        ReviewStoryTermSnapshot("t1", "maison", "n.", "房子"),
        ReviewStoryTermSnapshot("t2", "partir", "v.", "离开"),
        ReviewStoryTermSnapshot("t3", "heureux", "adj.", "高兴的"),
    )

    messages = build_review_story_messages(
        target_language="fr",
        feedback_language="zh",
        terms=terms,
    )

    assert [message["role"] for message in messages] == ["system", "user"]
    combined = "\n".join(message["content"] for message in messages)
    assert "French" in combined
    assert "Chinese" in combined

    payload_marker = "INPUT_TERMS_JSON="
    payload_text = next(
        line.removeprefix(payload_marker)
        for line in messages[1]["content"].splitlines()
        if line.startswith(payload_marker)
    )
    assert json.loads(payload_text) == [
        {
            "key": "t1",
            "surface": "maison",
            "part_of_speech": "n.",
            "meaning": "房子",
        },
        {
            "key": "t2",
            "surface": "partir",
            "part_of_speech": "v.",
            "meaning": "离开",
        },
        {
            "key": "t3",
            "surface": "heureux",
            "part_of_speech": "adj.",
            "meaning": "高兴的",
        },
    ]


@pytest.mark.parametrize(
    "target_language,target_name",
    [
        ("fr", "French"),
        ("en", "English"),
        ("ja", "Japanese"),
        ("ko", "Korean"),
        ("es", "Spanish"),
        ("zh", "Chinese"),
    ],
)
@pytest.mark.parametrize(
    "feedback_language,feedback_name",
    [
        ("zh", "Chinese"),
        ("fr", "French"),
        ("en", "English"),
        ("ja", "Japanese"),
        ("ko", "Korean"),
        ("es", "Spanish"),
    ],
)
def test_build_messages_supports_contract_languages(
    target_language,
    target_name,
    feedback_language,
    feedback_name,
):
    terms = (
        ReviewStoryTermSnapshot("t1", "one", "n.", "one"),
        ReviewStoryTermSnapshot("t2", "two", "n.", "two"),
        ReviewStoryTermSnapshot("t3", "three", "n.", "three"),
    )

    messages = build_review_story_messages(
        target_language=target_language,
        feedback_language=feedback_language,
        terms=terms,
    )

    combined = "\n".join(message["content"] for message in messages)
    assert target_name in combined
    assert feedback_name in combined


@pytest.mark.parametrize(
    "terms",
    [
        (
            ReviewStoryTermSnapshot("t1", "one", "n.", "one"),
            ReviewStoryTermSnapshot("t2", "two", "n.", "two"),
        ),
        tuple(
            ReviewStoryTermSnapshot(f"t{i}", f"word-{i}", "n.", f"meaning-{i}")
            for i in range(1, 7)
        ),
        (
            ReviewStoryTermSnapshot("t1", "one", "n.", "one"),
            ReviewStoryTermSnapshot("t3", "two", "n.", "two"),
            ReviewStoryTermSnapshot("t4", "three", "n.", "three"),
        ),
    ],
)
def test_build_messages_rejects_invalid_term_set(terms):
    with pytest.raises(ValueError, match="3 to 5|keys"):
        build_review_story_messages(
            target_language="fr",
            feedback_language="zh",
            terms=terms,
        )


def test_validate_legal_bilingual_story():
    raw = json.dumps(
        {
            "title": {
                "target": "Une journée heureuse",
                "translation": "快乐的一天",
            },
            "sentences": [
                {
                    "target": "Je quitte la maison.",
                    "translation": "我离开房子。",
                    "terms": [
                        {
                            "key": "t1",
                            "target_form": "maison",
                            "translation_form": "房子",
                        },
                        {
                            "key": "t2",
                            "target_form": "quitte",
                            "translation_form": "离开",
                        },
                    ],
                },
                {
                    "target": "Je suis heureux.",
                    "translation": "我很高兴。",
                    "terms": [
                        {
                            "key": "t3",
                            "target_form": "heureux",
                            "translation_form": "高兴",
                        },
                    ],
                },
                {
                    "target": "Le soleil brille.",
                    "translation": "阳光明媚。",
                    "terms": [],
                },
                {
                    "target": "La journée commence bien.",
                    "translation": "这一天有个好开端。",
                    "terms": [],
                },
            ],
        },
        ensure_ascii=False,
    )

    story = validate_review_story_result(
        raw,
        target_language="fr",
        feedback_language="zh",
        expected_keys=("t1", "t2", "t3"),
    )

    assert story.title.target == "Une journée heureuse"
    assert story.title.translation == "快乐的一天"
    assert len(story.sentences) == 4
    actual_keys = [
        anchor.key
        for sentence in story.sentences
        for anchor in sentence.terms
    ]
    assert actual_keys == [
        "t1",
        "t2",
        "t3",
    ]


def test_validate_rejects_non_json_with_stable_error():
    with pytest.raises(ReviewStoryContractError) as error:
        validate_review_story_result(
            "not json",
            target_language="fr",
            feedback_language="zh",
            expected_keys=("t1", "t2", "t3"),
        )

    assert error.value.code == "invalid_json"


@pytest.mark.parametrize(
    "case",
    [
        "extra_top_level",
        "empty_title",
        "three_sentences",
        "extra_sentence_field",
        "long_title",
    ],
)
def test_validate_rejects_invalid_schema(case):
    data = {
        "title": {"target": "Un jour", "translation": "一天"},
        "sentences": [
            {
                "target": "Je vois la maison.",
                "translation": "我看见房子。",
                "terms": [
                    {
                        "key": "t1",
                        "target_form": "maison",
                        "translation_form": "房子",
                    }
                ],
            },
            {
                "target": "Je veux partir.",
                "translation": "我想离开。",
                "terms": [
                    {
                        "key": "t2",
                        "target_form": "partir",
                        "translation_form": "离开",
                    }
                ],
            },
            {
                "target": "Je suis heureux.",
                "translation": "我很高兴。",
                "terms": [
                    {
                        "key": "t3",
                        "target_form": "heureux",
                        "translation_form": "高兴",
                    }
                ],
            },
            {
                "target": "La journée commence.",
                "translation": "一天开始了。",
                "terms": [],
            },
        ],
    }
    invalid = copy.deepcopy(data)
    if case == "extra_top_level":
        invalid["explanation"] = "not allowed"
    elif case == "empty_title":
        invalid["title"]["target"] = " "
    elif case == "three_sentences":
        invalid["sentences"].pop()
    elif case == "extra_sentence_field":
        invalid["sentences"][0]["note"] = "not allowed"
    elif case == "long_title":
        invalid["title"]["target"] = "x" * 121

    with pytest.raises(ReviewStoryContractError) as error:
        validate_review_story_result(
            json.dumps(invalid, ensure_ascii=False),
            target_language="fr",
            feedback_language="zh",
            expected_keys=("t1", "t2", "t3"),
        )

    assert error.value.code == "invalid_schema"


@pytest.mark.parametrize(
    "actual_keys",
    [
        ("t1", "t2"),
        ("t1", "t2", "t2", "t3"),
        ("t1", "t2", "t9"),
    ],
)
def test_validate_requires_each_expected_key_exactly_once(actual_keys):
    anchors = [
        {
            "key": key,
            "target_form": "maison",
            "translation_form": "房子",
        }
        for key in actual_keys
    ]
    raw = json.dumps(
        {
            "title": {"target": "Un jour", "translation": "一天"},
            "sentences": [
                {
                    "target": "Je vois la maison.",
                    "translation": "我看见房子。",
                    "terms": anchors,
                },
                {
                    "target": "Je marche.",
                    "translation": "我在走路。",
                    "terms": [],
                },
                {
                    "target": "Le soleil brille.",
                    "translation": "阳光明媚。",
                    "terms": [],
                },
                {
                    "target": "Je rentre.",
                    "translation": "我回去了。",
                    "terms": [],
                },
            ],
        },
        ensure_ascii=False,
    )

    with pytest.raises(ReviewStoryContractError) as error:
        validate_review_story_result(
            raw,
            target_language="fr",
            feedback_language="zh",
            expected_keys=("t1", "t2", "t3"),
        )

    assert error.value.code == "missing_or_duplicate_term"


@pytest.mark.parametrize("mismatch_field", ["target_form", "translation_form"])
def test_validate_rejects_anchor_outside_its_sentence(mismatch_field):
    first_anchor = {
        "key": "t1",
        "target_form": "maison",
        "translation_form": "房子",
    }
    first_anchor[mismatch_field] = "absent"
    raw = json.dumps(
        {
            "title": {"target": "Un jour", "translation": "一天"},
            "sentences": [
                {
                    "target": "Je vois la maison.",
                    "translation": "我看见房子。",
                    "terms": [first_anchor],
                },
                {
                    "target": "Je veux partir.",
                    "translation": "我想离开。",
                    "terms": [
                        {
                            "key": "t2",
                            "target_form": "partir",
                            "translation_form": "离开",
                        }
                    ],
                },
                {
                    "target": "Je suis heureux.",
                    "translation": "我很高兴。",
                    "terms": [
                        {
                            "key": "t3",
                            "target_form": "heureux",
                            "translation_form": "高兴",
                        }
                    ],
                },
                {
                    "target": "Je rentre.",
                    "translation": "我回去了。",
                    "terms": [],
                },
            ],
        },
        ensure_ascii=False,
    )

    with pytest.raises(ReviewStoryContractError) as error:
        validate_review_story_result(
            raw,
            target_language="fr",
            feedback_language="zh",
            expected_keys=("t1", "t2", "t3"),
        )

    assert error.value.code == "term_anchor_mismatch"


def test_validate_rejects_result_over_twelve_thousand_characters():
    raw = json.dumps(
        {
            "title": {"target": "Un jour", "translation": "一天"},
            "sentences": [
                {
                    "target": "maison " + ("x" * 12000),
                    "translation": "房子",
                    "terms": [
                        {
                            "key": "t1",
                            "target_form": "maison",
                            "translation_form": "房子",
                        }
                    ],
                },
                {
                    "target": "Je veux partir.",
                    "translation": "我想离开。",
                    "terms": [
                        {
                            "key": "t2",
                            "target_form": "partir",
                            "translation_form": "离开",
                        }
                    ],
                },
                {
                    "target": "Je suis heureux.",
                    "translation": "我很高兴。",
                    "terms": [
                        {
                            "key": "t3",
                            "target_form": "heureux",
                            "translation_form": "高兴",
                        }
                    ],
                },
                {
                    "target": "Je rentre.",
                    "translation": "我回去了。",
                    "terms": [],
                },
            ],
        },
        ensure_ascii=False,
    )

    with pytest.raises(ReviewStoryContractError) as error:
        validate_review_story_result(
            raw,
            target_language="fr",
            feedback_language="zh",
            expected_keys=("t1", "t2", "t3"),
        )

    assert error.value.code == "result_too_large"


@pytest.mark.parametrize(
    "target_language,feedback_language,target_text,translation_text",
    [
        ("zh", "en", "A French-looking sentence.", "An English sentence."),
        ("ru", "zh", "A Latin sentence.", "一句中文。"),
        ("fr", "en", "只有中文。", "也只有中文。"),
    ],
)
def test_validate_rejects_obviously_wrong_writing_system(
    target_language,
    feedback_language,
    target_text,
    translation_text,
):
    raw = json.dumps(
        {
            "title": {
                "target": target_text,
                "translation": translation_text,
            },
            "sentences": [
                {
                    "target": f"{target_text} alpha beta gamma",
                    "translation": f"{translation_text} 一二三",
                    "terms": [
                        {
                            "key": "t1",
                            "target_form": "alpha",
                            "translation_form": "一",
                        },
                        {
                            "key": "t2",
                            "target_form": "beta",
                            "translation_form": "二",
                        },
                        {
                            "key": "t3",
                            "target_form": "gamma",
                            "translation_form": "三",
                        },
                    ],
                },
                {
                    "target": target_text,
                    "translation": translation_text,
                    "terms": [],
                },
                {
                    "target": target_text,
                    "translation": translation_text,
                    "terms": [],
                },
                {
                    "target": target_text,
                    "translation": translation_text,
                    "terms": [],
                },
            ],
        },
        ensure_ascii=False,
    )

    with pytest.raises(ReviewStoryContractError) as error:
        validate_review_story_result(
            raw,
            target_language=target_language,
            feedback_language=feedback_language,
            expected_keys=("t1", "t2", "t3"),
        )

    assert error.value.code == "invalid_schema"


def test_build_messages_requests_fixed_json_and_term_anchors():
    terms = (
        ReviewStoryTermSnapshot("t1", "one", "n.", "one"),
        ReviewStoryTermSnapshot("t2", "two", "n.", "two"),
        ReviewStoryTermSnapshot("t3", "three", "n.", "three"),
    )

    messages = build_review_story_messages(
        target_language="en",
        feedback_language="zh",
        terms=terms,
    )

    user_prompt = messages[1]["content"]
    assert "4 to 6" in user_prompt
    assert "JSON only" in user_prompt
    assert '"sentences"' in user_prompt
    assert '"target_form"' in user_prompt
    assert '"translation_form"' in user_prompt


def test_generate_once_calls_general_json_mode_and_returns_usage(monkeypatch):
    raw = json.dumps(
        {
            "title": {"target": "Un jour heureux", "translation": "快乐的一天"},
            "sentences": [
                {
                    "target": "Je quitte la maison.",
                    "translation": "我离开房子。",
                    "terms": [
                        {
                            "key": "t1",
                            "target_form": "maison",
                            "translation_form": "房子",
                        },
                        {
                            "key": "t2",
                            "target_form": "quitte",
                            "translation_form": "离开",
                        },
                    ],
                },
                {
                    "target": "Je suis heureux.",
                    "translation": "我很高兴。",
                    "terms": [
                        {
                            "key": "t3",
                            "target_form": "heureux",
                            "translation_form": "高兴",
                        }
                    ],
                },
                {
                    "target": "Le soleil brille.",
                    "translation": "阳光明媚。",
                    "terms": [],
                },
                {
                    "target": "Je rentre.",
                    "translation": "我回去了。",
                    "terms": [],
                },
            ],
        },
        ensure_ascii=False,
    )
    calls = []

    def fake_chat(messages, *, task, json_mode, **kwargs):
        calls.append((messages, task, json_mode))
        return LLMResult(raw, 17, 23, "fake", "fake-model")

    monkeypatch.setattr(generation.llm, "chat", fake_chat)
    snapshots = (
        ReviewStoryTermSnapshot("t1", "maison", "n.", "房子"),
        ReviewStoryTermSnapshot("t2", "partir", "v.", "离开"),
        ReviewStoryTermSnapshot("t3", "heureux", "adj.", "高兴"),
    )
    summary = DailyReviewStorySummary(
        user_id=1,
        local_date=date(2026, 7, 24),
        day_start_utc=datetime(2026, 7, 23, 16),
        day_end_utc=datetime(2026, 7, 24, 16),
        target_language="fr",
        feedback_language="zh",
        reviewed_word_count=10,
        forgotten_word_count=3,
        eligibility="normal",
        targets=tuple(
            ReviewStoryTarget(index, 2, snapshot)
            for index, snapshot in enumerate(snapshots, start=1)
        ),
        input_hash="a" * 64,
    )

    attempt = generate_review_story_once(summary)

    assert len(calls) == 1
    assert calls[0][1:] == ("general", True)
    assert attempt.error_code is None
    assert attempt.story is not None
    assert attempt.story.title.target == "Un jour heureux"
    assert attempt.prompt_tokens == 17
    assert attempt.completion_tokens == 23
    assert attempt.provider == "fake"
    assert attempt.model == "fake-model"


def test_generate_once_degrades_when_all_providers_are_down(monkeypatch):
    calls = []

    def fake_chat(messages, *, task, json_mode):
        calls.append((messages, task, json_mode))
        raise generation.llm.AllProvidersDown("offline")

    monkeypatch.setattr(generation.llm, "chat", fake_chat)
    snapshots = (
        ReviewStoryTermSnapshot("t1", "maison", "n.", "房子"),
        ReviewStoryTermSnapshot("t2", "partir", "v.", "离开"),
        ReviewStoryTermSnapshot("t3", "heureux", "adj.", "高兴"),
    )
    summary = DailyReviewStorySummary(
        user_id=1,
        local_date=date(2026, 7, 24),
        day_start_utc=datetime(2026, 7, 23, 16),
        day_end_utc=datetime(2026, 7, 24, 16),
        target_language="fr",
        feedback_language="zh",
        reviewed_word_count=10,
        forgotten_word_count=3,
        eligibility="normal",
        targets=tuple(
            ReviewStoryTarget(index, 2, snapshot)
            for index, snapshot in enumerate(snapshots, start=1)
        ),
        input_hash="a" * 64,
    )

    attempt = generate_review_story_once(summary)

    assert len(calls) == 1
    assert attempt.story is None
    assert attempt.error_code == "provider_unavailable"
    assert attempt.prompt_tokens == 0
    assert attempt.completion_tokens == 0
    assert attempt.provider is None
    assert attempt.model is None


def test_generate_once_repairs_invalid_result_with_bounded_retry(monkeypatch):
    calls = []

    def fake_chat(messages, *, task, json_mode, **kwargs):
        calls.append((messages, task, json_mode, kwargs))
        return LLMResult("not json", 17, 23, "fake", "fake-model")

    monkeypatch.setattr(generation.llm, "chat", fake_chat)
    snapshots = (
        ReviewStoryTermSnapshot("t1", "maison", "n.", "房子"),
        ReviewStoryTermSnapshot("t2", "partir", "v.", "离开"),
        ReviewStoryTermSnapshot("t3", "heureux", "adj.", "高兴"),
    )
    summary = DailyReviewStorySummary(
        user_id=1,
        local_date=date(2026, 7, 24),
        day_start_utc=datetime(2026, 7, 23, 16),
        day_end_utc=datetime(2026, 7, 24, 16),
        target_language="fr",
        feedback_language="zh",
        reviewed_word_count=10,
        forgotten_word_count=3,
        eligibility="normal",
        targets=tuple(
            ReviewStoryTarget(index, 2, snapshot)
            for index, snapshot in enumerate(snapshots, start=1)
        ),
        input_hash="a" * 64,
    )

    attempt = generate_review_story_once(summary)

    assert len(calls) == 3
    assert attempt.story is None
    assert attempt.error_code == "invalid_json"
    assert attempt.prompt_tokens == 51
    assert attempt.completion_tokens == 69
    assert attempt.provider == "fake"
    assert attempt.model == "fake-model"
    assert calls[2][3]["excluded_provider_names"] == {"fake"}


def test_generate_once_returns_repaired_story_and_aggregated_usage(monkeypatch):
    repaired = json.dumps(
        {
            "title": {"target": "Un jour heureux", "translation": "快乐的一天"},
            "sentences": [
                {
                    "target": "Je quitte la maison.",
                    "translation": "我离开房子。",
                    "terms": [
                        {"key": "t1", "target_form": "maison", "translation_form": "房子"},
                        {"key": "t2", "target_form": "quitte", "translation_form": "离开"},
                    ],
                },
                {
                    "target": "Je suis heureux.",
                    "translation": "我很高兴。",
                    "terms": [{"key": "t3", "target_form": "heureux", "translation_form": "高兴"}],
                },
                {"target": "Le soleil brille.", "translation": "阳光明媚。", "terms": []},
                {"target": "Je rentre.", "translation": "我回去了。", "terms": []},
            ],
        },
        ensure_ascii=False,
    )
    responses = iter([
        LLMResult("not json", 17, 23, "fake", "fake-model"),
        LLMResult(repaired, 19, 29, "fake", "fake-model"),
    ])

    def fake_chat(messages, *, task, json_mode):
        return next(responses)

    monkeypatch.setattr(generation.llm, "chat", fake_chat)
    snapshots = (
        ReviewStoryTermSnapshot("t1", "maison", "n.", "房子"),
        ReviewStoryTermSnapshot("t2", "partir", "v.", "离开"),
        ReviewStoryTermSnapshot("t3", "heureux", "adj.", "高兴"),
    )
    summary = DailyReviewStorySummary(
        user_id=1,
        local_date=date(2026, 7, 24),
        day_start_utc=datetime(2026, 7, 23, 16),
        day_end_utc=datetime(2026, 7, 24, 16),
        target_language="fr",
        feedback_language="zh",
        reviewed_word_count=10,
        forgotten_word_count=3,
        eligibility="normal",
        targets=tuple(ReviewStoryTarget(index, 2, snapshot) for index, snapshot in enumerate(snapshots, start=1)),
        input_hash="a" * 64,
    )

    attempt = generate_review_story_once(summary)

    assert attempt.story is not None
    assert attempt.error_code is None
    assert attempt.prompt_tokens == 36
    assert attempt.completion_tokens == 52


def test_validate_normalizes_nfkc_case_whitespace_and_apostrophes():
    raw = json.dumps(
        {
            "title": {"target": "Un beau jour", "translation": "美好的一天"},
            "sentences": [
                {
                    "target": "Ｊ’ＡＩＭＥ la maison.",
                    "translation": "我喜欢房子。",
                    "terms": [
                        {
                            "key": "t1",
                            "target_form": "j'aime",
                            "translation_form": "房子",
                        }
                    ],
                },
                {
                    "target": "Je   veux partir.",
                    "translation": "我想离开。",
                    "terms": [
                        {
                            "key": "t2",
                            "target_form": "je veux partir",
                            "translation_form": "离开",
                        }
                    ],
                },
                {
                    "target": "Je suis heureux.",
                    "translation": "我很高兴。",
                    "terms": [
                        {
                            "key": "t3",
                            "target_form": "HEUREUX",
                            "translation_form": "高兴",
                        }
                    ],
                },
                {
                    "target": "Je rentre.",
                    "translation": "我回去了。",
                    "terms": [],
                },
            ],
        },
        ensure_ascii=False,
    )

    story = validate_review_story_result(
        raw,
        target_language="fr",
        feedback_language="zh",
        expected_keys=("t1", "t2", "t3"),
    )

    assert len(story.sentences) == 4


@pytest.mark.parametrize(
    "marked_up_target",
    [
        "Je vois <b>la maison</b>.",
        "Je vois **la maison**.",
    ],
)
def test_validate_rejects_html_and_markdown(marked_up_target):
    raw = json.dumps(
        {
            "title": {"target": "Un jour", "translation": "一天"},
            "sentences": [
                {
                    "target": marked_up_target,
                    "translation": "我看见房子。",
                    "terms": [
                        {
                            "key": "t1",
                            "target_form": "maison",
                            "translation_form": "房子",
                        }
                    ],
                },
                {
                    "target": "Je veux partir.",
                    "translation": "我想离开。",
                    "terms": [
                        {
                            "key": "t2",
                            "target_form": "partir",
                            "translation_form": "离开",
                        }
                    ],
                },
                {
                    "target": "Je suis heureux.",
                    "translation": "我很高兴。",
                    "terms": [
                        {
                            "key": "t3",
                            "target_form": "heureux",
                            "translation_form": "高兴",
                        }
                    ],
                },
                {
                    "target": "Je rentre.",
                    "translation": "我回去了。",
                    "terms": [],
                },
            ],
        },
        ensure_ascii=False,
    )

    with pytest.raises(ReviewStoryContractError) as error:
        validate_review_story_result(
            raw,
            target_language="fr",
            feedback_language="zh",
            expected_keys=("t1", "t2", "t3"),
        )

    assert error.value.code == "invalid_schema"

def test_build_messages_requests_simple_high_frequency_language():
    terms = (
        ReviewStoryTermSnapshot("t1", "one", "n.", "one"),
        ReviewStoryTermSnapshot("t2", "two", "n.", "two"),
        ReviewStoryTermSnapshot("t3", "three", "n.", "three"),
    )

    messages = build_review_story_messages(
        target_language="en",
        feedback_language="zh",
        terms=terms,
    )

    user_prompt = messages[1]["content"]
    assert "high-frequency" in user_prompt
    assert "Avoid rare idioms" in user_prompt
    assert "complex nested sentences" in user_prompt
