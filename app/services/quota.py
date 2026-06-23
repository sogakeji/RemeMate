"""造句额度门禁（按提交句数计，见用户决策 2026-06-23）。

- 系统 key：每日 3 句；自带 key：每日 20 句（自带 key 不烧系统额度）。
- 按「提交批改次数」计，写错重试也计入（口径最简、最省 token）。
- 每日按用户时区午夜重置（复用 quota_reset_at）。
- token 计数（tokens_used_today）保留作观测，不作为 /write 的限制。
"""
from datetime import datetime

from app.extensions import db
from app.models.user import User, UserSettings, UserQuota, TokenUsageLog
from app.services.timeutil import next_midnight_utc

SYSTEM_DAILY_SENTENCES = 3
OWNKEY_DAILY_SENTENCES = 20
DEFAULT_DAILY_LIMIT = 50_000


class SentenceQuotaExceeded(Exception):
    def __init__(self, used, limit):
        self.used = used
        self.limit = limit
        super().__init__(f"今日造句已达上限 {used}/{limit}")


def _get_or_create_quota(user_id) -> UserQuota:
    quota = db.session.get(UserQuota, user_id)
    if quota is None:
        user = db.session.get(User, user_id)
        quota = UserQuota(
            user_id=user_id, daily_base_limit=DEFAULT_DAILY_LIMIT,
            quota_reset_at=next_midnight_utc(user.timezone if user else "Asia/Shanghai"),
        )
        db.session.add(quota)
        db.session.commit()
    return quota


def _maybe_reset(quota: UserQuota):
    # None（漏初始化）也当「需重置」，否则永不重置（回归 review A3）
    if quota.quota_reset_at is None or datetime.utcnow() >= quota.quota_reset_at:
        quota.tokens_used_today = 0
        quota.bonus_tokens_today = 0
        quota.corrections_today = 0
        user = db.session.get(User, quota.user_id)
        quota.quota_reset_at = next_midnight_utc(user.timezone if user else "Asia/Shanghai")
        db.session.commit()


def _has_own_key(user_id) -> bool:
    settings = db.session.get(UserSettings, user_id)
    return bool(settings and settings.deepseek_key_enc)


def daily_limit(user_id) -> int:
    return OWNKEY_DAILY_SENTENCES if _has_own_key(user_id) else SYSTEM_DAILY_SENTENCES


def write_quota_status(user_id) -> dict:
    """给 UI 展示：已用/上限/是否自带 key。"""
    quota = _get_or_create_quota(user_id)
    _maybe_reset(quota)
    own = _has_own_key(user_id)
    return {
        "used": quota.corrections_today,
        "limit": OWNKEY_DAILY_SENTENCES if own else SYSTEM_DAILY_SENTENCES,
        "own_key": own,
    }


def check_write_quota(user_id) -> str:
    """检查今日造句额度。返回 'user_key'/'system_key'，超限 raise SentenceQuotaExceeded。

    只检查不递增；成功批改后由 record_correction 递增（避免失败也扣额度）。
    """
    quota = _get_or_create_quota(user_id)
    _maybe_reset(quota)
    own = _has_own_key(user_id)
    limit = OWNKEY_DAILY_SENTENCES if own else SYSTEM_DAILY_SENTENCES
    if quota.corrections_today >= limit:
        raise SentenceQuotaExceeded(used=quota.corrections_today, limit=limit)
    return "user_key" if own else "system_key"


def record_correction(user_id, *, prompt_tokens, completion_tokens,
                      provider, model, used_user_key, feature="correction"):
    """批改成功后调用：句数 +1，token 记账，写 TokenUsageLog。"""
    quota = _get_or_create_quota(user_id)
    quota.corrections_today += 1
    if not used_user_key:
        quota.tokens_used_today += (prompt_tokens or 0) + (completion_tokens or 0)
    quota.updated_at = datetime.utcnow()
    db.session.add(TokenUsageLog(
        user_id=user_id, provider=provider, model=model, feature=feature,
        prompt_tokens=prompt_tokens, completion_tokens=completion_tokens,
        used_user_key=used_user_key,
    ))
    db.session.commit()
