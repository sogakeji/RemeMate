"""每日任务卡聚合服务的单元测试。

任务卡 = 5 项任务，每项含 slug / 标题 / 目标量 / 当前进度 / 是否完成。
所有「今天」计算按用户时区（User.timezone）的本地午夜切。
"""
from __future__ import annotations


def test_task_card_has_five_tasks(app, bypass_engine):
    """卡片始终含 5 项任务，slug 固定，便于前端/测试稳定引用。"""
    from flask import g
    from app.services.tasks import get_today_task_card, TaskCard, TaskItem
    from tests.helpers import provision_user

    uid = provision_user(app, email="t@t.com")
    with app.test_request_context("/"):
        g.rls_uid = uid
        card = get_today_task_card(uid)

    assert isinstance(card, TaskCard)
    assert [t.slug for t in card.items] == [
        "review", "import", "read", "sentence", "diary",
    ]
    assert all(isinstance(t, TaskItem) for t in card.items)
    assert all(t.goal >= 1 for t in card.items)
    assert all(t.progress >= 0 for t in card.items)


def test_review_progress_counts_today_review_logs(app, bypass_engine):
    """复习进度 = 今天（用户时区）的 ReviewLog 条数。"""
    from flask import g
    from app.extensions import db
    from app.services.tasks import get_today_task_card
    from tests.helpers import make_word, make_review_log, provision_user

    uid = provision_user(app, email="rev@t.com")
    list_id, word_id = make_word(bypass_engine, uid, "cat")
    for _ in range(3):
        make_review_log(bypass_engine, uid, word_id)

    with app.test_request_context("/"):
        g.rls_uid = uid
        card = get_today_task_card(uid)
    review = next(t for t in card.items if t.slug == "review")
    assert review.goal == 10
    assert review.progress == 3
    assert not review.done