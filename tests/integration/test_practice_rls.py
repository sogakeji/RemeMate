"""PostgreSQL RLS isolation for contextual dictation practice records."""

import pytest
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError

from tests.helpers import make_user, make_word, set_uid


def test_practice_records_are_isolated_for_every_app_role_operation(
    app_engine, bypass_engine,
):
    owner = make_user(bypass_engine, "practice-rls-owner@t.com")
    attacker = make_user(bypass_engine, "practice-rls-attacker@t.com")
    _, word_id = make_word(bypass_engine, owner, word="secret")
    with bypass_engine.begin() as connection:
        definition_id = connection.execute(text(
            "INSERT INTO definitions(word_id, meaning, example) "
            "VALUES (:word_id, 'secret meaning', 'Un secret existe.') RETURNING id"
        ), {"word_id": word_id}).scalar_one()
        session_id = connection.execute(text(
            "INSERT INTO practice_sessions("
            "user_id, language_code, status, current_position, started_at, created_at, updated_at"
            ") VALUES (:user_id, 'fr', 'active', 0, now(), now(), now()) RETURNING id"
        ), {"user_id": owner}).scalar_one()
        item_id = connection.execute(text(
            "INSERT INTO practice_items("
            "session_id, user_id, word_id, definition_id, position, sentence, target, "
            "meaning, replay_count, created_at, updated_at"
            ") VALUES (:session_id, :user_id, :word_id, :definition_id, 0, "
            "'Un secret existe.', 'secret', 'secret meaning', 0, now(), now()) RETURNING id"
        ), {
            "session_id": session_id,
            "user_id": owner,
            "word_id": word_id,
            "definition_id": definition_id,
        }).scalar_one()

    with app_engine.begin() as connection:
        set_uid(connection, attacker)
        assert connection.execute(text(
            "SELECT count(*) FROM practice_sessions WHERE id=:session_id"
        ), {"session_id": session_id}).scalar_one() == 0
        assert connection.execute(text(
            "SELECT count(*) FROM practice_items WHERE id=:item_id"
        ), {"item_id": item_id}).scalar_one() == 0
        assert connection.execute(text(
            "UPDATE practice_sessions SET status='completed' WHERE id=:session_id"
        ), {"session_id": session_id}).rowcount == 0
        assert connection.execute(text(
            "DELETE FROM practice_items WHERE id=:item_id"
        ), {"item_id": item_id}).rowcount == 0

    with pytest.raises(DBAPIError):
        with app_engine.begin() as connection:
            set_uid(connection, attacker)
            connection.execute(text(
                "INSERT INTO practice_sessions("
                "user_id, language_code, status, current_position, started_at, created_at, updated_at"
                ") VALUES (:user_id, 'fr', 'active', 0, now(), now(), now())"
            ), {"user_id": owner})

    with app_engine.connect() as connection:
        set_uid(connection, owner)
        assert connection.execute(text(
            "SELECT count(*) FROM practice_sessions WHERE id=:session_id"
        ), {"session_id": session_id}).scalar_one() == 1
        assert connection.execute(text(
            "SELECT count(*) FROM practice_items WHERE id=:item_id"
        ), {"item_id": item_id}).scalar_one() == 1
