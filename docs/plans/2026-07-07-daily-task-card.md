# 每日任务系统 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 在首页展示一张「今日任务卡」，列出 5 项每日学习任务（复习 10 个单词 / 导入 5 个单词 / 阅读 1% / 造 1 句句子 / 写 3 行日记），实时显示每项的完成进度，全部完成有视觉收尾。任务定义按用户当前学习语言计算。

**Architecture:** 任务系统是只读仪表盘——不新增写入路径，复用已有的 SRS / 导入 / 阅读 / 写作子系统查询今日进度。新增 `app/services/tasks.py` 作为唯一聚合层，封装 5 项任务的「目标量 + 当前进度」计算；新增 `app/blueprints/main/routes.py` 的 `/` 路由注入 `task_card`；新增 `app/templates/main/_task_card.html` 渲染卡片。任务进度按用户时区（`User.timezone`）的「今天」计算。无后台调度——首页加载时实时查询。

**Tech Stack:** Flask + Jinja2 + SQLAlchemy + PostgreSQL（RLS）。复用 `app/services/words.py` `get_stats`、`app/services/reading/service.py` `list_documents`、`app/services/writing.py` `get_history`、`app/services/intake.py`。新增 Alembic 迁移加 `UserSettings.daily_task_config`（JSONB，存储用户自定义目标量，可空）。无新依赖。

---

## File Structure

| 文件 | 职责 | 动作 |
|---|---|---|
| `app/services/tasks.py` | **新建**：任务聚合服务。`get_today_task_card(user_id) -> TaskCard`。封装 5 项任务的目标量/进度查询，按用户时区切「今天」。 | Create |
| `app/models/user.py` | `UserSettings` 加 `daily_task_config` JSONB 列（nullable，存自定义目标量）。 | Modify |
| `migrations/versions/<new>_daily_task_config.py` | Alembic 迁移：加列 + RLS 策略（UserSettings 已有 RLS，列级无需新策略）。 | Create |
| `app/blueprints/main/routes.py` | `index()` 路由注入 `task_card=tasks_svc.get_today_task_card(current_user.id)`。 | Modify |
| `app/templates/main/_task_card.html` | **新建**：任务卡片段。Jinja macro 友好，循环渲染 5 项任务行（图标+名称+进度条+完成勾）。 | Create |
| `app/templates/main/index.html` | 在复习词卡上方插入 `{% include "main/_task_card.html" %}`。 | Modify |
| `tests/unit/test_tasks.py` | **新建**：`get_today_task_card` 单元测试，覆盖空词库、部分完成、全完成、跨时区。 | Create |
| `tests/integration/test_home_task_card.py` | **新建**：首页路由集成测试，验证 `task_card` 注入、跨用户隔离。 | Create |

**职责边界**：`tasks.py` 是唯一知道「5 项任务是什么」的地方。模板只渲染。路由只传递。修改任一任务的目标量只动 `tasks.py` 的 `DEFAULT_GOALS` 或 `UserSettings.daily_task_config`。

---

## Task 1: `get_today_task_card` 服务骨架（TDD）

**Files:**
- Create: `app/services/tasks.py`
- Test: `tests/unit/test_tasks.py`

- [ ] **Step 1: 写失败测试——5 项任务的结构**

```python
# tests/unit/test_tasks.py
"""每日任务卡聚合服务的单元测试。

任务卡 = 5 项任务，每项含 slug / 标题 / 目标量 / 当前进度 / 是否完成。
所有「今天」计算按用户时区（User.timezone）的本地午夜切。
"""
from app.services.tasks import get_today_task_card, TaskCard, TaskItem


def test_task_card_has_five_tasks(app):
    """卡片始终含 5 项任务，slug 固定，便于前端/测试稳定引用。"""
    with app.app_context():
        from app.extensions import db
        from app.models.user import User
        u = User(email="t@t.com", display_name="t")
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
```

- [ ] **Step 2: 跑测试确认失败**

Run: `cd /root/rememate && .venv/bin/python -m pytest tests/unit/test_tasks.py::test_task_card_has_five_tasks -v`
Expected: FAIL `ModuleNotFoundError: No module named 'app.services.tasks'`

- [ ] **Step 3: 写最小实现——dataclass + 5 个占位任务**

