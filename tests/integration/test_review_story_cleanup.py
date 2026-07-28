"""RS4: private story caches and content-free events obey retention."""
from sqlalchemy import text

from tests.helpers import provision_user


PW = "pw12345678"


def _seed_retention_rows(app, bypass_engine):
    user_id = provision_user(
        app,
        "review-story-cleanup@t.com",
        PW,
        tz="UTC",
    )
    with bypass_engine.begin() as connection:
        connection.execute(text("""
            INSERT INTO review_story_runs (
                user_id, local_date, target_language, feedback_language,
                contract_version, input_hash, term_snapshot, term_word_ids,
                result_json, status, attempt_count, attempt_version,
                content_expires_at, created_at, updated_at
            ) VALUES
                (
                    :uid, current_date - 9, 'fr', 'zh', 'review_story_v1',
                    :expired_ready_hash, '[]'::jsonb, '{}'::jsonb, '{}'::jsonb,
                    'ready', 1, 1, now() - interval '1 day',
                    now() - interval '8 days', now() - interval '8 days'
                ),
                (
                    :uid, current_date - 8, 'fr', 'zh', 'review_story_v1',
                    :stale_failed_hash, '[]'::jsonb, '{}'::jsonb, NULL,
                    'failed', 2, 2, NULL,
                    now() - interval '8 days', now() - interval '8 days'
                ),
                (
                    :uid, current_date, 'fr', 'zh', 'review_story_v1',
                    :fresh_hash, '[]'::jsonb, '{}'::jsonb, '{}'::jsonb,
                    'ready', 1, 1, now() + interval '1 day',
                    now() - interval '30 days',
                    now() - interval '30 days'
                )
        """), {
            "uid": user_id,
            "expired_ready_hash": "a" * 64,
            "stale_failed_hash": "b" * 64,
            "fresh_hash": "c" * 64,
        })
        connection.execute(text("""
            INSERT INTO learning_funnel_events (
                user_id, event_type, occurred_at, dedupe_key
            ) VALUES
                (
                    :uid, 'story_generation_ready',
                    now() - interval '181 days', :old_key
                ),
                (
                    :uid, 'story_output_saved',
                    now() - interval '179 days', :fresh_key
                )
        """), {
            "uid": user_id,
            "old_key": "d" * 64,
            "fresh_key": "e" * 64,
        })
    return user_id


def test_cleanup_review_stories_previews_then_applies_retention(
    app,
    runner,
    bypass_engine,
):
    user_id = _seed_retention_rows(app, bypass_engine)

    preview = runner.invoke(args=["cleanup-review-stories"])

    assert preview.exit_code == 0
    assert (
        "review story cleanup: mode=dry-run runs=2 events=1"
        in preview.output
    )
    with bypass_engine.connect() as connection:
        assert connection.execute(text(
            "SELECT count(*) FROM review_story_runs WHERE user_id=:uid"
        ), {"uid": user_id}).scalar_one() == 3
        assert connection.execute(text(
            "SELECT count(*) FROM learning_funnel_events WHERE user_id=:uid"
        ), {"uid": user_id}).scalar_one() == 2

    applied = runner.invoke(args=["cleanup-review-stories", "--apply"])

    assert applied.exit_code == 0
    assert "review story cleanup: mode=apply runs=2 events=1" in applied.output
    with bypass_engine.connect() as connection:
        remaining_runs = connection.execute(text(
            "SELECT input_hash FROM review_story_runs WHERE user_id=:uid"
        ), {"uid": user_id}).scalars().all()
        remaining_events = connection.execute(text(
            "SELECT dedupe_key FROM learning_funnel_events WHERE user_id=:uid"
        ), {"uid": user_id}).scalars().all()
    assert remaining_runs == ["c" * 64]
    assert remaining_events == ["e" * 64]


def test_cleanup_review_stories_requires_dispatch_connection(app, runner):
    app.config["DISPATCH_DATABASE_URL"] = None

    result = runner.invoke(args=["cleanup-review-stories"])

    assert result.exit_code != 0
    assert "DISPATCH_DATABASE_URL missing" in result.output
