"""OR1-B：匿名认证控制面模型与 PostgreSQL 约束。"""
import pytest
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError, IntegrityError

from app.models.account_access import AuthChallenge, AuthMailEvent
from tests.helpers import make_user


def _column_names(model):
    return {column.name for column in model.__table__.columns}


def _index_columns(conn, table_name):
    rows = conn.execute(text("""
        SELECT index_class.relname AS index_name,
               array_agg(attribute.attname ORDER BY key.ordinality) AS columns
        FROM pg_class AS table_class
        JOIN pg_namespace AS namespace
          ON namespace.oid = table_class.relnamespace
        JOIN pg_index AS index_info
          ON index_info.indrelid = table_class.oid
        JOIN pg_class AS index_class
          ON index_class.oid = index_info.indexrelid
        CROSS JOIN LATERAL unnest(index_info.indkey)
          WITH ORDINALITY AS key(attnum, ordinality)
        JOIN pg_attribute AS attribute
          ON attribute.attrelid = table_class.oid
         AND attribute.attnum = key.attnum
        WHERE namespace.nspname = 'public'
          AND table_class.relname = :table_name
        GROUP BY index_class.relname
    """), {"table_name": table_name}).mappings().all()
    return {row["index_name"]: tuple(row["columns"]) for row in rows}


def _constraint_definitions(conn, table_name):
    return [row[0] for row in conn.execute(text("""
        SELECT pg_get_constraintdef(oid)
        FROM pg_constraint
        WHERE conrelid = to_regclass(:table_name)
          AND contype = 'c'
    """), {"table_name": f"public.{table_name}"}).all()]


def _insert_challenge(engine, *, digest, purpose, email, user_id):
    with engine.begin() as conn:
        return conn.execute(text("""
            INSERT INTO auth_challenges(
                token_digest, purpose, email, user_id,
                expires_at, consumed_at, created_at
            ) VALUES (
                :digest, :purpose, :email, :user_id,
                now() + interval '1 hour', NULL, now()
            ) RETURNING id
        """), {
            "digest": digest,
            "purpose": purpose,
            "email": email,
            "user_id": user_id,
        }).scalar_one()


def _insert_mail_event(engine, *, challenge_id=None, purpose="registration",
                       status="reserved", email="mail-event@t.com"):
    with engine.begin() as conn:
        return conn.execute(text("""
            INSERT INTO auth_mail_events(
                challenge_id, purpose, email, client_key_digest,
                delivery_status, provider_message_id, created_at
            ) VALUES (
                :challenge_id, :purpose, :email, :client_key_digest,
                :delivery_status, NULL, now()
            ) RETURNING id
        """), {
            "challenge_id": challenge_id,
            "purpose": purpose,
            "email": email,
            "client_key_digest": "c" * 64,
            "delivery_status": status,
        }).scalar_one()


@pytest.fixture
def auth_user(bypass_engine):
    email = "auth-control-fixture@t.com"
    user_id = make_user(bypass_engine, email)
    yield user_id, email
    with bypass_engine.begin() as conn:
        conn.execute(text("""
            DELETE FROM auth_mail_events
            WHERE email = :email
               OR challenge_id IN (
                    SELECT id FROM auth_challenges WHERE user_id = :user_id
               )
        """), {"email": email, "user_id": user_id})
        conn.execute(text(
            "DELETE FROM auth_challenges WHERE email=:email OR user_id=:user_id"
        ), {"email": email, "user_id": user_id})
        conn.execute(text("DELETE FROM users WHERE id=:user_id"),
                     {"user_id": user_id})


def test_auth_control_models_declare_expected_fields_and_fk_actions():
    assert _column_names(AuthChallenge) == {
        "id", "token_digest", "purpose", "email", "user_id",
        "expires_at", "consumed_at", "created_at",
    }
    assert _column_names(AuthMailEvent) == {
        "id", "challenge_id", "purpose", "email", "client_key_digest",
        "delivery_status", "provider_message_id", "created_at",
    }

    assert AuthChallenge.__table__.c.token_digest.unique is True
    assert AuthChallenge.__table__.c.token_digest.type.length == 64
    assert AuthMailEvent.__table__.c.client_key_digest.type.length == 64
    assert AuthChallenge.__table__.c.user_id.nullable is True
    assert AuthMailEvent.__table__.c.challenge_id.nullable is True

    challenge_user_fk = next(
        fk for fk in AuthChallenge.__table__.foreign_key_constraints
        if any(element.target_fullname == "users.id" for element in fk.elements)
    )
    assert {element.ondelete for element in challenge_user_fk.elements} == {"CASCADE"}

    event_challenge_fk = next(
        fk for fk in AuthMailEvent.__table__.foreign_key_constraints
        if any(element.target_fullname == "auth_challenges.id"
               for element in fk.elements)
    )
    assert {element.ondelete for element in event_challenge_fk.elements} == {"SET NULL"}