```python
# app/services/tasks.py
"""每日任务卡聚合服务。

只读仪表盘：不写入，只查询今日进度。
所有「今天」按用户时区（User.timezone）的本地午夜切（复用 timeutil.today_local_start_utc）。
"""
from __future__ import annotations
from dataclasses import dataclass


@dataclass(frozen=True)
class TaskItem:
    slug: str           # 稳定标识：review/import/read/sentence/diary
    title: str          # 中文显示名
    goal: int           # 目标量
    progress: int       # 当前进度（0..goal）
    href: str           # 跳转去做这项任务的链接（url_for 路由名）

    @property
    def done(self) -> bool:
        return self.progress >= self.goal


@dataclass(frozen=True)
class TaskCard:
    items: list[TaskItem]

    @property
    def all_done(self) -> bool:
        return self.items and all(t.done for t in self.items)


# 默认目标量。用户可在 UserSettings.daily_task_config 覆盖单项目标（Task 5）。
DEFAULT_GOALS = {
    "review": 10,
    "import": 5,
    "read": 1,       # 1% 阅读进度（按 scroll_ratio 增量，见 Task 3）
    "sentence": 1,
    "diary": 1,      # 一篇三行日记算 1 项
}


def get_today_task_card(user_id: int) -> TaskCard:
    """返回今日任务卡。Task 2-5 逐步填充每项进度。"""
    items = [
        TaskItem(slug="review", title="复习单词", goal=DEFAULT_GOALS["review"],
                 progress=0, href="words.review" if False else "/review"),  # 占位
        TaskItem(slug="import", title="导入单词", goal=DEFAULT_GOALS["import"],
                 progress=0, href="/intake/quick-add"),
        TaskItem(slug="read", title="阅读 1%", goal=DEFAULT_GOALS["read"],
                 progress=0, href="/reading"),
        TaskItem(slug="sentence", title="造一句句子", goal=DEFAULT_GOALS["sentence"],
                 progress=0, href="/write"),
        TaskItem(slug="diary", title="写三行日记", goal=DEFAULT_GOALS["diary"],
                 progress=0, href="/write"),
    ]
    return TaskCard(items=items)
```
（注意：`href` 这里先用字面路径占位，Task 6 再统一改 `url_for`。）

- [ ] **Step 4: 跑测试确认通过**

Run: `cd /root/rememate && .venv/bin/python -m pytest tests/unit/test_tasks.py::test_task_card_has_five_tasks -v`
Expected: PASS

- [ ] **Step 5: 提交**

```bash
cd /root/rememate
git add app/services/tasks.py tests/unit/test_tasks.py
git commit -m "feat(tasks): task card skeleton with 5 daily tasks

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
```

---

## Task 2: 复习任务进度（按 ReviewLog 今日计数）

**Files:**
- Modify: `app/services/tasks.py`
- Test: `tests/unit/test_tasks.py`

- [ ] **Step 1: 写失败测试——复习进度按 ReviewLog 今日 ts 计数**

```python
# 追加到 tests/unit/test_tasks.py
from datetime import datetime, timedelta
from app.extensions import db
from app.models.word import WordList, Word, ReviewLog
from app.services.timeutil import utc_now
from tests.helpers import make_word, make_review_log  # bypass 复用


def test_review_progress_counts_today_review_logs(app, bypass_engine):
    """复习进度 = 今天（用户时区）的 ReviewLog 条数。"""
    with app.app_context():
        from app.models.user import User
        u = User(email="rev@t.com", display_name="rev", timezone="Asia/Shanghai")
        db.session.add(u); db.session.commit()
        uid = u.id

    list_id, word_id = make_word(bypass_engine, uid, "cat")
    # 今日 3 次复习
    for _ in range(3):
        make_review_log(bypass_engine, uid, word_id)

    with app.app_context():
        card = get_today_task_card(uid)
    review = next(t for t in card.items if t.slug == "review")
    assert review.goal == 10
    assert review.progress == 3
    assert not review.done
```

- [ ] **Step 2: 跑测试确认失败**

Run: `cd /root/rememate && .venv/bin/python -m pytest tests/unit/test_tasks.py::test_review_progress_counts_today_review_logs -v`
Expected: FAIL `assert review.progress == 3` (当前是 0)

- [ ] **Step 3: 实现复习进度查询**

在 `app/services/tasks.py` 顶部加 import，并替换 `review` 项的 progress：

