"""RS1 unit coverage for daily review summary and deterministic selection.

No provider calls, routes, or UI. Pure service + time-window behavior.
"""
from __future__ import annotations

from datetime import date, datetime, timezone
from zoneinfo import ZoneInfo

import pytest

from app.services.review_stories import (
    ELIGIBILITY_NORMAL,
    ELIGIBILITY_SILENT,
    ELIGIBILITY_STRONG,
    REVIEW_STORY_CONTRACT_VERSION,
    ReviewedWord,
    ReviewStoryTermSnapshot,
    build_daily_review_story_summary,
    review_story_eligibility,
    review_story_input_hash,
    select_review_story_targets,
)
from app.services.timeutil import local_day_window_utc


# ---------------------------------------------------------------------------
# Eligibility boundaries: 9/10 reviewed, 5/6 forgotten
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "reviewed,forgotten,expected",
    [
        (0, 0, ELIGIBILITY_SILENT),
        (9, 0, ELIGIBILITY_SILENT),
        (9, 5, ELIGIBILITY_SILENT),
        (10, 0, ELIGIBILITY_NORMAL),
        (10, 5, ELIGIBILITY_NORMAL),
        (9, 6, ELIGIBILITY_STRONG),  # strong overrides count floor
        (10, 6, ELIGIBILITY_STRONG),
        (6, 6, ELIGIBILITY_STRONG),  # forgotten is subset of reviewed
        (7, 6, ELIGIBILITY_STRONG),
    ],
)
def test_review_story_eligibility_boundaries(reviewed, forgotten, expected):
    assert review_story_eligibility(
        reviewed_word_count=reviewed,
        forgotten_word_count=forgotten,
    ) == expected


def test_review_story_eligibility_rejects_negative_and_impossible():
    with pytest.raises(ValueError):
        review_story_eligibility(reviewed_word_count=-1, forgotten_word_count=0)
    with pytest.raises(ValueError):
        review_story_eligibility(reviewed_word_count=3, forgotten_word_count=-1)
    with pytest.raises(ValueError):
        review_story_eligibility(reviewed_word_count=2, forgotten_word_count=3)


# ---------------------------------------------------------------------------
# Deterministic target selection: 2/3/4/5 and ordering
# ---------------------------------------------------------------------------


def _words(*pairs: tuple[int, int, str]) -> list[ReviewedWord]:
    """pairs: (word_id, worst_grade, surface)."""
    return [
        ReviewedWord(word_id=wid, surface=surface, worst_grade=grade)
        for wid, grade, surface in pairs
    ]


def test_select_targets_orders_by_worst_grade_then_id():
    # grades: 2 forgot, 3 hard, 5 easy — lower grade first, then word_id
    rows = _words(
        (30, 5, "easy-late"),
        (10, 3, "hard-early"),
        (20, 2, "forgot"),
        (11, 3, "hard-late"),
        (5, 5, "easy-early"),
        (40, 2, "forgot-late"),
    )
    selected = select_review_story_targets(rows, limit=5)
    assert [r.word_id for r in selected] == [20, 40, 10, 11, 5]
    assert [r.worst_grade for r in selected] == [2, 2, 3, 3, 5]


@pytest.mark.parametrize("n", [2, 3, 4, 5])
def test_select_targets_returns_all_when_under_or_equal_limit(n):
    rows = _words(*[(i + 1, 5, f"w{i}") for i in range(n)])
    selected = select_review_story_targets(rows, limit=5)
    assert len(selected) == n
    assert [r.word_id for r in selected] == list(range(1, n + 1))


def test_select_targets_caps_at_five_and_is_stable():
    rows = _words(*[(i, 5 if i > 3 else 2, f"w{i}") for i in range(1, 9)])
    a = select_review_story_targets(rows)
    b = select_review_story_targets(list(reversed(rows)))
    assert len(a) == 5
    assert a == b
    # three grade-2 first (ids 1,2,3), then grade-5 by id
    assert [r.word_id for r in a] == [1, 2, 3, 4, 5]


def test_select_targets_ignores_invalid_grades():
    rows = [
        ReviewedWord(1, "ok", 2),
        ReviewedWord(2, "bad-grade", 4),  # not in {2,3,5}
        ReviewedWord(3, "ok2", 5),
    ]
    selected = select_review_story_targets(rows)
    assert [r.word_id for r in selected] == [1, 3]


def test_select_targets_rejects_nonpositive_limit():
    with pytest.raises(ValueError):
        select_review_story_targets(_words((1, 5, "a")), limit=0)


# ---------------------------------------------------------------------------
# Input hash: stable, provider-safe fields only, changes on input
# ---------------------------------------------------------------------------


def _term(key, surface, pos="n", meaning="m") -> ReviewStoryTermSnapshot:
    return ReviewStoryTermSnapshot(
        key=key, surface=surface, part_of_speech=pos, meaning=meaning,
    )


def test_input_hash_stable_for_identical_canonical_input():
    terms = (_term("t1", "maison"), _term("t2", "partir", "v", "离开"))
    a = review_story_input_hash(
        contract_version=REVIEW_STORY_CONTRACT_VERSION,
        target_language="fr",
        feedback_language="zh",
        terms=terms,
    )
    b = review_story_input_hash(
        contract_version=REVIEW_STORY_CONTRACT_VERSION,
        target_language="fr",
        feedback_language="zh",
        terms=terms,
    )
    assert a == b
    assert len(a) == 64
    int(a, 16)  # hex


