# Dispatch 多用户化设计

> 记录日期：2026-06-22（更新：2026-06-23）
> 状态：P1 实现

---

## 背景

MemoBuddy 的 dispatch 是单用户的：固定扫描一个用户的到期词，生成 Bark 推送和播客音频。RemeMate 需要改成按用户遍历，同时要解决：
1. 后台任务绕过 RLS（需要 BYPASSRLS 连接角色）
2. TTS 生成不能阻塞心跳循环
3. 推送幂等，避免重复推送
4. 用户各自配置 bark_url / podcast_token，互相隔离

Bark 推送支持多种通知类型，每种类型用户可独立开关（见下文§通知类型与开关）。

---

## 通知类型与开关

Bark 推送分四种独立类型，`user_settings` 各有一个布尔开关：

| 字段 | 通知类型 | 默认 | 触发时机 |
|---|---|---|---|
| `notify_review_reminder` | 单词复习提醒 | `true` | 每 15 min bark timer，有到期词时推 |
| `notify_daily_summary` | 每日学习摘要 | `true` | 每日固定时间（用户 timezone 早上 8:00）|
| `notify_intake_done` | 导入完成通知 | `true` | `/intake/<source_id>/commit` 成功后即时推 |
| `notify_partner_activity` | 搭子动态（P2） | `false` | Session Pad P2 上线后启用，P1 字段预留但不触发 |

- `bark_url` 为空时，所有通知类型均静默，不报错
- 各开关默认值在 `flask create-user` 建账号时写入 `user_settings`

---

## 架构拆分

**不要**把 Bark 推送和 TTS 生成塞进同一个 systemd timer。拆成独立任务：

```
systemd
├── rememate-bark.timer        每 15 分钟：扫描到期词，发复习提醒
├── rememate-summary.timer     每日 08:00 UTC：发每日摘要（各用户本地时间由 runner 换算）
├── rememate-podcast.timer     每小时：生成播客音频（TTS 慢，独立运行）
└── rememate-backup.timer      每日 03:30：pg_dump 备份
```

加 `flock` 防止重叠执行：
```bash
# rememate-bark.service
ExecStart=/usr/bin/flock -n /tmp/rememate-bark.lock \
    /home/rememate/venv/bin/python -m dispatch.runner bark
```

---

## dispatch runner 结构

```python
# dispatch/runner.py

def run_bark():
    """每 15 分钟：遍历活跃用户，推复习提醒（notify_review_reminder=true）"""
    users = get_active_users_with_bark(notify_field="notify_review_reminder")
    for user in users:
        try:
            bark_job.run_review_reminder(user_id=user.id)
        except Exception as e:
            logger.error(f"bark review reminder failed for user {user.id}: {e}")
            continue

def run_daily_summary():
    """每小时触发，runner 内部按用户 timezone 判断是否到本地 08:00"""
    users = get_active_users_with_bark(notify_field="notify_daily_summary")
    now_utc = datetime.utcnow()
    for user in users:
        try:
            if not is_summary_time(user, now_utc):   # 换算本地时间，非 08:00 跳过
                continue
            bark_job.run_daily_summary(user_id=user.id)
        except Exception as e:
            logger.error(f"bark daily summary failed for user {user.id}: {e}")
            continue

def run_podcast():
    """每小时：遍历用户，生成播客音频"""
    users = get_active_users_with_podcast()
    for user in users:
        try:
            podcast_job.run(user_id=user.id)
        except Exception as e:
            logger.error(f"podcast job failed for user {user.id}: {e}")
            continue
```

`is_summary_time` 判断逻辑：读 `user_settings.timezone`（默认 `Asia/Shanghai`），换算当前 UTC 时间到本地时间，若本地时 `08:00–08:14`（15 min 窗口）则触发，配合幂等键防止重复推。

---

## BYPASSRLS 连接配置

dispatch 使用独立 Postgres 角色，绕过 RLS（见 data-isolation-security.md §后台任务）：

```python
# dispatch/runner.py
import os
from sqlalchemy import create_engine

DISPATCH_DB_URL = os.environ["DISPATCH_DATABASE_URL"]
# DISPATCH_DATABASE_URL 对应 BYPASSRLS 角色的连接串
# 例：postgresql://rememate_dispatch:password@localhost/rememate

dispatch_engine = create_engine(DISPATCH_DB_URL)
```

dispatch 的所有查询必须显式带 `user_id` 过滤，不依赖 RLS 隔离。

---

## Bark 推送 Job

