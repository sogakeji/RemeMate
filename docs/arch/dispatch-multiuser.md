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

## 推送通道

支持两条独立通道，用户可同时配置（都填了就两边都推）：

| 字段 | 通道 | 适用场景 |
|---|---|---|
| `bark_url` | Bark（APNs）| iOS，需自建或使用官方 Bark 服务端 |
| `webhook_url` | 通用 Webhook | Android（通知滤盒 / Tasker）或任意 HTTP 接收端 |

Webhook 格式（POST JSON）：
```json
{"title": "记搭 · 今日概览", "body": "昨日导入 5 词 · 今日到期 12 词"}
```

dispatch 发送逻辑：
```python
def send_notification(settings, title: str, body: str):
    if settings.bark_url and is_safe_push_url(settings.bark_url):
        bark.push(url=settings.bark_url, title=title, body=body)
    if settings.webhook_url and is_safe_push_url(settings.webhook_url):
        requests.post(settings.webhook_url, json={"title": title, "body": body},
                      timeout=5, allow_redirects=False)
```

### SSRF 防护（P1 必须，不能等迁 Bitwarden）

`bark_url` / `webhook_url` 是用户在 /settings 自填的，dispatch 后台直接对它发请求 = 经典 server-side SSRF：用户可填 `http://127.0.0.1:8890`（同机 MemoBuddy）、`http://169.254.169.254`（云元数据）、或本机 Bitwarden 端口，让服务器代发请求打内网。

**关键**：SSRF 在 invite-only P1 就能打——一个被邀请（或被盗）账号 day-1 即可横向打同机服务，**不能等「开放注册前迁 Bitwarden」**。

校验在两处都做：**保存时**（/settings POST 拒绝非法 URL，给用户即时反馈）+ **发送前**（dispatch 二次校验，防 DNS rebinding 与存量脏数据）。

```python
import ipaddress, socket
from urllib.parse import urlparse

def is_safe_push_url(url: str) -> bool:
    try:
        p = urlparse(url)
    except Exception:
        return False
    # 1. 仅允许 https（bark 自建服务也应上 TLS）
    if p.scheme != "https":
        return False
    if not p.hostname:
        return False
    # 2. 解析所有 A/AAAA 记录，任一落在私网/环回/链路本地/保留段即拒绝
    try:
        infos = socket.getaddrinfo(p.hostname, p.port or 443, proto=socket.IPPROTO_TCP)
    except socket.gaierror:
        return False
    for *_, sockaddr in infos:
        ip = ipaddress.ip_address(sockaddr[0])
        if (ip.is_private or ip.is_loopback or ip.is_link_local
                or ip.is_reserved or ip.is_multicast or ip.is_unspecified):
            return False
    return True
```

- `allow_redirects=False`：禁止跟随重定向（防 302 跳转绕过 IP 校验）
- 超时已有（5s）
- **DNS rebinding 残余风险**：getaddrinfo 校验与实际 connect 之间 DNS 可能变化。P1 接受此残余风险（攻击窗口窄、影响有限）；P2 若提高安全等级，改为「解析→锁定 IP→直连该 IP 并带 Host 头」。
- bark 官方 App 的固定服务地址（api.day.app）天然通过校验；自建 bark 服务必须用公网 https 域名，不能填 `127.0.0.1`。

---

## 通知类型与开关

推送内容分四种独立类型，`user_settings` 各有一个布尔开关：

| 字段 | 通知类型 | 默认 | 触发时机 |
|---|---|---|---|
| `notify_review_reminder` | 单词复习提醒 | `true` | 每 15 min bark timer，有到期词时推 |
| `notify_daily_summary` | 每日学习摘要 | `true` | summary timer 每 15 min 跑，命中用户本地 08:00 窗口时推 |
| `notify_intake_done` | 导入完成通知 | `true` | `/intake/<source_id>/commit` 成功后即时推 |
| `notify_partner_activity` | 搭子动态（P2） | `false` | Session Pad P2 上线后启用，P1 字段预留但不触发 |

- 两条通道（bark_url / webhook_url）均为空时，所有通知静默，不报错
- 各开关默认值在 `flask create-user` 建账号时写入 `user_settings`

---

## 架构拆分

**不要**把 Bark 推送和 TTS 生成塞进同一个 systemd timer。拆成独立任务：

