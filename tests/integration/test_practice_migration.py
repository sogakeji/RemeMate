"""Schema and migration verification for contextual dictation practice."""

from sqlalchemy import inspect, text

from app.models.practice import PracticeItem, PracticeSession


def test_practice_schema_matches_metadata_and_rls_contract(bypass_engine):
    inspector = inspect(bypass_engine)
    with bypass_engine.connect() as connection:
        assert connection.execute(text(
            "SELECT version_num FROM alembic_version"
        )).scalar_one() == "e9f0a1b2c3d4"

        flags = connection.execute(text(
            "SELECT relrowsecurity, relforcerowsecurity "
            "FROM pg_class WHERE relname IN ('practice_sessions', 'practice_items') "
            "ORDER BY relname"
        )).all()
        assert flags == [(True, True), (True, True)]

        policies = {
            row[0] for row in connection.execute(text(
                "SELECT policyname FROM pg_policies "
                "WHERE tablename IN ('practice_sessions', 'practice_items')"
            )).all()
        }
    assert {
        "practice_sessions_select",
        "practice_sessions_insert",
        "practice_sessions_update",
        "practice_sessions_delete",
        "practice_items_select",
        "practice_items_insert",
        "practice_items_update",
        "practice_items_delete",
    } <= policies

    for model in (PracticeSession, PracticeItem):
        columns = {column["name"] for column in inspector.get_columns(model.__tablename__)}
        assert columns == set(model.__table__.columns.keys())

    assert {index["name"] for index in inspector.get_indexes("practice_sessions")} >= {
        "ix_practice_sessions_user_created",
    }
    assert {index["name"] for index in inspector.get_indexes("practice_items")} >= {
        "ix_practice_items_session_position",
    }
    item_fks = inspector.get_foreign_keys("practice_items")
    ondelete_by_table = {
        fk["referred_table"]: fk["options"].get("ondelete")
        for fk in item_fks
    }
    assert ondelete_by_table["practice_sessions"] == "CASCADE"
    assert ondelete_by_table["users"] == "CASCADE"
    assert ondelete_by_table["words"] == "CASCADE"
    assert ondelete_by_table["definitions"] == "CASCADE"
