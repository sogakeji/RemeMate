# AI Token 额度机制设计

> 记录日期：2026-06-22
> 状态：P1 实现

---

## 背景

RemeMate 用系统 DeepSeek key 为所有用户提供 AI 功能。不限额会导致系统 key 被少数高频用户烧完，影响其他用户。额度机制需要：
1. 每用户每日有基础额度上限
2. 用户可提供自己的 key 绕过系统额度
3. 点夯可以小量增加当日额度（激励机制）
4. 按 feature 记录消耗，便于运营分析

---

## 数据模型

`user_settings` 存配置，`user_quota` 存高频写入的计数（拆表避免锁竞争）：

```python
class UserSettings(db.Model):
    user_id             = db.Column(db.Integer, db.ForeignKey("users.id"), primary_key=True)
    deepseek_key_enc    = db.Column(db.Text, nullable=True)     # 用户自带 key，DATA_ENCRYPTION_KEY 加密
    bark_url            = db.Column(db.String(500), nullable=True)
    podcast_token       = db.Column(db.String(100), nullable=True)
    podcast_public_base = db.Column(db.String(500), nullable=True)
    eudic_token_enc     = db.Column(db.Text, nullable=True)     # P2 预留

class UserQuota(db.Model):
    user_id             = db.Column(db.Integer, db.ForeignKey("users.id"), primary_key=True)
    daily_base_limit    = db.Column(db.Integer, default=50_000)   # tokens/天，管理员可调
    tokens_used_today   = db.Column(db.Integer, default=0)
    bonus_tokens_today  = db.Column(db.Integer, default=0)        # 点夯获得的额外额度
    quota_reset_at      = db.Column(db.DateTime)                  # 按用户时区的下一个午夜 UTC；create_user 时即初始化，禁止留 None
    updated_at          = db.Column(db.DateTime)

class TokenUsageLog(db.Model):
    id                  = db.Column(db.Integer, primary_key=True)
    user_id             = db.Column(db.Integer, db.ForeignKey("users.id"))
    provider            = db.Column(db.String(50))                # deepseek / openai / groq
    model               = db.Column(db.String(100))
    feature             = db.Column(db.String(50))                # extract / clean / write / tutor / nsfw
    prompt_tokens       = db.Column(db.Integer)
    completion_tokens   = db.Column(db.Integer)
    used_user_key       = db.Column(db.Boolean, default=False)
    created_at          = db.Column(db.DateTime, default=datetime.utcnow)
```

---

## 额度检查流程

```
用户触发 AI 功能
    ↓
quota.check(user_id)
    ├── 用户有自带 key（deepseek_key_enc 非空）→ 走用户 key，跳过额度检查
    └── 走系统 key
            ├── 检查 quota_reset_at，若已过期 → 重置 tokens_used_today = 0
            ├── tokens_used_today + 预估消耗 > daily_base_limit + bonus_tokens_today
            │       → 返回 QuotaExceeded，前端提示"今日额度已用完，可配置自己的 key"
            └── 通过 → 调用 llm.chat()
                        → 完成后 quota.record(user_id, tokens_used, feature, ...)
```

---

## 关键实现：services/quota.py

```python
MAX_TOKENS_PER_REQUEST = 20_000   # 单请求硬上限，防 estimate 估低绕过额度（见 review C5）

def check_and_reserve(user_id: int, estimated_tokens: int) -> str:
    """
    返回 'user_key' / 'system_key' / raise QuotaExceeded / raise RequestTooLarge
    """
    settings = UserSettings.query.get(user_id)
    if settings and settings.deepseek_key_enc:
        return "user_key"

    # 单请求上限：即便额度充足，单次请求也不能超过硬上限（防超大 /extract 估低后狂烧）
    if estimated_tokens > MAX_TOKENS_PER_REQUEST:
        raise RequestTooLarge(estimated=estimated_tokens, cap=MAX_TOKENS_PER_REQUEST)

    quota = _get_or_create_quota(user_id)   # 防 None：理论上 create_user 已建，这里兜底
    _maybe_reset(quota)

    total_limit = quota.daily_base_limit + quota.bonus_tokens_today
    if quota.tokens_used_today + estimated_tokens > total_limit:
        raise QuotaExceeded(used=quota.tokens_used_today, limit=total_limit)

    return "system_key"

def _get_or_create_quota(user_id: int) -> UserQuota:
    """纵深防御：正常情况 create_user 已建行；存量/异常用户在此惰性补建"""
    quota = UserQuota.query.get(user_id)
    if quota is None:
        user = User.query.get(user_id)
        quota = UserQuota(
            user_id=user_id, daily_base_limit=50_000,
            tokens_used_today=0, bonus_tokens_today=0,
            quota_reset_at=_next_midnight_utc(user.timezone if user else "Asia/Shanghai"),
        )
        db.session.add(quota)
        db.session.commit()
    return quota

def record(user_id: int, prompt_tokens: int, completion_tokens: int,
           feature: str, provider: str, model: str, used_user_key: bool):
    if not used_user_key:
        quota = UserQuota.query.get(user_id)
        quota.tokens_used_today += prompt_tokens + completion_tokens
        quota.updated_at = datetime.utcnow()

    log = TokenUsageLog(
        user_id=user_id, provider=provider, model=model, feature=feature,
        prompt_tokens=prompt_tokens, completion_tokens=completion_tokens,
        used_user_key=used_user_key,
    )
    db.session.add(log)
    db.session.commit()

def _maybe_reset(quota: UserQuota):
    # quota_reset_at 为 None（漏初始化的存量数据）也要自愈：当成「需要重置」处理，
    # 否则 None 会让 `if quota.quota_reset_at and ...` 永远跳过 → 用户永久锁死 AI（review A3）
    if quota.quota_reset_at is None or datetime.utcnow() >= quota.quota_reset_at:
        quota.tokens_used_today = 0
        quota.bonus_tokens_today = 0
        quota.quota_reset_at = _next_midnight_utc(quota.user.timezone)
        db.session.commit()
```

