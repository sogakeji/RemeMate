"""Privacy-safe closed-beta observation aggregates."""
from datetime import datetime, timedelta

from sqlalchemy import text

from tests.helpers import provision_user

PW = "pw12345678"
NOW = datetime(2026, 9, 6, 12, 0, 0)


def _output(connection, user_id, occurred_at, word_id=None):
    connection.execute(text("""
        INSERT INTO output_entries(
            user_id, word_id, original, corrected, word_text, language_code,
            is_public, upvote_count, is_nsfw, created_at
        ) VALUES (
            :user_id, :word_id, 'private sentinel', 'private sentinel',
            'private sentinel', 'fr', false, 0, false, :occurred_at
        )
    """), {
        "user_id": user_id,
        "word_id": word_id,
        "occurred_at": occurred_at,
    })


def test_report_compares_distinct_active_users_days_and_repeat_activity(
        app, bypass_engine):
    from app.services.closed_beta_observation import build_report

    first = provision_user(app, "observer-one@example.com", PW)
    second = provision_user(app, "observer-two@example.com", PW)
    with bypass_engine.begin() as connection:
        _output(connection, first, NOW - timedelta(days=1))
        _output(connection, first, NOW - timedelta(days=2))
        _output(connection, second, NOW - timedelta(days=3))
        _output(connection, first, NOW - timedelta(days=8))

    report = build_report(
        app.config["DISPATCH_DATABASE_URL"],
        now=NOW,
    )

    assert report.current.start == NOW - timedelta(days=7)
    assert report.current.end == NOW
    assert report.current.active_users == 2
    assert report.current.repeat_active_users == 1
    assert report.current.active_user_days == 3
    assert report.previous.start == NOW - timedelta(days=14)
    assert report.previous.end == NOW - timedelta(days=7)
    assert report.previous.active_users == 1
    assert report.previous.repeat_active_users == 0
    assert report.previous.active_user_days == 1


def test_active_users_include_existing_learning_facts_without_page_views(
        app, bypass_engine):
    from app.services.closed_beta_observation import build_report

    reviewers = [
        provision_user(app, f"active-{index}@example.com", PW)
        for index in range(4)
    ]
    occurred_at = NOW - timedelta(hours=3)
    with bypass_engine.begin() as connection:
        list_id = connection.execute(text("""
            INSERT INTO word_lists(user_id, name, language_code, created_at)
            VALUES (:user_id, 'List', 'fr', :occurred_at) RETURNING id
        """), {"user_id": reviewers[0], "occurred_at": occurred_at}).scalar_one()
        word_id = connection.execute(text("""
            INSERT INTO words(list_id, word, marked, due_date, interval, ease, reps, lapses)
            VALUES (:list_id, 'mot', false, :occurred_at, 1, 2.5, 0, 0) RETURNING id
        """), {"list_id": list_id, "occurred_at": occurred_at}).scalar_one()
        connection.execute(text("""
            INSERT INTO review_logs(word_id, user_id, ts, grade, source)
            VALUES (:word_id, :user_id, :occurred_at, 5, 'review')
        """), {"word_id": word_id, "user_id": reviewers[0], "occurred_at": occurred_at})

        intake_list = connection.execute(text("""
            INSERT INTO word_lists(user_id, name, language_code, created_at)
            VALUES (:user_id, 'List', 'fr', :occurred_at) RETURNING id
        """), {"user_id": reviewers[1], "occurred_at": occurred_at}).scalar_one()
        connection.execute(text("""
            INSERT INTO intake_sources(user_id, source_type, language_code, word_list_id,
                                       status, created_at)
            VALUES (:user_id, 'quick_add', 'fr', :list_id, 'done', :occurred_at)
        """), {"user_id": reviewers[1], "list_id": intake_list, "occurred_at": occurred_at})
        connection.execute(text("""
            INSERT INTO learning_funnel_events(user_id, event_type, occurred_at, dedupe_key)
            VALUES (:user_id, 'story_generation_started', :occurred_at, :dedupe_key)
        """), {
            "user_id": reviewers[2],
            "occurred_at": occurred_at,
            "dedupe_key": "a" * 64,
        })
        connection.execute(text("""
            INSERT INTO practice_sessions(
                user_id, language_code, status, current_position,
                started_at, completed_at, created_at, updated_at
            ) VALUES (
                :user_id, 'fr', 'completed', 1,
                :occurred_at, :occurred_at, :occurred_at, :occurred_at
            )
        """), {"user_id": reviewers[3], "occurred_at": occurred_at})

    report = build_report(app.config["DISPATCH_DATABASE_URL"], now=NOW)

    assert report.current.active_users == 4
    assert report.current.repeat_active_users == 0
    assert report.current.active_user_days == 4


