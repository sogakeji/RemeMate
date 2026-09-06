"""Admin-only, aggregate-only closed-beta observation page."""
import re
from datetime import datetime, timedelta

from sqlalchemy import text

from tests.helpers import login, provision_user

PW = "pw12345678"
NOW = datetime(2026, 9, 6, 12, 0, 0)


def test_observation_page_requires_admin(app, client):
    assert client.get("/admin/observation").status_code == 302
    provision_user(app, "plain-observer@example.com", PW)
    login(client, "plain-observer@example.com", PW)
    assert client.get("/admin/observation").status_code == 403


def test_observation_page_shows_only_aggregate_report(
        app, client, bypass_engine, monkeypatch):
    admin = provision_user(app, "admin-observer@example.com", PW, admin=True)
    participant = provision_user(
        app, "identity-must-not-appear@example.com", PW,
        name="Identity Must Not Appear",
    )
    with bypass_engine.begin() as connection:
        connection.execute(text("""
            INSERT INTO output_entries(
                user_id, original, corrected, word_text, language_code,
                is_public, upvote_count, is_nsfw, created_at
            ) VALUES (
                :user_id, 'CONTENT MUST NOT APPEAR', 'CONTENT MUST NOT APPEAR',
                'CONTENT MUST NOT APPEAR', 'fr', false, 0, false, :created_at
            )
        """), {
            "user_id": participant,
            "created_at": NOW - timedelta(days=1),
        })
    monkeypatch.setattr(
        "app.blueprints.admin.routes.utc_now", lambda: NOW,
        raising=False,
    )
    login(client, "admin-observer@example.com", PW)

    response = client.get("/admin/observation")
    page = response.get_data(as_text=True)

    assert response.status_code == 200
    assert "学习闭环观察" in page
    assert "最近 7 天" in page
    assert "前 7 天" in page
    assert re.search(
        r"学习活跃用户</th>\s*<td>1</td>\s*<td>0</td>", page,
    )
    assert "0 / 0\n (—)" in page
    assert "identity-must-not-appear@example.com" not in page
    assert "Identity Must Not Appear" not in page
    assert "CONTENT MUST NOT APPEAR" not in page

    admin_page = client.get("/admin/").get_data(as_text=True)
    assert 'href="/admin/observation"' in admin_page


def test_observation_page_degrades_without_dispatch_details(
        app, client, monkeypatch):
    provision_user(app, "admin-degraded@example.com", PW, admin=True)
    login(client, "admin-degraded@example.com", PW)

    def unavailable(*args, **kwargs):
        raise RuntimeError("postgresql://secret:password@host/private-db")

    monkeypatch.setattr(
        "app.blueprints.admin.routes.closed_beta_observation.build_report",
        unavailable,
        raising=False,
    )
    response = client.get("/admin/observation")
    page = response.get_data(as_text=True)

    assert response.status_code == 200
    assert "统计暂不可用" in page
    assert "secret" not in page
    assert "password" not in page
    assert "private-db" not in page