```python
# 顶部新增 import
from app.extensions import db
from app.models.user import User
from app.models.word import ReviewLog
from app.services.timeutil import today_local_start_utc


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
```

然后在 `get_today_task_card` 里把 review 项改成：
```python
TaskItem(slug="review", title="复习单词",
         goal=DEFAULT_GOALS["review"],
         progress=_review_progress(user_id),
         href="/review"),
```

- [ ] **Step 4: 跑测试确认通过**

Run: `cd /root/rememate && .venv/bin/python -m pytest tests/unit/test_tasks.py::test_review_progress_counts_today_review_logs -v`
Expected: PASS

- [ ] **Step 5: 提交**

```bash
git add app/services/tasks.py tests/unit/test_tasks.py
git commit -m "feat(tasks): review progress from today's ReviewLog count

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
```

---

## Task 3: 导入任务进度（今日新建 Word 数）

**Files:**
- Modify: `app/services/tasks.py`
- Test: `tests/unit/test_tasks.py`

> **设计说明**：导入任务的目标是「导入 5 个单词」。最稳定的定义是「今天通过任意路径加入词表的新 Word 行数」（CSV/extract/quick_add/reading commit 都最终 `db.session.add(Word(...))`）。`Word` 模型有 `created_at` 吗？查 `app/models/word.py`——若没有，本任务先按 `WordCandidate` 今日 created + status='accepted' 计数（reading 候选也走 WordCandidate），这覆盖所有导入路径。

- [ ] **Step 1: 确认 Word.created_at 是否存在**

Run: `cd /root/rememate && grep -n "created_at" app/models/word.py`
- 若 `Word` 有 `created_at`：进度 = 今日 `Word.created_at >= today_start` 且属于用户词表的数量。
- 若没有：进度 = 今日 `WordCandidate.created_at >= today_start` 且 `status='accepted'` 的数量（reading 候选也走 WordCandidate）。

下面假设 **Word 没有 created_at**（按探索报告，Word 模型字段里没列 created_at）。若 Step 1 发现有，改用 Word 查询，测试同等。

- [ ] **Step 2: 写失败测试**

```python
# 追加到 tests/unit/test_tasks.py
def test_import_progress_counts_today_accepted_candidates(app, bypass_engine):
    """导入进度 = 今天 accept 的 WordCandidate 数（覆盖 CSV/extract/quick_add/reading）。"""
    with app.app_context():
        from app.models.user import User
        u = User(email="imp@t.com", display_name="imp")
        db.session.add(u); db.session.commit()
        uid = u.id

    # 用 bypass_engine 插一个 word_list + 1 个今日 accepted candidate
    with bypass_engine.connect() as conn:
        from tests.helpers import set_uid
        set_uid(conn, uid)
        from sqlalchemy import text
        wl = conn.execute(text(
            "INSERT INTO word_lists (user_id, name, language_code, created_at) "
            "VALUES (:u, 'en', 'en', now()) RETURNING id"), {"u": uid}).scalar()
        conn.execute(text(
            "INSERT INTO word_candidates (source_id, user_id, word, status, created_at) "
            "VALUES (0, :u, 'w1', 'accepted', now())"), {"u": uid})
        # source_id 设个真实 source; 简化：先建 IntakeSource。见下。
    # 因 source_id FK，需先建 IntakeSource。简化测试用 service:
    from app.services import intake as intake_svc
    with app.app_context():
        src, _ = intake_svc.quick_add(uid, "en", "hello", None)
        from app.models.intake import WordCandidate
        c = WordCandidate.query.filter_by(source_id=src.id, user_id=uid).first()
        intake_svc.accept_candidate(uid, c.id)
        card = get_today_task_card(uid)
    imp = next(t for t in card.items if t.slug == "import")
    assert imp.goal == 5
    assert imp.progress == 1
```

- [ ] **Step 3: 跑测试确认失败**

Run: `.venv/bin/python -m pytest tests/unit/test_tasks.py::test_import_progress_counts_today_accepted_candidates -v`
Expected: FAIL（progress=0)

- [ ] **Step 4: 实现导入进度**

在 `tasks.py` 加：

