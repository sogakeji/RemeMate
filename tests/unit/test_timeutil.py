"""timeutil 时区/午夜计算单测（不依赖 DB）。

覆盖 review 2026-06-23 M2：stats 按用户本地午夜切，而非 UTC 午夜。
"""
from datetime import datetime, timezone

from app.services.timeutil import next_midnight_utc, today_local_start_utc


def test_today_local_start_shanghai_before_utc_midnight():
    """Asia/Shanghai UTC+8：now_utc=2026-06-27 18:00 → 本地 2026-06-28 02:00。
    本地今天 00:00（=2026-06-28 00:00 本地）= UTC 2026-06-27 16:00。"""
    utc_now = datetime(2026, 6, 27, 18, 0, 0, tzinfo=timezone.utc)
    start = today_local_start_utc("Asia/Shanghai", now_utc=utc_now)
    assert start == datetime(2026, 6, 27, 16, 0, 0)


def test_today_local_start_aware_utc():
    """UTC 时区：aware 注入。本地今天 00:00 = UTC 当天 00:00。"""
    start = today_local_start_utc("UTC", now_utc=datetime(2026, 6, 27, 5, 0, 0, tzinfo=timezone.utc))
    assert start == datetime(2026, 6, 27, 0, 0, 0)


def test_today_local_start_naive_utc_treated_as_utc():
    """注入 naive 也按 UTC 解释（生产 now_utc or datetime.utcnow() 路径）。

    系统 TZ 非 UTC 时，naive utcnow 若被当本地时区会算错；timeutil 应显式按 UTC。
    """
    start = today_local_start_utc("UTC", now_utc=datetime(2026, 6, 27, 5, 0, 0))
    assert start == datetime(2026, 6, 27, 0, 0, 0)


def test_today_local_start_negative_offset_gmt_plus_9():
    """Etc/GMT+9（POSIX 固定 UTC-9，无 DST）：now_utc=2026-06-27 08:00 →
    本地 2026-06-26 23:00 → 今天本地 00:00（=2026-06-26 00:00 本地）= UTC 2026-06-26 09:00。

    用固定偏移时区避免 DST 让断言季节性翻转。"""
    utc_now = datetime(2026, 6, 27, 8, 0, 0, tzinfo=timezone.utc)
    start = today_local_start_utc("Etc/GMT+9", now_utc=utc_now)
    assert start == datetime(2026, 6, 26, 9, 0, 0)