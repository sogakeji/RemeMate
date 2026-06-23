"""时区/时间工具。"""
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo


def next_midnight_utc(tz_name: str | None) -> datetime:
    """返回用户时区「下一个午夜」对应的 UTC naive datetime（用于额度重置点）。"""
    tz = ZoneInfo(tz_name or "Asia/Shanghai")
    now_local = datetime.now(tz)
    midnight_local = (now_local + timedelta(days=1)).replace(
        hour=0, minute=0, second=0, microsecond=0
    )
    return midnight_local.astimezone(ZoneInfo("UTC")).replace(tzinfo=None)
