"""SM-2 纯函数单测（不依赖 DB）。"""
from datetime import datetime, timedelta
from types import SimpleNamespace

import pytest

from app.services import srs


def _word(**kw):
    base = dict(interval=1, ease=2.5, reps=0, lapses=0,
                due_date=None, last_review=None)
    base.update(kw)
    return SimpleNamespace(**base)


def test_button_mapping():
    assert srs.quality_from_button("forgot") == 2
    assert srs.quality_from_button("fuzzy") == 3
    assert srs.quality_from_button("easy") == 5
    with pytest.raises(ValueError):
        srs.quality_from_button("bogus")


def test_first_pass_interval_1():
    w = _word(reps=0)
    srs.grade(w, 3)
    assert w.interval == 1
    assert w.reps == 1


def test_second_pass_interval_6():
    w = _word(reps=1, interval=1)
    srs.grade(w, 3)
    assert w.interval == 6
    assert w.reps == 2


def test_third_pass_multiplies_by_ease():
    w = _word(reps=2, interval=6, ease=2.5)
    srs.grade(w, 5)            # easy：ease 升到 2.6，interval = round(6*2.6)=16
    assert w.reps == 3
    assert w.interval == round(6 * w.ease)


def test_lapse_resets_and_counts():
    w = _word(reps=5, interval=40, ease=2.5, lapses=0)
    now = datetime(2026, 6, 23, 12, 0, 0)
    srs.grade(w, 2, now=now)   # forgot → lapse
    assert w.reps == 0
    assert w.interval == 1
    assert w.lapses == 1
    assert w.due_date == now + srs.LAPSE_MIN_DELAY   # 推迟一个最小区间（消除死循环感）
    assert w.ease < 2.5        # ease 下降


def test_ease_floor():
    w = _word(ease=1.3)
    srs.grade(w, 2)            # 大幅降，但不低于 1.3
    assert w.ease == pytest.approx(1.3)


def test_pass_sets_future_due():
    w = _word(reps=1, interval=1)
    now = datetime(2026, 6, 23, 12, 0, 0)
    srs.grade(w, 3, now=now)
    assert w.due_date == now + timedelta(days=6)
    assert w.last_review == now
