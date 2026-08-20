from pathlib import Path


def test_bark_systemd_units_define_quarter_hour_dispatch():
    root = Path(__file__).parents[2]
    timer = (root / "deploy/systemd/rememate-bark.timer").read_text(encoding="utf-8")
    service = (root / "deploy/systemd/rememate-bark.service").read_text(encoding="utf-8")

    assert "OnCalendar=*-*-* *:00,15,30,45:00" in timer
    assert "Persistent=true" in timer
    assert "Type=oneshot" in service
    assert "User=ubuntu" in service
    assert "WorkingDirectory=/srv/rememate" in service
    assert "EnvironmentFile=/srv/rememate/.env" in service
    assert "RuntimeDirectory=rememate" in service
    assert "After=network-online.target postgresql.service" in service
    assert "/run/rememate/bark.lock" in service
    assert "ExecStart=/srv/rememate/.venv/bin/python -u -m dispatch.runner bark --flock-lock /run/rememate/bark.lock" in service
    assert "flock -n" not in service