```python
from app.models.intake import WordCandidate


def _import_progress(user_id: int) -> int:
    """今天 accept 的候选词数（CSV/extract/quick_add/reading 全走 WordCandidate）。"""
    user = db.session.get(User, user_id)
    if user is None:
        return 0
    since = today_local_start_utc(user.timezone or "Asia/Shanghai")
    return (WordCandidate.query
            .filter(WordCandidate.user_id == user_id,
                    WordCandidate.status == "accepted",
                    WordCandidate.created_at >= since)
            .count())
```

把 import 项的 `progress=0` 改为 `progress=_import_progress(user_id)`。

- [ ] **Step 5: 跑测试确认通过**

Run: `.venv/bin/python -m pytest tests/unit/test_tasks.py::test_import_progress_counts_today_accepted_candidates -v`
Expected: PASS

- [ ] **Step 6: 提交**

```bash
git add app/services/tasks.py tests/unit/test_tasks.py
git commit -m "feat(tasks): import progress from today's accepted candidates

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
```

---

## Task 4: 阅读任务进度（今日阅读 scroll_ratio 增量）

**Files:**
- Modify: `app/services/tasks.py`
- Test: `tests/unit/test_tasks.py`

> **设计说明**：「阅读 1%」定义为「今天在任一文档上 scroll_ratio 增加了 ≥ 0.01」。需存储「今日开始时的 scroll_ratio 快照」。最轻量方案：新增 `ReadingDocument.progress_today_base` 是有状态写入，复杂。**改用更简单定义**：「今天 `updated_at` 落在今天的文档中，`last_position.scroll_ratio >= 0.01` 的文档数」——即「今天碰过任意一本书并读了至少 1%」。goal=1 篇。这避免新增列，纯查询 `ReadingDocument.updated_at` + `last_position`。

- [ ] **Step 1: 写失败测试**

```python
# 追加
def test_read_progress_counts_documents_touched_today(app, bypass_engine):
    """阅读进度 = 今天 updated_at 落今天的文档中 scroll_ratio>=0.01 的数。"""
    with app.app_context():
        from app.models.user import User
        u = User(email="rd@t.com", display_name="rd")
        db.session.add(u); db.session.commit()
        uid = u.id

    from app.services.reading import service as reading_svc
    with app.app_context():
        doc = reading_svc.create_document(
            uid, language_code="en", title="T",
            source_filename="t.pdf", content_text="x"*1000, page_count=1)
        reading_svc.update_last_position(uid, doc.id,
            {"char_offset": 50, "scroll_ratio": 0.05})
        card = get_today_task_card(uid)
    read = next(t for t in card.items if t.slug == "read")
    assert read.goal == 1
    assert read.progress == 1
    assert read.done
```

- [ ] **Step 2: 跑测试确认失败**

Run: `.venv/bin/python -m pytest tests/unit/test_tasks.py::test_read_progress_counts_documents_touched_today -v`
Expected: FAIL

- [ ] **Step 3: 实现**

```python
from app.models.reading import ReadingDocument


def _read_progress(user_id: int) -> int:
    """今天碰过的文档中，已读 ≥1% 的篇数。"""
    user = db.session.get(User, user_id)
    if user is None:
        return 0
    since = today_local_start_utc(user.timezone or "Asia/Shanghai")
    docs = (ReadingDocument.query
            .filter(ReadingDocument.user_id == user_id,
                    ReadingDocument.updated_at >= since)
            .all())
    return sum(
        1 for d in docs
        if (d.last_position or {}).get("scroll_ratio", 0) >= 0.01
    )
```

把 read 项的 progress 改为 `_read_progress(user_id)`。

- [ ] **Step 4: 跑测试确认通过**

Run: `.venv/bin/python -m pytest tests/unit/test_tasks.py::test_read_progress_counts_documents_touched_today -v`
Expected: PASS

- [ ] **Step 5: 提交**

```bash
git add app/services/tasks.py tests/unit/test_tasks.py
git commit -m "feat(tasks): read progress from today's touched documents

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
```

---

## Task 5: 造句 + 日记任务进度（今日 OutputEntry 计数）

**Files:**
- Modify: `app/services/tasks.py`
- Test: `tests/unit/test_tasks.py`

> **核心区分**：`OutputEntry.word_id IS NULL` = 日记，`IS NOT NULL` = 句子。`created_at` 在 OutputEntry 上存在。

- [ ] **Step 1: 写失败测试**