def test_report_counts_learning_story_and_practice_funnels_with_safe_rates(
        app, bypass_engine):
    from app.services.closed_beta_observation import build_report

    first = provision_user(app, "funnel-one@example.com", PW)
    second = provision_user(app, "funnel-two@example.com", PW)
    with bypass_engine.begin() as connection:
        word_ids = []
        for user_id, word in ((first, "un"), (second, "deux")):
            list_id = connection.execute(text("""
                INSERT INTO word_lists(user_id, name, language_code, created_at)
                VALUES (:user_id, 'List', 'fr', :created_at) RETURNING id
            """), {"user_id": user_id, "created_at": NOW - timedelta(days=2)}).scalar_one()
            word_ids.append(connection.execute(text("""
                INSERT INTO words(list_id, word, marked, due_date, interval, ease, reps, lapses)
                VALUES (:list_id, :word, false, :created_at, 1, 2.5, 0, 0)
                RETURNING id
            """), {
                "list_id": list_id,
                "word": word,
                "created_at": NOW - timedelta(days=2),
            }).scalar_one())
        connection.execute(text("""
            INSERT INTO review_logs(word_id, user_id, ts, grade, source) VALUES
            (:first_word, :first, :first_review, 3, 'review'),
            (:second_word, :second, :second_review, 5, 'bark'),
            (:second_word, :second, :write_review, 5, 'write')
        """), {
            "first_word": word_ids[0],
            "first": first,
            "first_review": NOW - timedelta(days=2),
            "second_word": word_ids[1],
            "second": second,
            "second_review": NOW - timedelta(days=3),
            "write_review": NOW - timedelta(days=1),
        })
        _output(connection, first, NOW - timedelta(days=2) + timedelta(hours=2), word_ids[0])
        _output(connection, second, NOW - timedelta(days=3, hours=1), word_ids[1])
        _output(connection, second, NOW - timedelta(days=3) + timedelta(hours=25), word_ids[1])
        for event_type, suffix in (
            ("story_eligible_normal", "a"),
            ("story_eligible_strong", "b"),
            ("story_generation_started", "c"),
            ("story_generation_ready", "d"),
            ("story_writing_handoff", "e"),
            ("story_output_saved", "f"),
        ):
            connection.execute(text("""
                INSERT INTO learning_funnel_events(
                    user_id, event_type, occurred_at, dedupe_key
                ) VALUES (:user_id, :event_type, :occurred_at, :dedupe_key)
            """), {
                "user_id": first,
                "event_type": event_type,
                "occurred_at": NOW - timedelta(days=1),
                "dedupe_key": suffix * 64,
            })
        for user_id, days_ago in ((first, 1), (first, 2), (second, 1)):
            occurred_at = NOW - timedelta(days=days_ago)
            connection.execute(text("""
                INSERT INTO practice_sessions(
                    user_id, language_code, status, current_position,
                    started_at, completed_at, created_at, updated_at
                ) VALUES (
                    :user_id, 'fr', 'completed', 1,
                    :occurred_at, :occurred_at, :occurred_at, :occurred_at
                )
            """), {"user_id": user_id, "occurred_at": occurred_at})

    current = build_report(
        app.config["DISPATCH_DATABASE_URL"], now=NOW,
    ).current

    assert current.review_users == 2
    assert current.output_users == 2
    assert current.review_to_output.numerator == 1
    assert current.review_to_output.denominator == 2
    assert current.review_to_output.percent == 50.0
    assert current.story_eligible_users == 1
    assert current.story_started_users == 1
    assert current.story_ready_users == 1
    assert current.story_handoff_users == 1
    assert current.story_saved_users == 1
    assert current.practice_completed_users == 2
    assert current.practice_repeat.numerator == 1
    assert current.practice_repeat.denominator == 2
    assert current.practice_repeat.percent == 50.0

    previous = build_report(
        app.config["DISPATCH_DATABASE_URL"], now=NOW,
    ).previous
    assert previous.review_to_output.percent is None
    assert previous.practice_repeat.percent is None