```python
# dispatch/jobs/bark_job.py

def run_review_reminder(user_id: int):
    """复习提醒：推最多 5 个到期词，每词一条通知"""
    settings = UserSettings.query.filter_by(user_id=user_id).first()
    if not settings or not settings.bark_url:
        return

    due_words = get_due_words(user_id=user_id, limit=5)
    for word in due_words:
        idempotency_key = f"{user_id}:review:{word.id}:{word.due_date.date()}"
        if already_pushed(idempotency_key):
            continue
        bark.push(
            url=settings.bark_url,
            title=word.word,
            body=get_short_meaning(word),
        )
        record_push(idempotency_key, push_type="review_reminder")


def run_daily_summary(user_id: int):
    """每日摘要：昨日导入词数 + 今日到期词数，一条通知"""
    settings = UserSettings.query.filter_by(user_id=user_id).first()
    if not settings or not settings.bark_url:
        return

    today = date.today()
    idempotency_key = f"{user_id}:summary:{today}"
    if already_pushed(idempotency_key):
        return

    yesterday_imported = count_imported_yesterday(user_id)
    due_today = count_due_today(user_id)

    parts = []
    if yesterday_imported:
        parts.append(f"昨日导入 {yesterday_imported} 词")
    if due_today:
        parts.append(f"今日到期 {due_today} 词")
    if not parts:
        return  # 无内容不推

    bark.push(
        url=settings.bark_url,
        title="记搭 · 今日概览",
        body=" · ".join(parts),
    )
    record_push(idempotency_key, push_type="daily_summary")


def run_intake_done(user_id: int, source_id: int, accepted_count: int):
    """导入完成即时通知：由 /intake/<source_id>/commit 路由直接调用，非 timer"""
    settings = UserSettings.query.filter_by(user_id=user_id).first()
    if not settings or not settings.bark_url:
        return
    if not settings.notify_intake_done:
        return

    bark.push(
        url=settings.bark_url,
        title="导入完成",
        body=f"已收录 {accepted_count} 个词，开始复习吧",
    )
    # 即时推送无需幂等键（用户操作触发，不会重复）


def get_due_words(user_id: int, limit: int) -> list[Word]:
    return (
        Word.query
        .join(WordList)
        .filter(
            WordList.user_id == user_id,
            Word.due_date <= datetime.utcnow(),
        )
        .order_by(Word.due_date)
        .limit(limit)
        .all()
    )
```

**幂等键规范**：
- 复习提醒：`{user_id}:review:{word_id}:{due_date}` — 同词同天唯一
- 每日摘要：`{user_id}:summary:{date}` — 同用户同天唯一
- 导入完成：无幂等键（用户主动操作，不走 timer）

---

## 播客 Job

```python
# dispatch/jobs/podcast_job.py

def run(user_id: int):
    settings = UserSettings.query.filter_by(user_id=user_id).first()
    if not settings or not settings.podcast_token:
        return

    due_words = get_due_words(user_id=user_id, limit=20)
    if not due_words:
        return

    audio_path = generate_podcast_audio(user_id=user_id, words=due_words)
    # 音频存 ~/rememate/audio/<user_id>/<date>.mp3
    # P2 迁移到对象存储（S3/R2）
    update_podcast_feed(user_id=user_id, audio_path=audio_path)
```

TTS 生成（edge-tts）是阻塞操作，每用户约 10–30 秒。独立 timer 保证不影响 Bark 心跳。

---

## 推送幂等记录表

```python
class PushLog(db.Model):
    id              = db.Column(db.Integer, primary_key=True)
    idempotency_key = db.Column(db.String(200), unique=True)
    user_id         = db.Column(db.Integer, db.ForeignKey("users.id"))
    push_type       = db.Column(db.String(30))  # review_reminder / daily_summary / podcast
    created_at      = db.Column(db.DateTime, default=datetime.utcnow)
```

保留 7 天，定期清理过期记录（dispatch runner 启动时清一次）。

---

## 活跃用户过滤

dispatch 不应该遍历所有注册用户（包括僵尸账号）。`get_active_users_with_bark` 接受 `notify_field` 参数，过滤对应开关已开启的用户：

```python
def get_active_users_with_bark(notify_field: str):
    return (
        db.session.query(User)
        .join(UserSettings, User.id == UserSettings.user_id)
        .filter(
            User.is_active == True,
            UserSettings.bark_url.isnot(None),
            getattr(UserSettings, notify_field) == True,
        )
        .all()
    )
```

复习提醒额外要求"有到期词"，在 `run_review_reminder` 内部判断（`get_due_words` 返回空则直接 return），不在过滤层做，避免过滤逻辑与业务逻辑耦合。

---

## 触发阈值评估

| 用户规模 | Bark 遍历时间 | 是否超过 15 min timer |
|---|---|---|
| 100 用户 | < 30 秒 | 安全 |
| 500 用户 | ~2 分钟 | 安全 |
| 2000 用户 | ~8 分钟 | 安全（含 flock 保护） |
| 5000 用户 | ~20 分钟 | 接近边界，届时优化批量推送 |

播客 TTS 每用户 ~20 秒，500 用户需要约 2.5 小时。届时需要并发处理或增量生成（只生成新增词），但这是 P2 问题。

---

## 与 Flask app 的关系

dispatch 是独立进程，不走 Flask HTTP 层，但共享：
- 数据库（独立 BYPASSRLS 连接）
- models（直接 import）
- services/bark.py、services/podcast.py、services/srs.py

不共享：
- Flask app context（dispatch 用独立 SQLAlchemy engine）
- blueprints、routes、templates
- Flask-Login session