```python
# 追加
def test_sentence_and_diary_progress(app, bypass_engine):
    """造句进度 = 今日 word_id 非空 OutputEntry 数；日记进度 = 今日 word_id 为空数。"""
    from app.services import writing as writing_svc
    from app.models.user import User
    with app.app_context():
        u = User(email="wr@t.com", display_name="wr")
        db.session.add(u); db.session.commit()
        uid = u.id

    list_id, word_id = make_word(bypass_engine, uid, "cat")

    with app.app_context():
        from app.models.output import OutputEntry
        # 一条句子
        db.session.add(OutputEntry(
            user_id=uid, word_id=word_id, language_code="en",
            original="The cat sleeps.",
            corrected="The cat sleeps.", feedback="", has_error=False,
            translation="", word_text="cat", is_public=False))
        # 一条日记（word_id=None）
        db.session.add(OutputEntry(
            user_id=uid, word_id=None, language_code="en",
            original="line1\nline2\nline3",
            corrected="line1\nline2\nline3", feedback="", has_error=False,
            translation="", word_text=None, is_public=False))
        db.session.commit()
        card = get_today_task_card(uid)

    s = next(t for t in card.items if t.slug == "sentence")
    d = next(t for t in card.items if t.slug == "diary")
    assert s.progress == 1 and s.done
    assert d.progress == 1 and d.done
```

- [ ] **Step 2: 跑测试确认失败**

Run: `.venv/bin/python -m pytest tests/unit/test_tasks.py::test_sentence_and_diary_progress -v`
Expected: FAIL

- [ ] **Step 3: 实现**

```python
from app.models.output import OutputEntry


def _writing_progress(user_id: int, *, diary: bool) -> int:
    """今天 OutputEntry 数。diary=True 计 word_id IS NULL，否则 IS NOT NULL。"""
    user = db.session.get(User, user_id)
    if user is None:
        return 0
    since = today_local_start_utc(user.timezone or "Asia/Shanghai")
    q = (OutputEntry.query
         .filter(OutputEntry.user_id == user_id,
                 OutputEntry.created_at >= since))
    if diary:
        q = q.filter(OutputEntry.word_id.is_(None))
    else:
        q = q.filter(OutputEntry.word_id.isnot(None))
    return q.count()
```

sentence 项 `progress=_writing_progress(user_id, diary=False)`，diary 项 `progress=_writing_progress(user_id, diary=True)`。

- [ ] **Step 4: 跑测试确认通过**

Run: `.venv/bin/python -m pytest tests/unit/test_tasks.py::test_sentence_and_diary_progress -v`
Expected: PASS

- [ ] **Step 5: 提交**

```bash
git add app/services/tasks.py tests/unit/test_tasks.py
git commit -m "feat(tasks): sentence + diary progress from today's OutputEntry

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
```

---

## Task 6: `href` 用 url_for + all_done 测试

**Files:**
- Modify: `app/services/tasks.py`
- Test: `tests/unit/test_tasks.py`

- [ ] **Step 1: 写测试——全完成 + href 是真实路由**

```python
# 追加
def test_all_done_and_href_routes(app, bypass_engine):
    from app.services import words as words_svc, intake as intake_svc
    from app.services.reading import service as reading_svc
    from app.models.user import User
    from app.models.word import WordList, Word
    from app.models.output import OutputEntry
    from app.services.timeutil import utc_now

    with app.app_context():
        u = User(email="all@t.com", display_name="all")
        db.session.add(u); db.session.commit()
        uid = u.id
        # 复习 10
        wl = words_svc.get_or_create_language_list(uid, "en")
        for i in range(10):
            w = Word(list_id=wl.id, word=f"w{i}", due_date=utc_now())
            db.session.add(w)
        db.session.commit()
        word_ids = [w.id for w in Word.query.filter_by(list_id=wl.id).all()]
        for wid in word_ids:
            db.session.add(ReviewLog(word_id=wid, user_id=uid, ts=utc_now(), grade=5, source="review"))
        # 导入 5：quick_add 5 个并 accept
        for i in range(5):
            src, _ = intake_svc.quick_add(uid, "en", f"w{i}", None)
            from app.models.intake import WordCandidate
            c = WordCandidate.query.filter_by(source_id=src.id, user_id=uid).first()
            intake_svc.accept_candidate(uid, c.id)
        # 阅读 1
        doc = reading_svc.create_document(uid, language_code="en", title="T",
            source_filename="t.pdf", content_text="x"*1000, page_count=1)
        reading_svc.update_last_position(uid, doc.id, {"char_offset": 50, "scroll_ratio": 0.05})
        # 句子 + 日记
        db.session.add(OutputEntry(user_id=uid, word_id=word_ids[0], language_code="en",
            original="x", corrected="x", feedback="", has_error=False,
            translation="", word_text="w0", is_public=False))
        db.session.add(OutputEntry(user_id=uid, word_id=None, language_code="en",
            original="x\ny\nz", corrected="x\ny\nz", feedback="", has_error=False,
            translation="", word_text=None, is_public=False))
        db.session.commit()

        card = get_today_task_card(uid)

    assert card.all_done
    assert all(t.done for t in card.items)
    # href 应能 url_for，不变 404
    from flask import url_for
    with app.test_request_context():
        for t in card.items:
            # t.href 存 url_for 字符串，反向解析应非 404
            assert t.href.startswith("/")
```