---

## 时区处理

每用户按自己时区的午夜重置额度（见 arch v0.1 §B6 决策）：

```python
from zoneinfo import ZoneInfo
from datetime import datetime, timedelta

def _next_midnight_utc(timezone_str: str) -> datetime:
    tz = ZoneInfo(timezone_str or "Asia/Shanghai")
    now_local = datetime.now(tz)
    midnight_local = (now_local + timedelta(days=1)).replace(
        hour=0, minute=0, second=0, microsecond=0
    )
    return midnight_local.astimezone(ZoneInfo("UTC")).replace(tzinfo=None)
```

P1 简化：新用户默认 `timezone = "Asia/Shanghai"`，/settings 页面可修改。

---

## 点夯增加额度

句子广场是 P1 功能，点夯换 token 是其激励闭环。每次用户点夯 → 增加**点击者**当日 bonus_tokens。但「点夯加额度」天然可刷，必须三重反刷（review C7）：

```python
DAILY_UPVOTE_BONUS_CAP = 20      # 每日最多 20 次点夯计入 bonus（≈ base 的合理增量）

def add_bonus_from_upvote(user_id: int, entry_id: int, bonus: int = 500):
    # 1. 同句去重：sentence_upvotes 的 UNIQUE(entry_id, user_id) 在 DB 层挡重复夯同一句
    #    （插入冲突时本函数不应被调用；调用方先成功 insert upvote 再调本函数）

    quota = _get_or_create_quota(user_id)
    _maybe_reset(quota)

    # 2. 每日计数封顶：当日已通过点夯获得 bonus 的次数 ≥ 上限则不再加额度（点夯本身仍记录）
    upvotes_today = SentenceUpvote.query.filter(
        SentenceUpvote.user_id == user_id,
        SentenceUpvote.created_at >= _today_start_local(user_id),
    ).count()
    if upvotes_today > DAILY_UPVOTE_BONUS_CAP:
        return   # 超过当日计酬次数，不加 bonus

    # 3. 总额封顶：bonus 累计 ≤ 基础额度（最多翻倍）
    max_bonus = quota.daily_base_limit
    quota.bonus_tokens_today = min(quota.bonus_tokens_today + bonus, max_bonus)
    db.session.commit()
```

三重防线：
- **同句去重**：`UNIQUE(entry_id, user_id)`，刷子无法对同一句反复夯
- **每日次数封顶**：`DAILY_UPVOTE_BONUS_CAP = 20`，防止刷大量不同句子换额度
- **总额封顶**：bonus ≤ base_limit（最多翻倍）

具体 bonus 数值（500 tokens/夯）和每日次数上限实现时调参，不写死。异常批量点夯（短时间大量）可叠加频率限制。

---

## 用户自带 key 的加密存储

使用独立 `DATA_ENCRYPTION_KEY`，不与 Flask `SECRET_KEY` 共用：

```python
# services/crypto.py
from cryptography.fernet import Fernet

def encrypt_key(plaintext: str) -> str:
    f = Fernet(current_app.config["DATA_ENCRYPTION_KEY"])
    return f.encrypt(plaintext.encode()).decode()

def decrypt_key(ciphertext: str) -> str:
    f = Fernet(current_app.config["DATA_ENCRYPTION_KEY"])
    return f.decrypt(ciphertext.encode()).decode()
```

密文格式：Fernet token 自带版本信息，支持 key 轮换（旧密文用旧 key 解密后重新加密）。

---

## 前端展示

/settings 页面显示今日额度使用情况：

```
今日 AI 额度：23,400 / 50,000 tokens（+ 1,500 点夯奖励）
明日重置时间：00:00 (Asia/Shanghai)

[使用自己的 DeepSeek Key]  → 不受每日限制
```

额度耗尽时，AI 功能按钮 disabled，tooltip 提示「今日额度已用完，可在设置页配置自己的 key」。

---

## dispatch 里的额度

dispatch 后台生成播客/Bark 推送时调用 TTS（edge-tts，本地不消耗 AI token），不计入 DeepSeek 额度。若 dispatch 触发 AI 功能（如生成推送文案），计入系统成本，不计入用户个人额度。

---

## P1 必测（services/quota.py）

| 测试 | 验证点 | 对应 review |
|---|---|---|
| 新用户无 UserQuota 行 → check 不崩 | `_get_or_create_quota` 惰性补建，不抛 AttributeError | A3 |
| `quota_reset_at = None` → 触发重置 | `_maybe_reset` 把 None 当「需重置」，不永久锁死 | A3 |
| 跨午夜 + 时区重置 | 用户本地午夜后首次 check，`tokens_used_today` 归零 | token-quota §时区 |
| 单请求超 `MAX_TOKENS_PER_REQUEST` | 抛 `RequestTooLarge`，即便额度充足 | C5 |
| 点夯反刷：当日超 `DAILY_UPVOTE_BONUS_CAP` 不再加 bonus | bonus 不随刷量线性增长 | C7 |
| 自带 key 用户跳过额度检查 | `deepseek_key_enc` 非空直接返回 `user_key` | — |
