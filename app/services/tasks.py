"""每日任务卡聚合服务。

只读仪表盘：不写入，只查询今日进度。
所有「今天」按用户时区（User.timezone）的本地午夜切（复用
app.services.timeutil.today_local_start_utc）。
"""
from __future__ import annotations
from dataclasses import dataclass

from app.extensions import db
from app.models.user import User
from app.models.word import ReviewLog
from app.services.timeutil import today_local_start_utc


@dataclass(frozen=True)
class TaskItem:
    slug: str           # 稳定标识：review/import/read/sentence/diary
    title: str          # 中文显示名
    goal: int           # 目标量
    progress: int       # 当前进度（0..goal）
    href: str           # 跳转去做这项任务的链接

    @property
    def done(self) -> bool:
        return self.progress >= self.goal


@dataclass(frozen=True)
class TaskCard:
    items: list[TaskItem]

    @property
    def all_done(self) -> bool:
        return bool(self.items) and all(t.done for t in self.items)


# 默认目标量。用户可在 UserSettings.daily_task_config 覆盖单项目标（Task 7）。
DEFAULT_GOALS = {
    "review": 10,
    "import": 5,
    "read": 1,       # 1 篇阅读至少 1%
    "sentence": 1,
    "diary": 1,      # 一篇三行日记算 1 项
}


def get_today_task_card(user_id: int) -> TaskCard:
    """返回今日任务卡。Tasks 2-5 逐步填充每项进度。"""
    items = [
        TaskItem(slug="review", title="复习单词",
                 goal=DEFAULT_GOALS["review"],
                 progress=_review_progress(user_id), href="/review"),
        TaskItem(slug="import", title="导入单词",
                 goal=DEFAULT_GOALS["import"], progress=0, href="/intake/quick-add"),
        TaskItem(slug="read", title="阅读 1%",
                 goal=DEFAULT_GOALS["read"], progress=0, href="/reading"),
        TaskItem(slug="sentence", title="造一句句子",
                 goal=DEFAULT_GOALS["sentence"], progress=0, href="/write"),
        TaskItem(slug="diary", title="写三行日记",
                 goal=DEFAULT_GOALS["diary"], progress=0, href="/write"),
    ]
    return TaskCard(items=items)


def _review_progress(user_id: int) -> int:
    """今天（用户时区）的复习次数。复用 get_stats 的算式。"""
    user = db.session.get(User, user_id)
    if user is None:
        return 0
    since = today_local_start_utc(user.timezone or "Asia/Shanghai")
    return (ReviewLog.query
            .filter(ReviewLog.user_id == user_id,
                    ReviewLog.ts >= since)
            .count())