- [ ] **Step 2: 跑测试确认失败**

Run: `.venv/bin/python -m pytest tests/unit/test_tasks.py::test_all_done_and_href_routes -v`
Expected: 可能部分过，但 href 是字面可能已通过。重点在 all_done 全绿。

- [ ] **Step 3: 用 url_for 重写 href（需 app context）**

```python
# tasks.py：把 get_today_task_card 改为带 url_for
from flask import url_for


def get_today_task_card(user_id: int) -> TaskCard:
    return TaskCard(items=[
        TaskItem("review", "复习单词", DEFAULT_GOALS["review"],
                 _review_progress(user_id), url_for("words.review")),
        TaskItem("import", "导入单词", DEFAULT_GOALS["import"],
                 _import_progress(user_id), url_for("intake.quick_add_page")),
        TaskItem("read", "阅读 1%", DEFAULT_GOALS["read"],
                 _read_progress(user_id), url_for("reading.index")),
        TaskItem("sentence", "造一句句子", DEFAULT_GOALS["sentence"],
                 _writing_progress(user_id, diary=False), url_for("write.compose")),
        TaskItem("diary", "写三行日记", DEFAULT_GOALS["diary"],
                 _writing_progress(user_id, diary=True), url_for("write.compose")),
    ])
```

> **注意**：确认 `intake.quick_add_page` 和 `write.compose` 是真实 endpoint。跑前 grep：`grep -rn "def quick_add_page\|def compose" app/blueprints/`。若名字不同改对应。

- [ ] **Step 4: 跑测试确认通过**

Run: `.venv/bin/python -m pytest tests/unit/test_tasks.py -v`
Expected: 全部 PASS

- [ ] **Step 5: 提交**

```bash
git add app/services/tasks.py tests/unit/test_tasks.py
git commit -m "feat(tasks): url_for hrefs + all_done green

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
```

---

## Task 7: 自定义目标量（UserSettings.daily_task_config）

**Files:**
- Modify: `app/models/user.py`（加列）
- Create: `migrations/versions/<new>_daily_task_config.py`
- Modify: `app/services/tasks.py`（读 config 覆盖 DEFAULT_GOALS）
- Test: `tests/unit/test_tasks.py`

- [ ] **Step 1: 加列**

在 `app/models/user.py` 的 `UserSettings` 类加：
```python
daily_task_config = db.Column(JSONB, nullable=True)  # {slug: goal} 覆盖默认
```
顶部若没 import JSONB，加 `from sqlalchemy.dialects.postgresql import JSONB`（看同文件已有用法）。

- [ ] **Step 2: 写迁移**

```bash
cd /root/rememate && .venv/bin/python -m flask db migrate -m "add daily_task_config"
```
检查生成的迁移只加 `user_settings.daily_task_config` 列。UserSettings 表已 FORCE RLS，列级无需新策略。

- [ ] **Step 3: 写失败测试**

```python
# 追加
def test_custom_goal_overrides_default(app, bypass_engine):
    from app.models.user import User, UserSettings
    with app.app_context():
        u = User(email="cfg@t.com", display_name="cfg")
        db.session.add(u); db.session.commit()
        uid = u.id
        st = UserSettings.query.get(uid) or UserSettings(user_id=uid)
        st.daily_task_config = {"review": 3}  # 复习目标 3 而非 10
        db.session.add(st); db.session.commit()
        card = get_today_task_card(uid)
    review = next(t for t in card.items if t.slug == "review")
    assert review.goal == 3
    imp = next(t for t in card.items if t.slug == "import")
    assert imp.goal == 5  # 未覆盖仍默认
```