```
systemd
├── rememate-bark.timer        每 15 分钟：扫描到期词，发复习提醒
├── rememate-summary.timer     每 15 分钟：runner 内判断哪些用户本地时间正落在 08:00 窗口，推每日摘要
├── rememate-podcast.timer     每小时：生成播客音频（TTS 慢，独立运行）
└── rememate-backup.timer      每日 03:30：pg_dump 备份
```

> **为什么 summary timer 也是每 15 分钟，而不是「每日 08:00 UTC」或「每小时」**：
> - 「每日 08:00 UTC」对默认时区（`Asia/Shanghai`）= 北京 16:00，永远命中不了本地 08:00 → 早期用户全收不到。
> - 「每小时整点」对半小时偏移时区（印度 +5:30、尼泊尔 +5:45）本地 08:00 落在 UTC 的 :30/:15，整点 timer 永进不了 15 min 窗口。
> - 每 15 分钟跑 + 本地 `08:00–08:14` 窗口，覆盖所有整数/半小时偏移时区；配合 per-day 幂等键 `{user_id}:summary:{date}` 保证当天只推一次。

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
    """每 15 分钟触发，runner 内部按用户 timezone 判断是否落在本地 08:00 窗口"""
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

```python
def is_summary_time(user, now_utc: datetime) -> bool:
    tz = ZoneInfo(user.timezone or "Asia/Shanghai")   # timezone 在 User 表
    local = now_utc.replace(tzinfo=ZoneInfo("UTC")).astimezone(tz)
    return local.hour == 8 and local.minute < 15        # 本地 08:00–08:14
```

`is_summary_time` 读 `User.timezone`（默认 `Asia/Shanghai`，注意时区字段在 `User` 模型上，不在 `user_settings`），换算当前 UTC 到用户本地时间，落在 `08:00–08:14`（15 min 窗口）则触发。timer 每 15 min 跑一次，每个窗口最多命中一次；配合 per-day 幂等键 `{user_id}:summary:{date}` 防重复推。

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
    today = date.today()
    for word in due_words:
        # 幂等键用「当天日期」而非 word.due_date：逾期词每天重新提醒一次，
        # 而不是固定 due_date 导致只推一次（review E）。同一词当天多次 timer 仍只推一次。
        idempotency_key = f"{user_id}:review:{word.id}:{today}"
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
- 复习提醒：`{user_id}:review:{word_id}:{today}` — 用**当天日期**，逾期词每天重提醒一次，当天内多次 timer 仍只推一次
- 每日摘要：`{user_id}:summary:{date}` — 同用户同天唯一
- 注：`PushLog` 保留 7 天足够（键含当天日期，跨天自然换新键），清理不会影响幂等性
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
    # 音频存 /srv/rememate/audio/<user_id>/<date>.mp3（与 v0.1 §6 部署路径一致）
    # P2 迁移到对象存储（S3/R2）
    update_podcast_feed(user_id=user_id, audio_path=audio_path)
```

> **podcast_token 轮换/撤销（设计先留接口，上线后第一件优化）**：`podcast_token` 是 RSS URL 里的静态凭证，泄露即可被他人订阅，目前无 revoke 路径。P1 设计上把 token 读写收敛到一个 `services/podcast.py:rotate_token(user_id)`（生成新 token、旧 feed 失效），即使 P1 不在 UI 暴露，接口先在，避免上线后改 RSS 结构。

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

---

## P1 必测（dispatch / 推送）

| 测试 | 验证点 | 对应 review |
|---|---|---|
| `is_summary_time` 半小时偏移时区 | 印度 +5:30 / 尼泊尔 +5:45 用户本地 08:00 能命中窗口 | A4 |
| `is_summary_time` 整数偏移时区 | 北京 +8 用户本地 08:00 命中，16:00 不命中 | A4 |
| `is_safe_push_url` 拒绝私网/环回 | `http://127.0.0.1`、`http://169.254.169.254`、`http://10.x`、`http://[::1]` 全拒 | A2 |
| `is_safe_push_url` 放行公网 https | `https://api.day.app/...` 通过 | A2 |
| webhook 非 https scheme 拒绝 | `http://`、`file://`、`gopher://` 全拒 | A2 |
| 复习提醒幂等键当天重提醒 | 同词跨天换新键、当天多次 timer 只推一次 | E |
| 单用户异常不中断遍历 | 一个用户抛异常，后续用户仍处理 | 已有 try/except |
