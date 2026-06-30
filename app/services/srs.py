"""SM-2 间隔重复调度（产品心脏）。

三按钮 → SM-2 质量分映射（见 docs/arch/v0.1-direction-and-constraints.md §3.6）：
- 没记住 forgot → q=2（视为 lapse）
- 有点模糊 fuzzy → q=3（通过偏难）
- 秒记起   easy  → q=5（通过容易）

FSRS 字段（stability/difficulty）P1 留空，P2 切换时本映射改 FSRS 评分。
"""
from datetime import datetime, timedelta

from app.services.timeutil import utc_now

EASE_FLOOR = 1.3
BUTTON_TO_QUALITY = {"forgot": 2, "fuzzy": 3, "easy": 5}

# lapse 后不复位到 now（否则 `due_date=now` + /review limit=1 会让同一张牌立刻再现，
# 形成「死循环感」——review 2026-06-23 M8）。给一个最小区间把它从「即时到期」
# 队列队首移开，让本轮先转去复习其他到期词，稍后再回到这张 lapse 牌。
LAPSE_MIN_DELAY = timedelta(minutes=10)


def quality_from_button(button: str) -> int:
    try:
        return BUTTON_TO_QUALITY[button]
    except KeyError:
        raise ValueError(f"未知复习按钮：{button!r}")


def _next_ease(ease: float, quality: int) -> float:
    # 标准 SM-2：EF' = EF + (0.1 - (5-q)*(0.08 + (5-q)*0.02))，下限 1.3
    delta = 0.1 - (5 - quality) * (0.08 + (5 - quality) * 0.02)
    return max(EASE_FLOOR, ease + delta)


def grade(word, quality: int, now: datetime | None = None):
    """按质量分更新 word 的 SM-2 字段（原地修改，不 commit）。返回 word。"""
    now = now or utc_now()
    word.ease = _next_ease(word.ease, quality)  # ease 每次都更新（含 lapse）

    if quality < 3:
        # lapse：重置，给最小区间推迟（见 LAPSE_MIN_DELAY），避免立即再现死循环。
        word.reps = 0
        word.interval = 1
        word.lapses = (word.lapses or 0) + 1
        word.due_date = now + LAPSE_MIN_DELAY
    else:
        if word.reps == 0:
            word.interval = 1
        elif word.reps == 1:
            word.interval = 6
        else:
            word.interval = round(word.interval * word.ease)
        word.reps += 1
        word.due_date = now + timedelta(days=word.interval)

    word.last_review = now
    return word
