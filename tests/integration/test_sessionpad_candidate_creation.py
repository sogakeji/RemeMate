"""Shared SessionPad candidate creation service."""
from concurrent.futures import ThreadPoolExecutor
from threading import Barrier
from flask import g
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError

from app.extensions import db
from app.services import sessionpad_candidates as candidates


PW = "pw12345678"


def _seed_source(app, bypass_engine, email, *, language="fr"):
    from app.services.provisioning import create_user_with_defaults

    with app.app_context():
        user_id, _ = create_user_with_defaults(
            email,
            "Candidate Creator",
            password=PW,
            learning_languages=[language],
        )
    with bypass_engine.begin() as conn:
        list_id = conn.execute(text(
            "SELECT id FROM word_lists "
            "WHERE user_id=:user AND language_code=:language"
        ), {"user": user_id, "language": language}).scalar_one()
        source_id = conn.execute(text(
            "INSERT INTO intake_sources("
            "user_id,source_type,language_code,word_list_id,status,"
            "total_segments,total_candidates,created_at"
            ") VALUES (:user,'sessionpad',:language,:list,'done',0,0,now()) "
            "RETURNING id"
        ), {
            "user": user_id,
            "language": language,
            "list": list_id,
        }).scalar_one()
    return user_id, list_id, source_id


def test_shared_creation_persists_context_without_copying_source_example(
    app,
    bypass_engine,
):
    user_id, _, source_id = _seed_source(
        app,
        bypass_engine,
        "candidate-create@t.com",
    )
    draft = candidates.CandidateDraft(
        term="prendre des cours",
        context="Elle prend des cours de danse.",
        provenance="user_edited",
    )

    with app.test_request_context():
        g.rls_uid = user_id
        result = candidates.create_sessionpad_candidates(
            user_id,
            source_id,
            [draft],
        )
        db.session.commit()

    assert result.created_count == 1
    assert result.existing_word_count == 0
    assert len(result.candidate_ids) == 1
    with bypass_engine.connect() as conn:
        row = conn.execute(text(
            "SELECT word,context_excerpt,context_provenance,source_example "
            "FROM word_candidates WHERE id=:candidate"
        ), {"candidate": result.candidate_ids[0]}).mappings().one()
    assert row == {
        "word": "prendre des cours",
        "context_excerpt": "Elle prend des cours de danse.",
        "context_provenance": "user_edited",
        "source_example": None,
    }


def test_repeated_term_reuses_candidate_without_overwriting_context(
    app,
    bypass_engine,
):
    user_id, _, source_id = _seed_source(
        app,
        bypass_engine,
        "candidate-reuse@t.com",
    )

    with app.test_request_context():
        g.rls_uid = user_id
        first = candidates.create_sessionpad_candidates(
            user_id,
            source_id,
            [candidates.CandidateDraft(
                term="Prendre des cours",
                context="first context",
                provenance="user_edited",
            )],
        )
        db.session.commit()
        second = candidates.create_sessionpad_candidates(
            user_id,
            source_id,
            [candidates.CandidateDraft(
                term=" prendre des cours ",
                context="replacement context",
                provenance="user_edited",
            )],
        )
        db.session.commit()

    assert first.created_count == 1
    assert second.created_count == 0
    assert second.candidate_ids[0] == first.candidate_ids[0]
    with bypass_engine.connect() as conn:
        row = conn.execute(text(
            "SELECT word,context_excerpt,context_provenance "
            "FROM word_candidates WHERE id=:candidate"
        ), {"candidate": first.candidate_ids[0]}).mappings().one()
    assert row == {
        "word": "Prendre des cours",
        "context_excerpt": "first context",
        "context_provenance": "user_edited",
    }


def test_database_rejects_concurrent_active_duplicate_in_one_source(
    app, bypass_engine,
):
    user_id, _, source_id = _seed_source(
        app,
        bypass_engine,
        "sp2-concurrent@t.com",
    )

    barrier = Barrier(2)

    def insert(term):
        try:
            with bypass_engine.begin() as conn:
                barrier.wait()
                conn.execute(text(
                    "INSERT INTO word_candidates("
                    "source_id,user_id,word,status,created_at"
                    ") VALUES (:source,:user,:term,'pending',now())"
                ), {"source": source_id, "user": user_id, "term": term})
            return "created"
        except IntegrityError:
            return "duplicate"

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(insert, ["Alpha", " alpha "]))

    assert sorted(results) == ["created", "duplicate"]
    with bypass_engine.connect() as conn:
        assert conn.execute(text(
            "SELECT count(*) FROM word_candidates WHERE source_id=:source"
        ), {"source": source_id}).scalar_one() == 1

def test_active_candidate_uniqueness_is_scoped_to_source_and_status(
    app, bypass_engine,
):
    user_id, list_id, first_source_id = _seed_source(
        app,
        bypass_engine,
        "sp2-index-scope@t.com",
    )
    with bypass_engine.begin() as conn:
        second_source_id = conn.execute(text(
            "INSERT INTO intake_sources("
            "user_id,source_type,language_code,word_list_id,status,created_at"
            ") VALUES (:user,'sessionpad','fr',:list,'done',now()) RETURNING id"
        ), {"user": user_id, "list": list_id}).scalar_one()
        conn.execute(text(
            "INSERT INTO word_candidates("
            "source_id,user_id,word,status,created_at"
            ") VALUES "
            "(:first,:user,'Alpha','ignored',now()),"
            "(:first,:user,' alpha ','pending',now()),"
            "(:second,:user,'ALPHA','pending',now())"
        ), {
            "first": first_source_id,
            "second": second_source_id,
            "user": user_id,
        })

    with bypass_engine.connect() as conn:
        rows = conn.execute(text(
            "SELECT source_id,status FROM word_candidates "
            "WHERE user_id=:user ORDER BY id"
        ), {"user": user_id}).mappings().all()
    assert rows == [
        {"source_id": first_source_id, "status": "ignored"},
        {"source_id": first_source_id, "status": "pending"},
        {"source_id": second_source_id, "status": "pending"},
    ]

def test_reused_candidate_can_fill_an_empty_context_once(app, bypass_engine):
    user_id, _, source_id = _seed_source(
        app,
        bypass_engine,
        "sp2-fill-context@t.com",
    )
    with app.test_request_context():
        g.rls_uid = user_id
        first = candidates.create_sessionpad_candidates(
            user_id,
            source_id,
            [candidates.CandidateDraft("se reposer", None, None)],
        )
        db.session.commit()
        second = candidates.create_sessionpad_candidates(
            user_id,
            source_id,
            [candidates.CandidateDraft(
                "SE REPOSER",
                "Elle se repose.",
                "source_quote",
            )],
        )
        db.session.commit()

    assert first.candidate_ids == second.candidate_ids
    assert second.created_count == 0
    with bypass_engine.connect() as conn:
        row = conn.execute(text(
            "SELECT context_excerpt,context_provenance "
            "FROM word_candidates WHERE id=:candidate"
        ), {"candidate": first.candidate_ids[0]}).mappings().one()
    assert row == {
        "context_excerpt": "Elle se repose.",
        "context_provenance": "source_quote",
    }