def test_input_hash_changes_when_feedback_language_or_terms_change():
    terms = (_term("t1", "maison"),)
    base = dict(
        contract_version=REVIEW_STORY_CONTRACT_VERSION,
        target_language="fr",
        feedback_language="zh",
        terms=terms,
    )
    h0 = review_story_input_hash(**base)
    h_fb = review_story_input_hash(**{**base, "feedback_language": "en"})
    h_term = review_story_input_hash(
        **{**base, "terms": (_term("t1", "maison", "n", "房子"),)}
    )
    h_order = review_story_input_hash(
        **{**base, "terms": (_term("t2", "partir"), _term("t1", "maison"))}
    )
    assert len({h0, h_fb, h_term, h_order}) == 4


def test_input_hash_normalizes_whitespace_and_apostrophes():
    a = review_story_input_hash(
        contract_version=REVIEW_STORY_CONTRACT_VERSION,
        target_language="fr",
        feedback_language="zh",
        terms=(_term("t1", "l’été"),),
    )
    b = review_story_input_hash(
        contract_version=REVIEW_STORY_CONTRACT_VERSION,
        target_language="fr",
        feedback_language="zh",
        terms=(_term("t1", "l'été"),),
    )
    c = review_story_input_hash(
        contract_version=REVIEW_STORY_CONTRACT_VERSION,
        target_language="fr",
        feedback_language="zh",
        terms=(_term("t1", "  l'été  "),),
    )
    assert a == b == c


def test_provider_dict_exposes_only_safe_fields():
    snap = _term("t1", "maison", "nf", "房子")
    d = snap.as_provider_dict()
    assert set(d.keys()) == {"key", "surface", "part_of_speech", "meaning"}
    assert "word_id" not in d
    assert d["surface"] == "maison"


def test_input_hash_rejects_unsupported_languages():
    with pytest.raises(ValueError):
        review_story_input_hash(
            contract_version=REVIEW_STORY_CONTRACT_VERSION,
            target_language="xx",
            feedback_language="zh",
            terms=(),
        )
    with pytest.raises(ValueError):
        review_story_input_hash(
            contract_version=REVIEW_STORY_CONTRACT_VERSION,
            target_language="fr",
            feedback_language="ja",
            terms=(),
        )


# ---------------------------------------------------------------------------
# Local day window + DST (timeutil used by summary)
# ---------------------------------------------------------------------------


def test_local_day_window_shanghai_half_open():
    start, end = local_day_window_utc("Asia/Shanghai", local_date=date(2026, 7, 22))
    assert start == datetime(2026, 7, 21, 16, 0, 0)
    assert end == datetime(2026, 7, 22, 16, 0, 0)


def test_local_day_window_dst_spring_forward_us_pacific():
    """2026-03-08 US/Pacific: clocks spring forward 02:00 → 03:00 (23h day)."""
    start, end = local_day_window_utc("US/Pacific", local_date=date(2026, 3, 8))
    # Local midnights: 2026-03-08 00:00 PST = UTC 08:00; next midnight PDT = UTC 07:00 next day
    assert start == datetime(2026, 3, 8, 8, 0, 0)
    assert end == datetime(2026, 3, 9, 7, 0, 0)
    # Not a fixed 24h add
    assert (end - start).total_seconds() == 23 * 3600


def test_local_day_window_dst_fall_back_us_pacific():
    """2026-11-01 US/Pacific: clocks fall back 02:00 → 01:00 (25h day)."""
    start, end = local_day_window_utc("US/Pacific", local_date=date(2026, 11, 1))
    assert start == datetime(2026, 11, 1, 7, 0, 0)
    assert end == datetime(2026, 11, 2, 8, 0, 0)
    assert (end - start).total_seconds() == 25 * 3600


def test_local_day_window_from_now_utc_crosses_local_midnight():
    # Shanghai 2026-07-22 00:30 local = 2026-07-21 16:30 UTC → local date 22nd
    now = datetime(2026, 7, 21, 16, 30, 0, tzinfo=timezone.utc)
    start, end = local_day_window_utc("Asia/Shanghai", now_utc=now)
    assert start == datetime(2026, 7, 21, 16, 0, 0)
    assert end == datetime(2026, 7, 22, 16, 0, 0)
    # Just before local midnight (UTC 15:59 on 21st) → still local date 21st
    before = datetime(2026, 7, 21, 15, 59, 0, tzinfo=timezone.utc)
    s2, e2 = local_day_window_utc("Asia/Shanghai", now_utc=before)
    assert s2 == datetime(2026, 7, 20, 16, 0, 0)
    assert e2 == datetime(2026, 7, 21, 16, 0, 0)


def test_build_summary_rejects_unsupported_languages():
    with pytest.raises(ValueError):
        build_daily_review_story_summary(
            user_id=1,
            timezone_name="UTC",
            target_language="xx",
            feedback_language="zh",
        )
    with pytest.raises(ValueError):
        build_daily_review_story_summary(
            user_id=1,
            timezone_name="UTC",
            target_language="fr",
            feedback_language="de",
        )