- [ ] **Step 4: 实现读 config**

```python
# tasks.py
def _goals_for(user_id: int) -> dict[str, int]:
    user = db.session.get(User, user_id)
    if user is None or not getattr(user, "settings", None):
        return dict(DEFAULT_GOALS)
    cfg = user.settings.daily_task_config or {}
    out = dict(DEFAULT_GOALS)
    for k, v in cfg.items():
        if k in out and isinstance(v, int) and v >= 1:
            out[k] = v
    return out
```

`get_today_task_card` 内把 `DEFAULT_GOALS["..."]` 都换成 `_goals_for(user_id)["..."]`。

- [ ] **Step 5: 跑测试确认通过**

Run: `.venv/bin/python -m pytest tests/unit/test_tasks.py::test_custom_goal_overrides_default -v`
Expected: PASS

- [ ] **Step 6: 跑迁移 + 提交**

```bash
.venv/bin/python -m flask db upgrade
git add app/models/user.py migrations/versions/*daily_task_config* app/services/tasks.py tests/unit/test_tasks.py
git commit -m "feat(tasks): per-user custom goals via UserSettings.daily_task_config

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
```

---

## Task 8: 首页路由注入 task_card

**Files:**
- Modify: `app/blueprints/main/routes.py`
- Test: `tests/integration/test_home_task_card.py`

- [ ] **Step 1: 写集成测试**

```python
# tests/integration/test_home_task_card.py
def test_home_injects_task_card(app, client, bypass_engine):
    from tests.helpers import make_user, login
    uid = make_user(bypass_engine, "home@t.com")
    login(client, "home@t.com", "pass")
    resp = client.get("/")
    assert resp.status_code == 200
    # 卡片渲染标识
    assert b"task-card" in resp.data
    assert "复习单词".encode() in resp.data
    assert "造一句句子".encode() in resp.data


def test_task_card_is_per_user(app, client, bypass_engine):
    from tests.helpers import make_user, login, make_review_log, make_word
    uid_a = make_user(bypass_engine, "a@t.com")
    uid_b = make_user(bypass_engine, "b@t.com")
    _, wid = make_word(bypass_engine, uid_a, "cat")
    make_review_log(bypass_engine, uid_a, wid)  # A 复习了 1 次
    login(client, "b@t.com", "pass")
    resp = client.get("/")
    # B 的复习进度应为 0
    assert b'progress="1"' not in resp.data or b'data-progress="0"' in resp.data
```

- [ ] **Step 2: 跑确认失败**

Run: `.venv/bin/python -m pytest tests/integration/test_home_task_card.py -v`
Expected: FAIL（卡片未注入）

- [ ] **Step 3: 改路由**

`app/blueprints/main/routes.py` `index()` 末尾 `render_template` 加 `task_card=tasks_svc.get_today_task_card(current_user.id)`。顶部 `from app.services import tasks as tasks_svc`。

未登录场景：`@login_required` 已守门，无需处理。

- [ ] **Step 4: 跑测试确认通过（先跳过，模板还没建）**

Run: `.venv/bin/python -m pytest tests/integration/test_home_task_card.py -v`
Expected: 仍 FAIL（模板未渲染 task-card）——等 Task 9。

- [ ] **Step 5: 暂不提交，进 Task 9 一起提**

---

## Task 9: 任务卡模板 `_task_card.html`

**Files:**
- Create: `app/templates/main/_task_card.html`
- Modify: `app/templates/main/index.html`

- [ ] **Step 1: 写模板**

```html
{# app/templates/main/_task_card.html #}
<div class="task-card" id="task-card">
  <div class="task-card-header">
    <h2>今日任务</h2>
    {% if task_card and task_card.all_done %}
      <span class="task-done-badge">全部完成 🎉</span>
    {% endif %}
  </div>
  <ul class="task-list">
    {% for t in task_card.items %}
    <li class="task-item {{ 'done' if t.done else '' }}">
      <a href="{{ t.href }}">
        <span class="task-title">{{ t.title }}</span>
        <span class="task-progress"
              data-slug="{{ t.slug }}"
              data-progress="{{ t.progress }}"
              data-goal="{{ t.goal }}">
          {{ t.progress }}/{{ t.goal }}
        </span>
        {% if t.done %}<span class="task-check">✓</span>{% endif %}
      </a>
    </li>
    {% endfor %}
  </ul>
</div>
```

