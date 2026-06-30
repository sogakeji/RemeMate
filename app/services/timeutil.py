"""时区/时间工具。"""
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo


def utc_now() -> datetime:
    """Return the current UTC time as a naive datetime for DB DateTime columns."""
    return datetime.now(timezone.utc).replace(tzinfo=None)


def next_midnight_utc(tz_name: str | None) -> datetime:
    """返回用户时区「下一个午夜」对应的 UTC naive datetime（用于额度重置点）。"""
    tz = ZoneInfo(tz_name or "Asia/Shanghai")
    now_local = datetime.now(tz)
    midnight_local = (now_local + timedelta(days=1)).replace(
        hour=0, minute=0, second=0, microsecond=0
    )
    return midnight_local.astimezone(ZoneInfo("UTC")).replace(tzinfo=None)


def today_local_start_utc(tz_name: str | None, *, now_utc: datetime | None = None) -> datetime:
    """返回用户时区「今天本地 00:00」对应的 UTC naive datetime。

    用于 stats 的「今日已复习」按用户本地午夜切，而非 UTC 午夜
    （review 2026-06-23 M2）：Asia/Shanghai 用户本地 00:00–08:00（UTC 16:00–24:00）
    的复习，若按 UTC 午夜切会被错算到「昨天」。

    ``now_utc`` 仅用于测试注入固定时刻；生产留空取当前 UTC。
    """
    tz = ZoneInfo(tz_name or "Asia/Shanghai")
    now_utc = now_utc or utc_now()
    # 注入的 naive datetime 当 UTC；aware 直接用。
    now_utc = now_utc.replace(tzinfo=timezone.utc) if now_utc.tzinfo is None else now_utc
    now_local = now_utc.astimezone(tz)
    midnight_local = now_local.replace(hour=0, minute=0, second=0, microsecond=0)
    return midnight_local.astimezone(ZoneInfo("UTC")).replace(tzinfo=None)
