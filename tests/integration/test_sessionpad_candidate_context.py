"""SessionPad candidate context schema and service contract."""
import pytest
from flask import g
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError

from app.services import intake as intake_svc
PW = "pw12345678"


def _seed_candidate(app, bypass_engine, email, *, context=None, provenance=None):
    from app.services.provisioning import create_user_with_defaults

    with app.app_context():
        user_id, _ = create_user_with_defaults(
            email,
            "Context Tester",
            password=PW,
            learning_languages=["fr"],
        )
    with bypass_engine.begin() as conn:
        list_id = conn.execute(text(
            "SELECT id FROM word_lists "
            "WHERE user_id=:user AND language_code='fr'"
        ), {"user": user_id}).scalar_one()
        source_id = conn.execute(text(
            "INSERT INTO intake_sources("
            "user_id,source_type,language_code,word_list_id,status,"
            "total_segments,total_candidates,created_at"
            ") VALUES (:user,'sessionpad','fr',:list,'done',0,1,now()) "
            "RETURNING id"
        ), {"user": user_id, "list": list_id}).scalar_one()
        candidate_id = conn.execute(text(
            "INSERT INTO word_candidates("
            "source_id,user_id,word,status,context_excerpt,"
            "context_provenance,created_at"
            ") VALUES (:source,:user,'prendre des cours','pending',"
            ":context,:provenance,now()) RETURNING id"
        ), {
            "source": source_id,
            "user": user_id,
            "context": context,
            "provenance": provenance,
        }).scalar_one()
    return user_id, source_id, candidate_id


def test_context_pair_constraint_accepts_only_meaningful_valid_pairs(
    app,
    bypass_engine,
):
    _, source_id, _ = _seed_candidate(
        app,
        bypass_engine,
        "context-valid@t.com",
        context="prendre des cours de danse",
        provenance="source_quote",
    )

    invalid_values = [
        (None, "user_edited"),
        ("un contexte", None),
        ("un contexte", "generated"),
        ("   ", "source_quote"),
        ("x" * 301, "user_edited"),
    ]
    for context, provenance in invalid_values:
        with pytest.raises(DBAPIError):
            with bypass_engine.begin() as conn:
                conn.execute(text(
                    "INSERT INTO word_candidates("
                    "source_id,user_id,word,status,context_excerpt,"
                    "context_provenance,created_at"
                    ") SELECT :source,user_id,:word,'pending',"
                    ":context,:provenance,now() "
                    "FROM intake_sources WHERE id=:source"
                ), {
                    "source": source_id,
                    "word": f"invalid-{provenance}-{len(context or '')}",
                    "context": context,
                    "provenance": provenance,
                })


def test_user_context_edit_is_trimmed_and_marked_user_edited(
    app,
    bypass_engine,
):
    user_id, _, candidate_id = _seed_candidate(
        app,
        bypass_engine,
        "context-edit@t.com",
    )

    with app.test_request_context():
        g.rls_uid = user_id
        assert intake_svc.accept_candidate(
            user_id,
            candidate_id,
            {"context_excerpt": "  prendre des cours de danse  "},
        )

    with bypass_engine.connect() as conn:
        row = conn.execute(text(
            "SELECT context_excerpt,context_provenance,status "
            "FROM word_candidates WHERE id=:candidate"
        ), {"candidate": candidate_id}).mappings().one()
    assert row == {
        "context_excerpt": "prendre des cours de danse",
        "context_provenance": "user_edited",
        "status": "accepted",
    }


def test_user_context_edit_rejects_overlong_value_without_mutation(
    app,
    bypass_engine,
):
    user_id, _, candidate_id = _seed_candidate(
        app,
        bypass_engine,
        "context-too-long@t.com",
        context="source phrase",
        provenance="source_quote",
    )

    with app.test_request_context():
        g.rls_uid = user_id
        with pytest.raises(ValueError, match="300"):
            intake_svc.accept_candidate(
                user_id,
                candidate_id,
                {"context_excerpt": "x" * 301},
            )

    with bypass_engine.connect() as conn:
        row = conn.execute(text(
            "SELECT context_excerpt,context_provenance,status "
            "FROM word_candidates WHERE id=:candidate"
        ), {"candidate": candidate_id}).mappings().one()
    assert row == {
        "context_excerpt": "source phrase",
        "context_provenance": "source_quote",
        "status": "pending",
    }

def test_clearing_user_context_clears_provenance(
    app,
    bypass_engine,
):
    user_id, _, candidate_id = _seed_candidate(
        app,
        bypass_engine,
        "context-clear@t.com",
        context="source phrase",
        provenance="source_quote",
    )

    with app.test_request_context():
        g.rls_uid = user_id
        assert intake_svc.accept_candidate(
            user_id,
            candidate_id,
            {"context_excerpt": "   "},
        )

    with bypass_engine.connect() as conn:
        row = conn.execute(text(
            "SELECT context_excerpt,context_provenance,status "
            "FROM word_candidates WHERE id=:candidate"
        ), {"candidate": candidate_id}).mappings().one()
    assert row == {
        "context_excerpt": None,
        "context_provenance": None,
        "status": "accepted",
    }
