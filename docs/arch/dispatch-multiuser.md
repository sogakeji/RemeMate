# Dispatch 多用户化设计

> 记录日期：2026-06-22
> 状态：P1 实现

---

## 背景

MemoBuddy 的 dispatch 是单用户的：固定扫描一个用户的到期词，生成 Bark 推送和播客音频。RemeMate 需要改成按用户遍历，同时要解决：
1. 后台任务绕过 RLS（需要 BYPASSRLS 连接角色）
2. TTS 生成不能阻塞心跳循环
3. 推送幂等，避免重复推送
4. 用户各自配置 bark_url / podcast_token，互相隔离

---

## 架构拆分

**不要**把 Bark 推送和 TTS 生成塞进同一个 systemd timer。拆成独立任务：

```
systemd
├── rememate-bark.timer        每 15 分钟：扫描到期词，发 Bark 通知
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
    """每 15 分钟：遍历所有活跃用户，推送到期词"""
    users = get_active_users_with_bark()        # 有 bark_url 且有到期词的用户
    for user in users:
        try:
            bark_job.run(user_id=user.id)
        except Exception as e:
            logger.error(f"bark job failed for user {user.id}: {e}")
            continue                             # 单用户失败不影响其他用户

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

def run(user_id: int):
    settings = UserSettings.query.filter_by(user_id=user_id).first()
    if not settings or not settings.bark_url:
        return

    due_words = get_due_words(user_id=user_id, limit=5)
    if not due_words:
        return

    for word in due_words:
        idempotency_key = f"{user_id}:{word.id}:{word.due_date.date()}"
        if already_pushed(idempotency_key):         # 查 push_logs 防重复
            continue

        bark.push(
            url=settings.bark_url,
            title=word.word,
            body=get_short_meaning(word),
        )
        record_push(idempotency_key)

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

**幂等键**：`user_id:word_id:due_date` 当天唯一，避免同一天重复推同一个词。

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
    push_type       = db.Column(db.String(20))    # bark / podcast
    created_at      = db.Column(db.DateTime, default=datetime.utcnow)
```

保留 7 天，定期清理过期记录（dispatch runner 启动时清一次）。

---

## 活跃用户过滤

dispatch 不应该遍历所有注册用户（包括僵尸账号）。过滤条件：

```python
def get_active_users_with_bark():
    return (
        db.session.query(User)
        .join(UserSettings, User.id == UserSettings.user_id)
        .filter(
            User.is_active == True,
            UserSettings.bark_url.isnot(None),
            User.id.in_(
                db.session.query(Word.user_id)   # 有到期词的用户
                .join(WordList)
                .filter(Word.due_date <= datetime.utcnow())
            )
        )
        .all()
    )
```

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