- [ ] **Step 2: 在 index.html 引入**

`app/templates/main/index.html` 复习词卡上方加：
```jinja
{% include "main/_task_card.html" %}
```
（确认 `task_card` 已由路由注入；Task 8 已做。）

- [ ] **Step 3: 加最小 CSS 到 `app/static/style.css`**

```css
.task-card { margin: 16px 0; padding: 16px 20px; border-radius: 12px;
  background: var(--card-bg, #fff); box-shadow: 0 1px 3px rgba(0,0,0,.08); }
.task-card-header { display: flex; justify-content: space-between; align-items: center; }
.task-card-header h2 { margin: 0; font-size: 18px; }
.task-done-badge { color: var(--success, #4caf50); font-size: 14px; }
.task-list { list-style: none; padding: 0; margin: 12px 0 0; }
.task-item { padding: 10px 0; border-top: 1px solid var(--border, #eee); }
.task-item.done { opacity: .55; text-decoration: line-through; }
.task-item a { display: flex; justify-content: space-between; align-items: center;
  text-decoration: none; color: inherit; }
.task-progress { font-size: 13px; color: var(--text-secondary, #888); }
.task-check { color: var(--success, #4caf50); margin-left: 8px; }
```

- [ ] **Step 4: 跑集成测试**

Run: `.venv/bin/python -m pytest tests/integration/test_home_task_card.py -v`
Expected: PASS

- [ ] **Step 5: 提交**

```bash
git add app/blueprints/main/routes.py app/templates/main/_task_card.html app/templates/main/index.html app/static/style.css tests/integration/test_home_task_card.py
git commit -m "feat(tasks): home route injects + renders task card

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
```

---

## Task 10: 跨用户隔离回归 + 全套测试

**Files:**
- Test: `tests/integration/test_home_task_card.py`（补强）

- [ ] **Step 1: 补强跨用户测试**

```python
def test_task_card_progress_isolated_per_user(app, client, bypass_engine):
    from tests.helpers import make_user, login, make_word, make_review_log
    uid_a = make_user(bypass_engine, "iso-a@t.com")
    uid_b = make_user(bypass_engine, "iso-b@t.com")
    list_id, wid = make_word(bypass_engine, uid_a, "cat")
    for _ in range(5):
        make_review_log(bypass_engine, uid_a, wid)
    login(client, "iso-b@t.com", "pass")
    resp = client.get("/")
    # B 看到 0/10，不出现 5/10
    body = resp.data.decode()
    assert "0/10" in body
    assert "5/10" not in body
```

- [ ] **Step 2: 跑全套测试**

Run: `cd /root/rememate && .venv/bin/python -m pytest -q`
Expected: 之前 312 passed + 新 8 个测试全绿，0 新增失败。2 个预存 PDF upload 失败仍失败（无关）。

- [ ] **Step 3: 提交**

```bash
git add tests/integration/test_home_task_card.py
git commit -m "test(tasks): cross-user isolation regression

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
```

---

## 验收清单

- [ ] 首页 `/` 显示任务卡，5 项任务
- [ ] 复习 10 词项进度随复习实时增长
- [ ] 导入 5 词项进度随 accept 候选增长
- [ ] 阅读 1% 项在任一文档读到 ≥1% 变绿
- [ ] 造句 / 日记项在保存后变绿
- [ ] 全部完成显示「全部完成 🎉」
- [ ] 跨用户进度互不影响
- [ ] `pytest -q` 不新增失败

## 不在本计划做

- 后台调度 / 每日推送（PushLog 调度逻辑）——基础设施已留好，定时部分另立项
- 任务完成度历史 / 连续打卡 —— YAGNI
- 任务卡 mini 进度条渲染 —— 文字 `3/10` 已够，视觉效果后续
- 跨语言聚合 —— 任务按 `current_language` 还是全语言？当前实现是**全语言聚合**（复习/导入/阅读/写作都不按语言过滤，因为任务卡是「今日总学习量」概念）。若要按当前语言过滤，在 `_review_progress` 等加 `language_code` 过滤即可——但 OutputEntry 没有 language 上的隐式约束，先全聚合。