def test_auth_control_schema_has_constraints_indexes_and_no_user_rls(
        bypass_engine):
    with bypass_engine.connect() as conn:
        columns = {}
        for table_name in ("auth_challenges", "auth_mail_events"):
            rows = conn.execute(text("""
                SELECT column_name, is_nullable, character_maximum_length
                FROM information_schema.columns
                WHERE table_schema='public' AND table_name=:table_name
            """), {"table_name": table_name}).mappings().all()
            columns[table_name] = {row["column_name"]: row for row in rows}

        challenge_checks = [
            " ".join(definition.lower().split())
            for definition in _constraint_definitions(conn, "auth_challenges")
        ]
        table_state = conn.execute(text("""
            SELECT c.relname, c.relrowsecurity, c.relforcerowsecurity,
                   (SELECT count(*) FROM pg_policies AS p
                    WHERE p.schemaname = n.nspname
                      AND p.tablename = c.relname) AS policy_count
            FROM pg_class AS c
            JOIN pg_namespace AS n ON n.oid = c.relnamespace
            WHERE n.nspname='public'
              AND c.relname IN ('auth_challenges', 'auth_mail_events')
        """)).mappings().all()

        challenge_indexes = _index_columns(conn, "auth_challenges")
        mail_indexes = _index_columns(conn, "auth_mail_events")

    challenge_columns = columns["auth_challenges"]
    mail_columns = columns["auth_mail_events"]
    for name in ("id", "token_digest", "purpose", "email",
                 "expires_at", "created_at"):
        assert challenge_columns[name]["is_nullable"] == "NO"
    assert challenge_columns["user_id"]["is_nullable"] == "YES"
    assert challenge_columns["consumed_at"]["is_nullable"] == "YES"
    assert challenge_columns["token_digest"]["character_maximum_length"] == 64

    for name in ("id", "purpose", "email", "client_key_digest",
                 "delivery_status", "created_at"):
        assert mail_columns[name]["is_nullable"] == "NO"
    assert mail_columns["challenge_id"]["is_nullable"] == "YES"
    assert mail_columns["provider_message_id"]["is_nullable"] == "YES"
    assert mail_columns["client_key_digest"]["character_maximum_length"] == 64

    assert any("registration" in definition and "user_id is null" in definition
               for definition in challenge_checks)
    assert any("password_reset" in definition
               and "user_id is not null" in definition
               for definition in challenge_checks)

    assert ("email", "purpose", "created_at") in challenge_indexes.values()
    assert ("expires_at",) in challenge_indexes.values()
    assert ("email", "created_at") in mail_indexes.values()
    assert ("client_key_digest", "created_at") in mail_indexes.values()
    assert ("created_at",) in mail_indexes.values()

    assert {row["relname"] for row in table_state} == {
        "auth_challenges", "auth_mail_events",
    }
    assert all(not row["relrowsecurity"] and not row["relforcerowsecurity"]
               and row["policy_count"] == 0 for row in table_state)


def test_challenge_digest_and_purpose_user_id_constraints(
        bypass_engine, auth_user):
    user_id, email = auth_user
    _insert_challenge(
        bypass_engine, digest="a" * 64, purpose="registration",
        email=email, user_id=None,
    )
    _insert_challenge(
        bypass_engine, digest="b" * 64, purpose="password_reset",
        email=email, user_id=user_id,
    )

    with pytest.raises(IntegrityError):
        _insert_challenge(
            bypass_engine, digest="a" * 64, purpose="registration",
            email=email, user_id=None,
        )
    with pytest.raises(DBAPIError):
        _insert_challenge(
            bypass_engine, digest="c" * 64, purpose="registration",
            email=email, user_id=user_id,
        )
    with pytest.raises(DBAPIError):
        _insert_challenge(
            bypass_engine, digest="d" * 64, purpose="password_reset",
            email=email, user_id=None,
        )
    with pytest.raises(DBAPIError):
        _insert_challenge(
            bypass_engine, digest="e" * 64, purpose="unknown",
            email=email, user_id=None,
        )


def test_mail_event_purpose_and_delivery_status_constraints(bypass_engine):
    with pytest.raises(DBAPIError):
        _insert_mail_event(bypass_engine, purpose="unknown")
    with pytest.raises(DBAPIError):
        _insert_mail_event(bypass_engine, status="unknown")


def test_auth_control_foreign_keys_have_expected_delete_semantics(
        bypass_engine, auth_user):
    user_id, email = auth_user
    challenge_id = _insert_challenge(
        bypass_engine, digest="f" * 64, purpose="password_reset",
        email=email, user_id=user_id,
    )
    _insert_mail_event(
        bypass_engine, challenge_id=challenge_id,
        purpose="password_reset", status="sent", email=email,
    )

    with bypass_engine.begin() as conn:
        conn.execute(text("DELETE FROM users WHERE id=:user_id"),
                     {"user_id": user_id})

    with bypass_engine.connect() as conn:
        assert conn.execute(text(
            "SELECT count(*) FROM auth_challenges WHERE id=:id"
        ), {"id": challenge_id}).scalar_one() == 0
        assert conn.execute(text(
            "SELECT challenge_id FROM auth_mail_events "
            "WHERE purpose='password_reset' AND email=:email"
        ), {"email": email}).scalar_one() is None
