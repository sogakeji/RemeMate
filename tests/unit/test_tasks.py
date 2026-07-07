"""每日任务卡聚合服务的单元测试。

任务卡 = 5 项任务，每项含 slug / 标题 / 目标量 / 当前进度 / 是否完成。
所有「今天」计算按用户时区（User.timezone）的本地午夜切。
"""
from __future__ import annotations


def test_task_card_has_five_tasks(app):
    """卡片始终含 5 项任务，slug 固定，便于前端/测试稳定引用。"""
    with app.app_context():
        from app.extensions import db
        from app.models.user import User
        from app.services.tasks import get_today_task_card, TaskCard, TaskItem

        u = User(email="t@t.com", display_name="t",
                 password_hash="x", timezone="Asia/Shanghai")
        db.session.add(u)
        db.session.commit()
        card = get_today_task_card(u.id)

    assert isinstance(card, TaskCard)
    assert [t.slug for t in card.items] == [
        "review", "import", "read", "sentence", "diary",
    ]
    assert all(isinstance(t, TaskItem) for t in card.items)
    assert all(t.goal >= 1 for t in card.items)
    assert all(t.progress >= 0 for t in card.items)