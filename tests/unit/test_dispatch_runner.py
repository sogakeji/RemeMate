from types import SimpleNamespace

from dispatch.runner import run_bark


def test_run_bark_processes_every_user_after_one_user_fails(capsys):
    users = [
        SimpleNamespace(id=11),
        SimpleNamespace(id=22),
        SimpleNamespace(id=33),
    ]
    calls = []

    def send_review_reminder(user, *, dry_run):
        calls.append((user.id, dry_run))
        if user.id == 22:
            raise RuntimeError("temporary Bark failure")

    stats = run_bark(
        users,
        send_review_reminder=send_review_reminder,
        dry_run=True,
    )

    assert calls == [(11, True), (22, True), (33, True)]
    assert stats.users_seen == 3
    assert stats.failed == 1
    assert "user 22" in capsys.readouterr().err
