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
    quota_reset_at      = db.Column(db.DateTime)                  # 按用户时区的下一个午夜 UTC 时间
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
def check_and_reserve(user_id: int, estimated_tokens: int) -> str:
    """
    返回 'user_key' / 'system_key' / raise QuotaExceeded
    """
    settings = UserSettings.query.get(user_id)
    if settings and settings.deepseek_key_enc:
        return "user_key"

    quota = UserQuota.query.get(user_id)
    _maybe_reset(quota)

    total_limit = quota.daily_base_limit + quota.bonus_tokens_today
    if quota.tokens_used_today + estimated_tokens > total_limit:
        raise QuotaExceeded(used=quota.tokens_used_today, limit=total_limit)

    return "system_key"

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
    if quota.quota_reset_at and datetime.utcnow() >= quota.quota_reset_at:
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

每次用户点夯 → 增加点击者当日 bonus_tokens：

```python
def add_bonus_from_upvote(user_id: int, bonus: int = 500):
    quota = UserQuota.query.get(user_id)
    _maybe_reset(quota)
    max_bonus = quota.daily_base_limit          # 上限：bonus ≤ 基础额度（最多翻倍）
    quota.bonus_tokens_today = min(
        quota.bonus_tokens_today + bonus, max_bonus
    )
    db.session.commit()
```

具体 bonus 数值（500 tokens/夯）实现时调参，不写死配置。

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