def test_report_counts_sessionpad_participation_without_content(app, bypass_engine):
    from app.services.closed_beta_observation import build_report

    sender = provision_user(app, "sender-private@example.com", PW)
    recipient = provision_user(app, "recipient-private@example.com", PW)
    occurred_at = NOW - timedelta(hours=1)
    with bypass_engine.begin() as connection:
        partner_id = connection.execute(text("""
            INSERT INTO language_partners(
                user_id, linked_user_id, display_name, private_note, created_at, updated_at
            ) VALUES (
                :sender, :recipient, 'private sentinel', 'private sentinel',
                :occurred_at, :occurred_at
            ) RETURNING id
        """), {
            "sender": sender,
            "recipient": recipient,
            "occurred_at": occurred_at,
        }).scalar_one()
        recap_id = connection.execute(text("""
            INSERT INTO partner_recaps(
                user_id, partner_id, session_date, title, created_at, updated_at
            ) VALUES (
                :sender, :partner_id, CAST(:occurred_at AS date),
                'private sentinel', :occurred_at, :occurred_at
            ) RETURNING id
        """), {
            "sender": sender,
            "partner_id": partner_id,
            "occurred_at": occurred_at,
        }).scalar_one()
        packet_id = connection.execute(text("""
            INSERT INTO partner_packets(
                sender_user_id, recipient_user_id, partner_id, recap_id,
                sender_display_name, recipient_display_name, recap_title,
                session_date, language_code, content_fingerprint, item_count, created_at
            ) VALUES (
                :sender, :recipient, :partner_id, :recap_id,
                'private sentinel', 'private sentinel', 'private sentinel',
                CAST(:occurred_at AS date), 'fr', :fingerprint, 1, :occurred_at
            ) RETURNING id
        """), {
            "sender": sender,
            "recipient": recipient,
            "partner_id": partner_id,
            "recap_id": recap_id,
            "fingerprint": "1" * 64,
            "occurred_at": occurred_at,
        }).scalar_one()
        item_id = connection.execute(text("""
            INSERT INTO partner_packet_items(packet_id, kind, content, position)
            VALUES (:packet_id, 'expression', 'private sentinel', 0) RETURNING id
        """), {"packet_id": packet_id}).scalar_one()
        connection.execute(text("""
            INSERT INTO partner_packet_thanks(packet_id, recipient_user_id, thanked_at)
            VALUES (:packet_id, :recipient, :occurred_at)
        """), {
            "packet_id": packet_id,
            "recipient": recipient,
            "occurred_at": occurred_at,
        })
        list_id = connection.execute(text("""
            INSERT INTO word_lists(user_id, name, language_code, created_at)
            VALUES (:recipient, 'List', 'fr', :occurred_at) RETURNING id
        """), {"recipient": recipient, "occurred_at": occurred_at}).scalar_one()
        source_id = connection.execute(text("""
            INSERT INTO intake_sources(
                user_id, source_type, language_code, word_list_id, status, created_at
            ) VALUES (
                :recipient, 'quick_add', 'fr', :list_id, 'done', :occurred_at
            ) RETURNING id
        """), {
            "recipient": recipient,
            "list_id": list_id,
            "occurred_at": occurred_at,
        }).scalar_one()
        candidate_id = connection.execute(text("""
            INSERT INTO word_candidates(
                source_id, user_id, word, meaning, status, created_at
            ) VALUES (
                :source_id, :recipient, 'private sentinel', 'private sentinel',
                'pending', :occurred_at
            ) RETURNING id
        """), {
            "source_id": source_id,
            "recipient": recipient,
            "occurred_at": occurred_at,
        }).scalar_one()
        connection.execute(text("""
            INSERT INTO partner_packet_item_adoptions(
                packet_item_id, packet_id, recipient_user_id, candidate_id, created_at
            ) VALUES (
                :item_id, :packet_id, :recipient, :candidate_id, :occurred_at
            )
        """), {
            "item_id": item_id,
            "packet_id": packet_id,
            "recipient": recipient,
            "candidate_id": candidate_id,
            "occurred_at": occurred_at,
        })

    current = build_report(
        app.config["DISPATCH_DATABASE_URL"], now=NOW,
    ).current

    assert current.recap_users == 1
    assert current.packet_sent_users == 1
    assert current.thank_users == 1
    assert current.adoption_users == 1


def test_report_windows_are_half_open(app, bypass_engine):
    from app.services.closed_beta_observation import build_report

    at_current_start = provision_user(app, "boundary-current@example.com", PW)
    at_previous_start = provision_user(app, "boundary-previous@example.com", PW)
    at_end = provision_user(app, "boundary-end@example.com", PW)
    with bypass_engine.begin() as connection:
        _output(connection, at_current_start, NOW - timedelta(days=7))
        _output(connection, at_previous_start, NOW - timedelta(days=14))
        _output(connection, at_end, NOW)

    report = build_report(app.config["DISPATCH_DATABASE_URL"], now=NOW)

    assert report.current.active_users == 1
    assert report.previous.active_users == 1
