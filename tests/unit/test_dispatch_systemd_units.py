from pathlib import Path


def test_bark_systemd_units_define_quarter_hour_dispatch():
    root = Path(__file__).parents[2]
    timer = (root / "deploy/systemd/rememate-bark.timer").read_text(encoding="utf-8")
    service = (root / "deploy/systemd/rememate-bark.service").read_text(encoding="utf-8")

    assert "OnCalendar=*-*-* *:00,15,30,45:00" in timer
    assert "Persistent=true" in timer
    assert "Type=oneshot" in service
    assert "/usr/bin/flock -n /tmp/rememate-bark.lock" in service
    assert "/srv/rememate/.venv/bin/python -m dispatch.runner bark" in service
