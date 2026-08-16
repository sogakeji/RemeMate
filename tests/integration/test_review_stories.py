"""Review-story integration: summary, generation, state, RLS, and observation.

Covers the provider-free data contract plus provider orchestration, transactional
state, privacy-safe events, token accounting, and concurrency. No routes or UI.
"""
from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
import json
from datetime import date, datetime, timedelta, timezone
from threading import Barrier, Event

import pytest
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError, ProgrammingError

from app.models.review_story import (
    LEARNING_FUNNEL_EVENT_TYPES,
    REVIEW_STORY_STATUSES,
)
from app.services.review_stories import (
    ELIGIBILITY_NORMAL,
    ELIGIBILITY_SILENT,
    ELIGIBILITY_STRONG,
    REVIEW_STORY_CONTRACT_VERSION,
    get_daily_review_story_summary,
    review_story_input_hash,
)
from tests.helpers import make_user, provision_user, set_uid

HASH64_A = "a" * 64
HASH64_B = "b" * 64
PW = "pw12345678"


# ---------------------------------------------------------------------------
# Fixture helpers
# ---------------------------------------------------------------------------


def _set_rls_uid(uid):
    """Inject RLS GUC for bare app_context service calls (no request hooks)."""
    from flask import g
    from app.extensions import db

    g.rls_uid = uid
    db.session.execute(
        text("SELECT set_config('app.current_user_id', :u, false)"),
        {"u": str(uid)},
    )
    db.session.commit()
    db.session.expire_all()


def _set_user_lang(bypass_engine, uid, *, current="fr", learning="fr", tz="UTC"):
    with bypass_engine.begin() as c:
        c.execute(text(
            "UPDATE users SET learning_languages=:l, current_language=:c, "
            "timezone=:tz WHERE id=:uid"
        ), {"l": learning, "c": current, "tz": tz, "uid": uid})


def _set_feedback_lang(bypass_engine, uid, feedback="zh"):
    with bypass_engine.begin() as c:
        c.execute(text(
            "UPDATE user_settings SET feedback_language=:f WHERE user_id=:uid"
        ), {"f": feedback, "uid": uid})


def _ensure_list(bypass_engine, uid, language="fr"):
    with bypass_engine.begin() as c:
        list_id = c.execute(text(
            "SELECT id FROM word_lists WHERE user_id=:u AND language_code=:lang"
        ), {"u": uid, "lang": language}).scalar()
        if list_id is None:
            list_id = c.execute(text(
                "INSERT INTO word_lists(user_id,name,language_code,created_at) "
                "VALUES (:u,:n,:lang,now()) RETURNING id"
            ), {"u": uid, "n": f"L-{language}", "lang": language}).scalar()
        return list_id


def _add_word(
    bypass_engine,
    uid,
    surface,
    *,
    language="fr",
    meanings=None,
    pos="n",
):
    """Create a word (+ optional definitions). meanings: list of (pos, meaning)."""
    list_id = _ensure_list(bypass_engine, uid, language)
    with bypass_engine.begin() as c:
        word_id = c.execute(text(
            "INSERT INTO words(list_id,word,marked,due_date,interval,ease,reps,lapses) "
            "VALUES (:l,:w,false,now(),1,2.5,0,0) RETURNING id"
        ), {"l": list_id, "w": surface}).scalar()
        if meanings:
            for p, m in meanings:
                c.execute(text(
                    "INSERT INTO definitions(word_id,part_of_speech,meaning) "
                    "VALUES (:w,:p,:m)"
                ), {"w": word_id, "p": p, "m": m})
        elif meanings is None:
            c.execute(text(
                "INSERT INTO definitions(word_id,part_of_speech,meaning) "
                "VALUES (:w,:p,:m)"
            ), {"w": word_id, "p": pos, "m": f"meaning-{surface}"})
        return word_id


def _log(
    bypass_engine,
    uid,
    word_id,
    grade,
    *,
    ts: datetime,
    source="review",
):
    with bypass_engine.begin() as c:
        c.execute(text(
            "INSERT INTO review_logs(word_id,user_id,ts,grade,source,interval_after) "
            "VALUES (:w,:u,:ts,:g,:s,1)"
        ), {"w": word_id, "u": uid, "ts": ts, "g": grade, "s": source})


def _seed_user(app, bypass_engine, email, *, tz="UTC", lang="fr", feedback="zh"):
    uid = provision_user(app, email, PW, tz=tz)
    _set_user_lang(bypass_engine, uid, current=lang, learning=lang, tz=tz)
    _set_feedback_lang(bypass_engine, uid, feedback)
    return uid


# ---------------------------------------------------------------------------
# Daily summary: window, worst grade, isolation, eligibility, snapshots
# ---------------------------------------------------------------------------


def test_summary_uses_local_day_and_excludes_adjacent_nights(
    app, bypass_engine,
):
    """Asia/Shanghai day D includes [D 00:00, D+1 00:00) local only."""
    uid = _seed_user(app, bypass_engine, "day@t.com", tz="Asia/Shanghai")
    # Local date 2026-07-22 → UTC [2026-07-21 16:00, 2026-07-22 16:00)
    in_day = datetime(2026, 7, 21, 16, 0, 0)          # local midnight
    near_end = datetime(2026, 7, 22, 15, 59, 59)      # still inside
    before = datetime(2026, 7, 21, 15, 59, 59)        # previous local day
    after = datetime(2026, 7, 22, 16, 0, 0)           # next local day

    words = []
    for i, surface in enumerate(["in1", "in2", "edge", "before", "after"]):
        words.append(_add_word(bypass_engine, uid, surface))

    _log(bypass_engine, uid, words[0], 5, ts=in_day)
    _log(bypass_engine, uid, words[1], 3, ts=near_end)
    _log(bypass_engine, uid, words[2], 2, ts=near_end)
    _log(bypass_engine, uid, words[3], 2, ts=before)
    _log(bypass_engine, uid, words[4], 2, ts=after)

    # Pad to eligibility so targets are populated; boundary filter still applies.
    filler = []
    for i in range(7):
        wid = _add_word(bypass_engine, uid, f"pad{i}")
        filler.append(wid)
        _log(bypass_engine, uid, wid, 5, ts=in_day + timedelta(minutes=i + 1))

    with app.app_context():
        _set_rls_uid(uid)
        summary = get_daily_review_story_summary(
            uid,
            local_date=date(2026, 7, 22),
            now_utc=datetime(2026, 7, 22, 8, 0, 0, tzinfo=timezone.utc),
        )

    assert summary is not None
    assert summary.local_date == date(2026, 7, 22)
    assert summary.day_start_utc == datetime(2026, 7, 21, 16, 0, 0)
    assert summary.day_end_utc == datetime(2026, 7, 22, 16, 0, 0)
    # 3 boundary-in + 7 pad; adjacent-night words excluded
    assert summary.reviewed_word_count == 10
    assert summary.forgotten_word_count == 1
    assert summary.weak_word_count == 2
    assert summary.eligibility == ELIGIBILITY_NORMAL
    target_ids = {t.word_id for t in summary.targets}
    # grade-2 edge word is selected first among targets
    assert words[2] in target_ids
    assert words[3] not in target_ids and words[3] not in summary.term_word_ids.values()
    assert words[4] not in target_ids and words[4] not in summary.term_word_ids.values()
    assert set(filler).isdisjoint({words[3], words[4]})


def test_summary_same_word_repeated_grades_uses_worst(
    app, bypass_engine,
):
    uid = _seed_user(app, bypass_engine, "worst@t.com", tz="UTC")
    day = date(2026, 7, 22)
    base = datetime(2026, 7, 22, 10, 0, 0)

    # One word reviewed thrice: 5, then 3, then 2 → worst 2, counts as 1 word
    wid = _add_word(bypass_engine, uid, "maison")
    _log(bypass_engine, uid, wid, 5, ts=base)
    _log(bypass_engine, uid, wid, 3, ts=base + timedelta(minutes=5))
    _log(bypass_engine, uid, wid, 2, ts=base + timedelta(minutes=10), source="bark")

    # Nine more distinct easy words → total 10 reviewed, 1 forgotten → normal
    for i in range(9):
        w = _add_word(bypass_engine, uid, f"easy{i}")
        _log(bypass_engine, uid, w, 5, ts=base + timedelta(minutes=20 + i))

    with app.app_context():
        _set_rls_uid(uid)
        summary = get_daily_review_story_summary(uid, local_date=day)

    assert summary.reviewed_word_count == 10
    assert summary.forgotten_word_count == 1
    assert summary.weak_word_count == 1
    assert summary.eligibility == ELIGIBILITY_NORMAL
    # maison (grade 2) must be first among targets
    assert summary.targets[0].word_id == wid
    assert summary.targets[0].worst_grade == 2
    assert summary.targets[0].snapshot.key == "t1"
    assert summary.input_hash is not None


def test_summary_cross_user_and_cross_language_isolation(
    app, bypass_engine,
):
    a = _seed_user(app, bypass_engine, "iso-a@t.com", tz="UTC", lang="fr")
    b = _seed_user(app, bypass_engine, "iso-b@t.com", tz="UTC", lang="fr")
    day = date(2026, 7, 22)
    ts = datetime(2026, 7, 22, 12, 0, 0)

    # A: 10 fr words
    a_ids = []
    for i in range(10):
        wid = _add_word(bypass_engine, a, f"a-fr-{i}", language="fr")
        a_ids.append(wid)
        _log(bypass_engine, a, wid, 5, ts=ts + timedelta(seconds=i))

    # A also has en reviews that must not count while current_language=fr
    en = _add_word(bypass_engine, a, "english-only", language="en")
    _log(bypass_engine, a, en, 2, ts=ts)

    # B: different user's words
    b_ids = []
    for i in range(10):
        wid = _add_word(bypass_engine, b, f"b-fr-{i}", language="fr")
        b_ids.append(wid)
        _log(bypass_engine, b, wid, 2, ts=ts + timedelta(seconds=i))

    with app.app_context():
        _set_rls_uid(a)
        sa = get_daily_review_story_summary(a, local_date=day)
        _set_rls_uid(b)
        sb = get_daily_review_story_summary(b, local_date=day)

    assert sa.reviewed_word_count == 10
    assert sa.forgotten_word_count == 0
    assert en not in sa.term_word_ids.values()
    assert set(sa.term_word_ids.values()).issubset(set(a_ids))
    assert set(sa.term_word_ids.values()).isdisjoint(set(b_ids))

    assert sb.reviewed_word_count == 10
    assert sb.forgotten_word_count == 10
    assert sb.eligibility == ELIGIBILITY_STRONG
    assert set(sb.term_word_ids.values()).issubset(set(b_ids))
    assert set(sb.term_word_ids.values()).isdisjoint(set(a_ids))


@pytest.mark.parametrize(
    "n_reviewed,n_forgot,n_fuzzy,expected",
    [
        (9, 0, 0, ELIGIBILITY_SILENT),
        (10, 0, 0, ELIGIBILITY_NORMAL),
        (9, 5, 0, ELIGIBILITY_SILENT),
        (9, 6, 0, ELIGIBILITY_SILENT),
        (10, 5, 0, ELIGIBILITY_NORMAL),
        (10, 0, 5, ELIGIBILITY_NORMAL),
        (10, 0, 6, ELIGIBILITY_STRONG),
        (10, 3, 3, ELIGIBILITY_STRONG),
    ],
)
def test_summary_eligibility_boundaries_with_logs(
    app, bypass_engine, n_reviewed, n_forgot, n_fuzzy, expected,
):
    uid = _seed_user(
        app, bypass_engine,
        f"elig-{n_reviewed}-{n_forgot}-{n_fuzzy}@t.com",
        tz="UTC",
    )
    day = date(2026, 7, 22)
    ts = datetime(2026, 7, 22, 9, 0, 0)
    assert n_forgot + n_fuzzy <= n_reviewed
    for i in range(n_reviewed):
        grade = 2 if i < n_forgot else 3 if i < n_forgot + n_fuzzy else 5
        wid = _add_word(bypass_engine, uid, f"w{i}")
        _log(bypass_engine, uid, wid, grade, ts=ts + timedelta(seconds=i))

    with app.app_context():
        _set_rls_uid(uid)
        summary = get_daily_review_story_summary(uid, local_date=day)

    assert summary.reviewed_word_count == n_reviewed
    assert summary.forgotten_word_count == n_forgot
    assert summary.weak_word_count == n_forgot + n_fuzzy
    assert summary.eligibility == expected
    if expected == ELIGIBILITY_SILENT:
        assert summary.targets == ()
        assert summary.input_hash is None
        assert summary.provider_terms == ()
    else:
        assert 1 <= len(summary.targets) <= 5
        assert summary.input_hash is not None
        assert len(summary.input_hash) == 64


def test_summary_eligible_path_selects_five_targets(
    app, bypass_engine,
):
    """Production eligibility: 10 reviewed with 6 weak terms → 5 targets."""
    uid = _seed_user(app, bypass_engine, "targets-prod@t.com", tz="UTC")
    day = date(2026, 7, 22)
    ts = datetime(2026, 7, 22, 11, 0, 0)
    # 6 forgotten + 4 easy → strong, min(5, 10) = 5
    for i in range(10):
        grade = 2 if i < 6 else 5
        wid = _add_word(bypass_engine, uid, f"p{i:02d}")
        _log(bypass_engine, uid, wid, grade, ts=ts + timedelta(seconds=i))

    with app.app_context():
        _set_rls_uid(uid)
        s1 = get_daily_review_story_summary(uid, local_date=day)
        s2 = get_daily_review_story_summary(uid, local_date=day)

    assert s1.eligibility == ELIGIBILITY_STRONG
    assert s1.reviewed_word_count == 10
    assert len(s1.targets) == 5
    assert [t.snapshot.key for t in s1.targets] == [f"t{i}" for i in range(1, 6)]
    assert [t.word_id for t in s1.targets] == [t.word_id for t in s2.targets]
    assert s1.input_hash == s2.input_hash
    grades = [t.worst_grade for t in s1.targets]
    assert grades == sorted(grades)
    assert grades[:5].count(2) == 5  # five worst (forgot) first


@pytest.mark.parametrize("n_targets", [2, 3, 4, 5])
def test_summary_builds_exactly_n_target_snapshots(
    app, bypass_engine, n_targets, monkeypatch,
):
    """Snapshot/hash path for 2–5 words (eligibility forced; product floor is unit-tested).

    Real eligibility never emits targets with fewer than 10 reviewed words.
    Force normal here so
    integration still exercises snapshot keys, ordering, and provider-safe fields
    for each exact target count.
    """
    from app.services import review_stories as rs

    monkeypatch.setattr(
        rs, "review_story_eligibility",
        lambda **kwargs: ELIGIBILITY_NORMAL,
    )
    uid = _seed_user(
        app, bypass_engine, f"targets-n{n_targets}@t.com", tz="UTC",
    )
    day = date(2026, 7, 22)
    ts = datetime(2026, 7, 22, 11, 0, 0)
    # Mix grades so ordering is non-trivial; insert easy first then forgot
    for i in range(n_targets):
        grade = 5 if i < max(1, n_targets - 2) else 2
        wid = _add_word(bypass_engine, uid, f"t{i:02d}")
        _log(bypass_engine, uid, wid, grade, ts=ts + timedelta(seconds=i))

    with app.app_context():
        _set_rls_uid(uid)
        s1 = get_daily_review_story_summary(uid, local_date=day)
        s2 = get_daily_review_story_summary(uid, local_date=day)

    assert s1.reviewed_word_count == n_targets
    assert len(s1.targets) == n_targets
    assert [t.snapshot.key for t in s1.targets] == [
        f"t{i}" for i in range(1, n_targets + 1)
    ]
    assert [t.word_id for t in s1.targets] == [t.word_id for t in s2.targets]
    assert s1.input_hash == s2.input_hash
    assert s1.input_hash is not None and len(s1.input_hash) == 64
    grades = [t.worst_grade for t in s1.targets]
    assert grades == sorted(grades)
    for term in s1.provider_terms:
        assert set(term.keys()) == {
            "key", "surface", "part_of_speech", "meaning",
        }
        assert "word_id" not in term


def test_summary_main_definition_is_first_nonempty_meaning(
    app, bypass_engine,
):
    uid = _seed_user(app, bypass_engine, "def@t.com", tz="UTC")
    day = date(2026, 7, 22)
    ts = datetime(2026, 7, 22, 10, 0, 0)

    # 6 forgotten + 4 easy for strong eligibility
    first_id = None
    for i in range(10):
        if i == 0:
            wid = _add_word(
                bypass_engine, uid, "poly",
                meanings=[
                    ("", "   "),           # empty → skip
                    ("nf", "房子"),         # first non-empty meaning
                    ("nm", "家"),
                ],
            )
            first_id = wid
        else:
            wid = _add_word(bypass_engine, uid, f"f{i}")
        _log(bypass_engine, uid, wid, 2, ts=ts + timedelta(seconds=i))

    with app.app_context():
        _set_rls_uid(uid)
        summary = get_daily_review_story_summary(uid, local_date=day)

    target = next(t for t in summary.targets if t.word_id == first_id)
    assert target.snapshot.part_of_speech == "nf"
    assert target.snapshot.meaning == "房子"
    # internal mapping keeps word_id, provider dict does not
    assert summary.term_word_ids[target.snapshot.key] == first_id
    assert "word_id" not in target.snapshot.as_provider_dict()


def test_summary_hash_stable_and_busts_on_feedback_or_meaning(
    app, bypass_engine,
):
    uid = _seed_user(
        app, bypass_engine, "hash@t.com", tz="UTC", feedback="zh",
    )
    day = date(2026, 7, 22)
    ts = datetime(2026, 7, 22, 10, 0, 0)
    for i in range(10):
        wid = _add_word(bypass_engine, uid, f"h{i}", meanings=[("n", f"m{i}")])
        _log(bypass_engine, uid, wid, 2, ts=ts + timedelta(seconds=i))

    with app.app_context():
        from app.extensions import db

        _set_rls_uid(uid)
        s1 = get_daily_review_story_summary(uid, local_date=day)
        s2 = get_daily_review_story_summary(uid, local_date=day)
        assert s1.input_hash == s2.input_hash
        h_zh = s1.input_hash

        # recompute with feedback_language change via settings
        _set_feedback_lang(bypass_engine, uid, "en")
        db.session.expire_all()
        s_en = get_daily_review_story_summary(uid, local_date=day)
        assert s_en.input_hash != h_zh

        # change a meaning → hash busts
        _set_feedback_lang(bypass_engine, uid, "zh")
        first_wid = s1.targets[0].word_id
        with bypass_engine.begin() as c:
            c.execute(text(
                "UPDATE definitions SET meaning='CHANGED' WHERE word_id=:w"
            ), {"w": first_wid})
        db.session.expire_all()
        s_changed = get_daily_review_story_summary(uid, local_date=day)
        assert s_changed.input_hash != h_zh

        # pure recompute of hash from provider-safe snapshots matches summary
        recomputed = review_story_input_hash(
            contract_version=REVIEW_STORY_CONTRACT_VERSION,
            target_language="fr",
            feedback_language="zh",
            terms=tuple(t.snapshot for t in s_changed.targets),
        )
        assert recomputed == s_changed.input_hash


def test_summary_ignores_invalid_source_and_empty_surface(
    app, bypass_engine,
):
    uid = _seed_user(app, bypass_engine, "filter@t.com", tz="UTC")
    day = date(2026, 7, 22)
    ts = datetime(2026, 7, 22, 10, 0, 0)

    good = []
    for i in range(10):
        wid = _add_word(bypass_engine, uid, f"good{i}")
        good.append(wid)
        _log(bypass_engine, uid, wid, 2, ts=ts + timedelta(seconds=i))

    # write source must not count
    bad_src = _add_word(bypass_engine, uid, "from-write")
    _log(bypass_engine, uid, bad_src, 2, ts=ts, source="write")

    # empty / whitespace surface excluded by length(btrim(word)) > 0
    empty_id = _add_word(bypass_engine, uid, "   ")
    _log(bypass_engine, uid, empty_id, 2, ts=ts)

    with app.app_context():
        _set_rls_uid(uid)
        summary = get_daily_review_story_summary(uid, local_date=day)

    assert summary.reviewed_word_count == 10
    assert bad_src not in summary.term_word_ids.values()
    assert empty_id not in summary.term_word_ids.values()


def test_get_summary_returns_none_for_missing_user_or_bad_language(
    app, bypass_engine,
):
    with app.app_context():
        assert get_daily_review_story_summary(999999) is None

    uid = provision_user(app, "nolang@t.com", PW)
    with bypass_engine.begin() as c:
        c.execute(text(
            "UPDATE users SET current_language=NULL WHERE id=:u"
        ), {"u": uid})
    with app.app_context():
        from app.extensions import db
        db.session.expire_all()
        _set_rls_uid(uid)
        assert get_daily_review_story_summary(uid) is None


# ---------------------------------------------------------------------------
# FORCE RLS + unique constraints + event whitelist + concurrency
# ---------------------------------------------------------------------------


def _insert_run(conn, *, uid, local_date, input_hash, status="pending",
                target="fr", feedback="zh", contract=REVIEW_STORY_CONTRACT_VERSION):
    return conn.execute(text(
        "INSERT INTO review_story_runs("
        "user_id,local_date,target_language,feedback_language,"
        "contract_version,input_hash,status,attempt_count,attempt_version,"
        "created_at,updated_at) "
        "VALUES (:u,:d,:t,:f,:c,:h,:s,0,0,now(),now()) RETURNING id"
    ), {
        "u": uid, "d": local_date, "t": target, "f": feedback,
        "c": contract, "h": input_hash, "s": status,
    }).scalar()


def _insert_event(conn, *, uid, event_type, dedupe_key):
    return conn.execute(text(
        "INSERT INTO learning_funnel_events("
        "user_id,event_type,occurred_at,dedupe_key) "
        "VALUES (:u,:e,now(),:k) RETURNING id"
    ), {"u": uid, "e": event_type, "k": dedupe_key}).scalar()


def test_review_story_runs_force_rls_crud(app_engine, bypass_engine):
    a = make_user(bypass_engine, "rls-a@t.com")
    b = make_user(bypass_engine, "rls-b@t.com")
    day = date(2026, 7, 22)

    with bypass_engine.begin() as c:
        run_a = _insert_run(c, uid=a, local_date=day, input_hash=HASH64_A)
        run_b = _insert_run(c, uid=b, local_date=day, input_hash=HASH64_B)

    with app_engine.connect() as conn:
        set_uid(conn, a)
        rows = conn.execute(text(
            "SELECT id FROM review_story_runs ORDER BY id"
        )).fetchall()
        assert [r.id for r in rows] == [run_a]

        # own update ok
        conn.execute(text(
            "UPDATE review_story_runs SET status='ready' WHERE id=:id"
        ), {"id": run_a})
        conn.commit()

        # cannot update peer
        updated = conn.execute(text(
            "UPDATE review_story_runs SET status='failed' WHERE id=:id"
        ), {"id": run_b}).rowcount
        assert updated == 0
        conn.commit()

        # cannot insert as another user (RLS WITH CHECK)
        with pytest.raises(ProgrammingError) as ei:
            with conn.begin_nested():
                _insert_run(
                    conn, uid=b, local_date=day, input_hash="c" * 64,
                )
        assert "row-level security" in str(ei.value).lower()
        conn.rollback()
        set_uid(conn, a)

        # delete own
        deleted = conn.execute(text(
            "DELETE FROM review_story_runs WHERE id=:id"
        ), {"id": run_a}).rowcount
        assert deleted == 1
        conn.commit()

    # peer row still present
    with app_engine.connect() as conn:
        set_uid(conn, b)
        assert conn.execute(text(
            "SELECT count(*) FROM review_story_runs"
        )).scalar() == 1


def test_learning_funnel_events_force_rls(app_engine, bypass_engine):
    """Read isolation + write isolation (own INSERT ok; spoof other user denied)."""
    a = make_user(bypass_engine, "ev-a@t.com")
    b = make_user(bypass_engine, "ev-b@t.com")
    with bypass_engine.begin() as c:
        ea = _insert_event(
            c, uid=a, event_type="story_eligible_normal", dedupe_key=HASH64_A,
        )
        eb = _insert_event(
            c, uid=b, event_type="story_eligible_strong", dedupe_key=HASH64_B,
        )

    with app_engine.connect() as conn:
        set_uid(conn, a)
        rows = conn.execute(text(
            "SELECT id,event_type FROM learning_funnel_events"
        )).fetchall()
        assert len(rows) == 1
        assert rows[0].id == ea
        assert rows[0].event_type == "story_eligible_normal"

        # own INSERT ok
        own = _insert_event(
            conn, uid=a, event_type="story_cache_hit", dedupe_key="c" * 64,
        )
        conn.commit()
        assert own is not None
        assert conn.execute(text(
            "SELECT count(*) FROM learning_funnel_events"
        )).scalar() == 2

        # cannot INSERT spoofing peer user_id
        with pytest.raises(ProgrammingError) as ei:
            with conn.begin_nested():
                _insert_event(
                    conn, uid=b, event_type="story_writing_handoff",
                    dedupe_key="d" * 64,
                )
        assert "row-level security" in str(ei.value).lower()
        conn.rollback()
        set_uid(conn, a)

        # cannot UPDATE peer row
        updated = conn.execute(text(
            "UPDATE learning_funnel_events "
            "SET event_type='story_output_saved' WHERE id=:id"
        ), {"id": eb}).rowcount
        assert updated == 0
        conn.commit()

        # cannot DELETE peer row
        deleted = conn.execute(text(
            "DELETE FROM learning_funnel_events WHERE id=:id"
        ), {"id": eb}).rowcount
        assert deleted == 0
        conn.commit()

        # own DELETE ok
        deleted_own = conn.execute(text(
            "DELETE FROM learning_funnel_events WHERE id=:id"
        ), {"id": own}).rowcount
        assert deleted_own == 1
        conn.commit()

        # unset GUC → empty
        set_uid(conn, None)
        assert conn.execute(text(
            "SELECT count(*) FROM learning_funnel_events"
        )).scalar() == 0

    # peer row still present under their GUC
    with app_engine.connect() as conn:
        set_uid(conn, b)
        assert conn.execute(text(
            "SELECT count(*) FROM learning_funnel_events"
        )).scalar() == 1


def test_review_story_run_unique_identity(app_engine, bypass_engine):
    a = make_user(bypass_engine, "uniq@t.com")
    day = date(2026, 7, 22)
    with app_engine.connect() as conn:
        set_uid(conn, a)
        _insert_run(conn, uid=a, local_date=day, input_hash=HASH64_A)
        conn.commit()
        with pytest.raises(IntegrityError):
            _insert_run(conn, uid=a, local_date=day, input_hash=HASH64_A)
            conn.commit()
        conn.rollback()

        # different hash allowed same day
        _insert_run(conn, uid=a, local_date=day, input_hash=HASH64_B)
        conn.commit()


def test_learning_funnel_event_unique_and_type_whitelist(
    app_engine, bypass_engine,
):
    a = make_user(bypass_engine, "ev-uniq@t.com")
    with app_engine.connect() as conn:
        set_uid(conn, a)
        _insert_event(
            conn, uid=a, event_type="story_cache_hit", dedupe_key=HASH64_A,
        )
        conn.commit()
        with pytest.raises(IntegrityError):
            _insert_event(
                conn, uid=a, event_type="story_cache_hit", dedupe_key=HASH64_A,
            )
            conn.commit()
        conn.rollback()

        with pytest.raises(IntegrityError):
            _insert_event(
                conn, uid=a, event_type="not_a_real_event", dedupe_key=HASH64_B,
            )
            conn.commit()
        conn.rollback()

        # every whitelisted type is insertable with distinct keys
        for i, et in enumerate(LEARNING_FUNNEL_EVENT_TYPES):
            key = f"{i:064d}"
            if et == "story_cache_hit":
                # already inserted with HASH64_A; use fresh key
                pass
            _insert_event(conn, uid=a, event_type=et, dedupe_key=key)
        conn.commit()

    assert set(LEARNING_FUNNEL_EVENT_TYPES) == {
        "story_eligible_normal",
        "story_eligible_strong",
        "story_generation_started",
        "story_generation_ready",
        "story_generation_failed",
        "story_cache_hit",
        "story_writing_handoff",
        "story_output_saved",
    }
    assert set(REVIEW_STORY_STATUSES) == {"pending", "ready", "failed"}


def test_review_story_run_status_and_hash_length_checks(bypass_engine):
    """Check constraints are DB-enforced (use bypass role to isolate from RLS)."""
    a = make_user(bypass_engine, "ck@t.com")
    day = date(2026, 7, 22)
    with bypass_engine.connect() as conn:
        with pytest.raises(IntegrityError):
            with conn.begin():
                _insert_run(
                    conn, uid=a, local_date=day, input_hash="short",
                )

        with pytest.raises(IntegrityError):
            with conn.begin():
                _insert_run(
                    conn, uid=a, local_date=day, input_hash=HASH64_A,
                    status="running",
                )

        # attempt_count must be 0..2
        with pytest.raises(IntegrityError):
            with conn.begin():
                conn.execute(text(
                    "INSERT INTO review_story_runs("
                    "user_id,local_date,target_language,feedback_language,"
                    "contract_version,input_hash,status,attempt_count,"
                    "attempt_version,created_at,updated_at) "
                    "VALUES (:u,:d,'fr','zh',:c,:h,'pending',3,0,now(),now())"
                ), {
                    "u": a, "d": day, "c": REVIEW_STORY_CONTRACT_VERSION,
                    "h": HASH64_B,
                })


def test_review_story_run_concurrent_unique_conflict(bypass_engine):
    """Two concurrent inserts of the same identity: exactly one wins."""
    a = make_user(bypass_engine, "race@t.com")
    day = date(2026, 7, 22)
    barrier = Barrier(2)
    results: list[str] = []

    def worker():
        try:
            with bypass_engine.connect() as conn:
                barrier.wait(timeout=10)
                try:
                    with conn.begin():
                        _insert_run(
                            conn, uid=a, local_date=day, input_hash=HASH64_A,
                        )
                    results.append("ok")
                except IntegrityError:
                    results.append("conflict")
        except Exception as exc:  # pragma: no cover - surface unexpected
            results.append(f"err:{exc}")

    with ThreadPoolExecutor(max_workers=2) as pool:
        futs = [pool.submit(worker) for _ in range(2)]
        for f in futs:
            f.result(timeout=30)

    assert sorted(results) == ["conflict", "ok"]
    with bypass_engine.connect() as c:
        n = c.execute(text(
            "SELECT count(*) FROM review_story_runs WHERE user_id=:u"
        ), {"u": a}).scalar()
    assert n == 1


def test_force_rls_enabled_on_new_tables(bypass_engine):
    with bypass_engine.connect() as c:
        rows = c.execute(text(
            "SELECT relname, relrowsecurity, relforcerowsecurity "
            "FROM pg_class "
            "WHERE relname IN ('review_story_runs','learning_funnel_events') "
            "ORDER BY relname"
        )).fetchall()
    assert len(rows) == 2
    for row in rows:
        assert row.relrowsecurity is True
        assert row.relforcerowsecurity is True


def test_review_logs_daily_index_exists(bypass_engine):
    with bypass_engine.connect() as c:
        exists = c.execute(text(
            "SELECT 1 FROM pg_indexes "
            "WHERE indexname='ix_review_logs_user_ts_word_grade'"
        )).scalar()
    assert exists == 1


# ---------------------------------------------------------------------------
# RS2-B public state-machine seam
# ---------------------------------------------------------------------------


def test_claim_first_eligible_summary_returns_generation_lease(
    app, bypass_engine,
):
    from app.services.review_story_state import claim_review_story_run

    uid = _seed_user(app, bypass_engine, "rs2b-first@t.com", tz="UTC")
    day = date(2026, 7, 25)
    reviewed_at = datetime(2026, 7, 25, 9, 0, 0)
    for i in range(10):
        word_id = _add_word(bypass_engine, uid, f"lease-{i}")
        _log(
            bypass_engine,
            uid,
            word_id,
            2,
            ts=reviewed_at + timedelta(seconds=i),
        )

    now = datetime(2026, 7, 25, 10, 0, 0)
    with app.app_context():
        _set_rls_uid(uid)
        summary = get_daily_review_story_summary(uid, local_date=day)
        decision = claim_review_story_run(summary, now_utc=now)

    assert decision.action == "generate"
    assert decision.run_id > 0
    assert decision.attempt_count == 1
    assert decision.attempt_version == 1
    assert decision.lease_expires_at == now + timedelta(seconds=60)
    assert decision.story is None
    assert decision.error_code is None


def test_claim_active_pending_returns_same_run_without_new_attempt(
    app, bypass_engine,
):
    from app.services.review_story_state import claim_review_story_run

    uid = _seed_user(app, bypass_engine, "rs2b-pending@t.com", tz="UTC")
    day = date(2026, 7, 25)
    reviewed_at = datetime(2026, 7, 25, 9, 0, 0)
    for i in range(10):
        word_id = _add_word(bypass_engine, uid, f"pending-{i}")
        _log(
            bypass_engine,
            uid,
            word_id,
            2,
            ts=reviewed_at + timedelta(seconds=i),
        )

    now = datetime(2026, 7, 25, 10, 0, 0)
    with app.app_context():
        _set_rls_uid(uid)
        summary = get_daily_review_story_summary(uid, local_date=day)
        first = claim_review_story_run(summary, now_utc=now)
        second = claim_review_story_run(
            summary,
            now_utc=now + timedelta(seconds=30),
        )

    assert second.action == "pending"
    assert second.run_id == first.run_id
    assert second.attempt_count == 1
    assert second.attempt_version == 1
    assert second.lease_expires_at == first.lease_expires_at


def _successful_story_attempt():
    from app.services.review_story_generation import (
        ReviewStoryAttemptResult,
        ReviewStorySentence,
        ReviewStoryTermAnchor,
        ReviewStoryText,
        ValidatedReviewStory,
    )

    story = ValidatedReviewStory(
        title=ReviewStoryText(target="Une journée", translation="一天"),
        sentences=(
            ReviewStorySentence(
                target="Je vois mot-un.",
                translation="我看见词一。",
                terms=(ReviewStoryTermAnchor("t1", "mot-un", "词一"),),
            ),
            ReviewStorySentence(
                target="Je vois mot-deux.",
                translation="我看见词二。",
                terms=(ReviewStoryTermAnchor("t2", "mot-deux", "词二"),),
            ),
            ReviewStorySentence(
                target="Je vois mot-trois.",
                translation="我看见词三。",
                terms=(ReviewStoryTermAnchor("t3", "mot-trois", "词三"),),
            ),
            ReviewStorySentence(
                target="Je vois mot-quatre et mot-cinq.",
                translation="我看见词四和词五。",
                terms=(
                    ReviewStoryTermAnchor("t4", "mot-quatre", "词四"),
                    ReviewStoryTermAnchor("t5", "mot-cinq", "词五"),
                ),
            ),
        ),
    )
    return ReviewStoryAttemptResult(
        story=story,
        error_code=None,
        prompt_tokens=120,
        completion_tokens=80,
        provider="fake",
        model="fake-story",
    )


def test_complete_success_then_claim_returns_cached_story(
    app, bypass_engine,
):
    from app.services.review_story_state import (
        claim_review_story_run,
        complete_review_story_run,
    )

    uid = _seed_user(app, bypass_engine, "rs2b-cache@t.com", tz="UTC")
    day = date(2026, 7, 25)
    reviewed_at = datetime(2026, 7, 25, 9, 0, 0)
    for i in range(10):
        word_id = _add_word(bypass_engine, uid, f"cache-{i}")
        _log(
            bypass_engine,
            uid,
            word_id,
            2,
            ts=reviewed_at + timedelta(seconds=i),
        )

    now = datetime(2026, 7, 25, 10, 0, 0)
    attempt = _successful_story_attempt()
    with app.app_context():
        _set_rls_uid(uid)
        summary = get_daily_review_story_summary(uid, local_date=day)
        lease = claim_review_story_run(summary, now_utc=now)
        applied = complete_review_story_run(
            user_id=uid,
            run_id=lease.run_id,
            attempt_version=lease.attempt_version,
            result=attempt,
            now_utc=now + timedelta(seconds=5),
        )
        cached = claim_review_story_run(
            summary,
            now_utc=now + timedelta(seconds=10),
        )

    assert applied is True
    assert cached.action == "cached"
    assert cached.run_id == lease.run_id
    assert cached.attempt_count == 1
    assert cached.attempt_version == 1
    assert cached.lease_expires_at is None
    assert cached.story == attempt.story
    assert cached.error_code is None


def _failed_story_attempt(error_code="invalid_json"):
    from app.services.review_story_generation import ReviewStoryAttemptResult

    return ReviewStoryAttemptResult(
        story=None,
        error_code=error_code,
        prompt_tokens=40,
        completion_tokens=10,
        provider="fake",
        model="fake-story",
    )


def test_failed_run_allows_only_one_explicit_retry(
    app, bypass_engine,
):
    from app.services.review_story_state import (
        claim_review_story_run,
        complete_review_story_run,
    )

    uid = _seed_user(app, bypass_engine, "rs2b-retry@t.com", tz="UTC")
    day = date(2026, 7, 25)
    reviewed_at = datetime(2026, 7, 25, 9, 0, 0)
    for i in range(10):
        word_id = _add_word(bypass_engine, uid, f"retry-{i}")
        _log(
            bypass_engine,
            uid,
            word_id,
            2,
            ts=reviewed_at + timedelta(seconds=i),
        )

    now = datetime(2026, 7, 25, 10, 0, 0)
    with app.app_context():
        _set_rls_uid(uid)
        summary = get_daily_review_story_summary(uid, local_date=day)
        first = claim_review_story_run(summary, now_utc=now)
        first_applied = complete_review_story_run(
            user_id=uid,
            run_id=first.run_id,
            attempt_version=first.attempt_version,
            result=_failed_story_attempt(),
            now_utc=now + timedelta(seconds=5),
        )
        without_retry = claim_review_story_run(
            summary,
            now_utc=now + timedelta(seconds=10),
        )
        retry = claim_review_story_run(
            summary,
            retry_requested=True,
            now_utc=now + timedelta(seconds=15),
        )
        second_applied = complete_review_story_run(
            user_id=uid,
            run_id=retry.run_id,
            attempt_version=retry.attempt_version,
            result=_failed_story_attempt("provider_unavailable"),
            now_utc=now + timedelta(seconds=20),
        )
        exhausted = claim_review_story_run(
            summary,
            retry_requested=True,
            now_utc=now + timedelta(seconds=25),
        )

    assert first_applied is True
    assert without_retry.action == "failed"
    assert without_retry.run_id == first.run_id
    assert without_retry.attempt_count == 1
    assert without_retry.attempt_version == 1
    assert without_retry.error_code == "invalid_json"

    assert retry.action == "generate"
    assert retry.run_id == first.run_id
    assert retry.attempt_count == 2
    assert retry.attempt_version == 2
    assert retry.lease_expires_at == now + timedelta(seconds=75)
    assert retry.error_code is None

    assert second_applied is True
    assert exhausted.action == "failed"
    assert exhausted.run_id == first.run_id
    assert exhausted.attempt_count == 2
    assert exhausted.attempt_version == 2
    assert exhausted.lease_expires_at is None
    assert exhausted.error_code == "provider_unavailable"


def test_expired_lease_is_reclaimed_once_then_exhausted(
    app, bypass_engine,
):
    from app.services.review_story_state import claim_review_story_run

    uid = _seed_user(app, bypass_engine, "rs2b-expired@t.com", tz="UTC")
    day = date(2026, 7, 25)
    reviewed_at = datetime(2026, 7, 25, 9, 0, 0)
    for i in range(10):
        word_id = _add_word(bypass_engine, uid, f"expired-{i}")
        _log(
            bypass_engine,
            uid,
            word_id,
            2,
            ts=reviewed_at + timedelta(seconds=i),
        )

    now = datetime(2026, 7, 25, 10, 0, 0)
    with app.app_context():
        _set_rls_uid(uid)
        summary = get_daily_review_story_summary(uid, local_date=day)
        first = claim_review_story_run(summary, now_utc=now)
        reclaimed = claim_review_story_run(
            summary,
            now_utc=now + timedelta(seconds=61),
        )
        exhausted = claim_review_story_run(
            summary,
            retry_requested=True,
            now_utc=now + timedelta(seconds=122),
        )
        still_exhausted = claim_review_story_run(
            summary,
            retry_requested=True,
            now_utc=now + timedelta(seconds=183),
        )

    assert first.action == "generate"
    assert first.attempt_count == 1
    assert first.attempt_version == 1

    assert reclaimed.action == "generate"
    assert reclaimed.run_id == first.run_id
    assert reclaimed.attempt_count == 2
    assert reclaimed.attempt_version == 2
    assert reclaimed.lease_expires_at == now + timedelta(seconds=121)

    assert exhausted.action == "failed"
    assert exhausted.run_id == first.run_id
    assert exhausted.attempt_count == 2
    assert exhausted.attempt_version == 2
    assert exhausted.lease_expires_at is None
    assert exhausted.error_code == "lease_expired"

    assert still_exhausted.action == "failed"
    assert still_exhausted.attempt_count == 2
    assert still_exhausted.attempt_version == 2
    assert still_exhausted.error_code == "lease_expired"


def test_stale_attempt_cannot_overwrite_reclaimed_attempt(
    app, bypass_engine,
):
    from app.services.review_story_state import (
        claim_review_story_run,
        complete_review_story_run,
    )

    uid = _seed_user(app, bypass_engine, "rs2b-stale@t.com", tz="UTC")
    day = date(2026, 7, 25)
    reviewed_at = datetime(2026, 7, 25, 9, 0, 0)
    for i in range(10):
        word_id = _add_word(bypass_engine, uid, f"stale-{i}")
        _log(
            bypass_engine,
            uid,
            word_id,
            2,
            ts=reviewed_at + timedelta(seconds=i),
        )

    now = datetime(2026, 7, 25, 10, 0, 0)
    success = _successful_story_attempt()
    with app.app_context():
        _set_rls_uid(uid)
        summary = get_daily_review_story_summary(uid, local_date=day)
        first = claim_review_story_run(summary, now_utc=now)
        second = claim_review_story_run(
            summary,
            now_utc=now + timedelta(seconds=61),
        )
        stale_applied = complete_review_story_run(
            user_id=uid,
            run_id=first.run_id,
            attempt_version=first.attempt_version,
            result=success,
            now_utc=now + timedelta(seconds=62),
        )
        while_second_pending = claim_review_story_run(
            summary,
            now_utc=now + timedelta(seconds=63),
        )
        current_applied = complete_review_story_run(
            user_id=uid,
            run_id=second.run_id,
            attempt_version=second.attempt_version,
            result=success,
            now_utc=now + timedelta(seconds=64),
        )
        cached = claim_review_story_run(
            summary,
            now_utc=now + timedelta(seconds=65),
        )

    assert first.attempt_version == 1
    assert second.attempt_version == 2
    assert stale_applied is False
    assert while_second_pending.action == "pending"
    assert while_second_pending.attempt_version == 2
    assert current_applied is True
    assert cached.action == "cached"
    assert cached.attempt_count == 2
    assert cached.attempt_version == 2
    assert cached.story == success.story


def test_concurrent_first_claim_returns_one_generate_and_one_pending(
    app, bypass_engine,
):
    from app.services.review_story_state import claim_review_story_run

    uid = _seed_user(app, bypass_engine, "rs2b-race@t.com", tz="UTC")
    day = date(2026, 7, 25)
    reviewed_at = datetime(2026, 7, 25, 9, 0, 0)
    for i in range(10):
        word_id = _add_word(bypass_engine, uid, f"race-claim-{i}")
        _log(
            bypass_engine,
            uid,
            word_id,
            2,
            ts=reviewed_at + timedelta(seconds=i),
        )

    now = datetime(2026, 7, 25, 10, 0, 0)
    with app.app_context():
        _set_rls_uid(uid)
        summary = get_daily_review_story_summary(uid, local_date=day)

    barrier = Barrier(2)
    results = []

    def worker():
        from flask import g

        with app.test_request_context("/"):
            g.rls_uid = uid
            barrier.wait(timeout=10)
            decision = claim_review_story_run(summary, now_utc=now)
            return (
                decision.action,
                decision.run_id,
                decision.attempt_count,
                decision.attempt_version,
            )

    with ThreadPoolExecutor(max_workers=2) as pool:
        futures = [pool.submit(worker) for _ in range(2)]
        for future in futures:
            results.append(future.result(timeout=30))

    actions = sorted(result[0] for result in results)
    run_ids = {result[1] for result in results}
    attempts = {(result[2], result[3]) for result in results}

    assert actions == ["generate", "pending"]
    assert len(run_ids) == 1
    assert attempts == {(1, 1)}


def test_cross_user_cannot_complete_review_story_run(
    app, bypass_engine,
):
    from app.services.review_story_state import (
        claim_review_story_run,
        complete_review_story_run,
    )

    owner = _seed_user(app, bypass_engine, "rs2b-owner@t.com", tz="UTC")
    peer = _seed_user(app, bypass_engine, "rs2b-peer@t.com", tz="UTC")
    day = date(2026, 7, 25)
    reviewed_at = datetime(2026, 7, 25, 9, 0, 0)
    for i in range(10):
        word_id = _add_word(bypass_engine, owner, f"owner-{i}")
        _log(
            bypass_engine,
            owner,
            word_id,
            2,
            ts=reviewed_at + timedelta(seconds=i),
        )

    now = datetime(2026, 7, 25, 10, 0, 0)
    with app.app_context():
        _set_rls_uid(owner)
        summary = get_daily_review_story_summary(owner, local_date=day)
        lease = claim_review_story_run(summary, now_utc=now)

        _set_rls_uid(peer)
        spoofed = complete_review_story_run(
            user_id=owner,
            run_id=lease.run_id,
            attempt_version=lease.attempt_version,
            result=_successful_story_attempt(),
            now_utc=now + timedelta(seconds=5),
        )

        _set_rls_uid(owner)
        still_pending = claim_review_story_run(
            summary,
            now_utc=now + timedelta(seconds=10),
        )

    assert spoofed is False
    assert still_pending.action == "pending"
    assert still_pending.run_id == lease.run_id
    assert still_pending.attempt_version == lease.attempt_version


def test_completion_after_lease_expiry_is_rejected_before_reclaim(
    app, bypass_engine,
):
    from app.services.review_story_state import (
        claim_review_story_run,
        complete_review_story_run,
    )

    uid = _seed_user(app, bypass_engine, "rs2b-late@t.com", tz="UTC")
    day = date(2026, 7, 25)
    reviewed_at = datetime(2026, 7, 25, 9, 0, 0)
    for i in range(10):
        word_id = _add_word(bypass_engine, uid, f"late-{i}")
        _log(
            bypass_engine,
            uid,
            word_id,
            2,
            ts=reviewed_at + timedelta(seconds=i),
        )

    now = datetime(2026, 7, 25, 10, 0, 0)
    with app.app_context():
        _set_rls_uid(uid)
        summary = get_daily_review_story_summary(uid, local_date=day)
        first = claim_review_story_run(summary, now_utc=now)
        late_applied = complete_review_story_run(
            user_id=uid,
            run_id=first.run_id,
            attempt_version=first.attempt_version,
            result=_successful_story_attempt(),
            now_utc=now + timedelta(seconds=61),
        )
        reclaimed = claim_review_story_run(
            summary,
            now_utc=now + timedelta(seconds=62),
        )

    assert late_applied is False
    assert reclaimed.action == "generate"
    assert reclaimed.run_id == first.run_id
    assert reclaimed.attempt_count == 2
    assert reclaimed.attempt_version == 2


# ---------------------------------------------------------------------------
# RS2-C public orchestration and privacy-safe event seams
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def _reset_review_story_test_provider():
    yield
    from app.services import llm

    llm.set_registry(None)
    llm.reset_breaker()


def _valid_provider_story_json():
    return json.dumps(
        {
            "title": {
                "target": "Une journée",
                "translation": "一天",
            },
            "sentences": [
                {
                    "target": "Je vois mot-un.",
                    "translation": "我看见词一。",
                    "terms": [
                        {
                            "key": "t1",
                            "target_form": "mot-un",
                            "translation_form": "词一",
                        }
                    ],
                },
                {
                    "target": "Je vois mot-deux.",
                    "translation": "我看见词二。",
                    "terms": [
                        {
                            "key": "t2",
                            "target_form": "mot-deux",
                            "translation_form": "词二",
                        }
                    ],
                },
                {
                    "target": "Je vois mot-trois.",
                    "translation": "我看见词三。",
                    "terms": [
                        {
                            "key": "t3",
                            "target_form": "mot-trois",
                            "translation_form": "词三",
                        }
                    ],
                },
                {
                    "target": "Je vois mot-quatre et mot-cinq.",
                    "translation": "我看见词四和词五。",
                    "terms": [
                        {
                            "key": "t4",
                            "target_form": "mot-quatre",
                            "translation_form": "词四",
                        },
                        {
                            "key": "t5",
                            "target_form": "mot-cinq",
                            "translation_form": "词五",
                        },
                    ],
                },
            ],
        },
        ensure_ascii=False,
    )


def test_orchestrate_first_generation_returns_ready_and_records_observation(
    app, bypass_engine,
):
    from flask import g
    from app.services import llm
    from app.services.review_story_orchestration import orchestrate_review_story

    class Provider:
        name = "fake-story"
        calls = 0

        def call(self, messages, *, timeout, json_mode=False):
            self.calls += 1
            return llm.LLMResult(
                _valid_provider_story_json(),
                13,
                21,
                self.name,
                "story-model",
            )

    provider = Provider()
    llm.set_registry({"general": [provider]})
    llm.reset_breaker()
    uid = _seed_user(app, bypass_engine, "rs2c-ready@t.com", tz="UTC")
    day = date(2026, 7, 25)
    reviewed_at = datetime(2026, 7, 25, 9, 0, 0)
    for i in range(10):
        word_id = _add_word(bypass_engine, uid, f"orchestrate-{i}")
        _log(
            bypass_engine,
            uid,
            word_id,
            2,
            ts=reviewed_at + timedelta(seconds=i),
        )

    with app.test_request_context("/"):
        g.rls_uid = uid
        summary = get_daily_review_story_summary(uid, local_date=day)
        outcome = orchestrate_review_story(
            summary,
            now_utc=datetime(2026, 7, 25, 10, 0, 0),
        )
    llm.set_registry(None)
    llm.reset_breaker()

    assert outcome.action == "ready"
    assert outcome.story is not None
    assert outcome.error_code is None
    assert provider.calls == 1
    with bypass_engine.connect() as connection:
        token_row = connection.execute(text(
            "SELECT feature,prompt_tokens,completion_tokens "
            "FROM token_usage_log WHERE user_id=:uid"
        ), {"uid": uid}).one()
        event_types = set(connection.execute(text(
            "SELECT event_type FROM learning_funnel_events "
            "WHERE user_id=:uid"
        ), {"uid": uid}).scalars())
    assert token_row == ("review_story", 13, 21)
    assert event_types == {
        "story_eligible_strong",
        "story_generation_started",
        "story_generation_ready",
    }


def test_orchestrate_cached_story_does_not_repeat_provider_or_tokens(
    app, bypass_engine,
):
    from flask import g
    from app.services import llm
    from app.services.review_story_orchestration import orchestrate_review_story

    class Provider:
        name = "fake-story"
        calls = 0

        def call(self, messages, *, timeout, json_mode=False):
            self.calls += 1
            return llm.LLMResult(
                _valid_provider_story_json(),
                8,
                12,
                self.name,
                "story-model",
            )

    provider = Provider()
    llm.set_registry({"general": [provider]})
    llm.reset_breaker()
    uid = _seed_user(app, bypass_engine, "rs2c-cache@t.com", tz="UTC")
    day = date(2026, 7, 25)
    reviewed_at = datetime(2026, 7, 25, 9, 0, 0)
    for i in range(10):
        word_id = _add_word(bypass_engine, uid, f"cache-orchestrate-{i}")
        _log(
            bypass_engine,
            uid,
            word_id,
            2,
            ts=reviewed_at + timedelta(seconds=i),
        )

    with app.test_request_context("/"):
        g.rls_uid = uid
        summary = get_daily_review_story_summary(uid, local_date=day)
        first = orchestrate_review_story(
            summary,
            now_utc=datetime(2026, 7, 25, 10, 0, 0),
        )
        second = orchestrate_review_story(
            summary,
            now_utc=datetime(2026, 7, 25, 10, 0, 1),
        )
        third = orchestrate_review_story(
            summary,
            now_utc=datetime(2026, 7, 25, 10, 0, 2),
        )
    llm.set_registry(None)
    llm.reset_breaker()

    assert first.action == "ready"
    assert second.action == "cached"
    assert third.action == "cached"
    assert provider.calls == 1
    with bypass_engine.connect() as connection:
        token_count = connection.execute(text(
            "SELECT count(*) FROM token_usage_log "
            "WHERE user_id=:uid AND feature='review_story'"
        ), {"uid": uid}).scalar_one()
        event_counts = dict(connection.execute(text(
            "SELECT event_type,count(*) FROM learning_funnel_events "
            "WHERE user_id=:uid GROUP BY event_type"
        ), {"uid": uid}).all())
    assert token_count == 1
    assert event_counts["story_cache_hit"] == 1
    assert event_counts["story_generation_started"] == 1
    assert event_counts["story_generation_ready"] == 1


def test_orchestrate_invalid_result_records_tokens_and_failed_event(
    app, bypass_engine,
):
    from flask import g
    from app.services import llm
    from app.services.review_story_orchestration import orchestrate_review_story

    class Provider:
        name = "fake-invalid"

        def call(self, messages, *, timeout, json_mode=False):
            return llm.LLMResult(
                '{"unexpected":true}',
                7,
                9,
                self.name,
                "invalid-model",
            )

    llm.set_registry({"general": [Provider()]})
    llm.reset_breaker()
    uid = _seed_user(app, bypass_engine, "rs2c-invalid@t.com", tz="UTC")
    day = date(2026, 7, 25)
    reviewed_at = datetime(2026, 7, 25, 9, 0, 0)
    for i in range(10):
        word_id = _add_word(bypass_engine, uid, f"invalid-{i}")
        _log(
            bypass_engine,
            uid,
            word_id,
            2,
            ts=reviewed_at + timedelta(seconds=i),
        )

    with app.test_request_context("/"):
        g.rls_uid = uid
        summary = get_daily_review_story_summary(uid, local_date=day)
        outcome = orchestrate_review_story(
            summary,
            now_utc=datetime(2026, 7, 25, 10, 0, 0),
        )
    llm.set_registry(None)
    llm.reset_breaker()

    assert outcome.action == "failed"
    assert outcome.story is None
    assert outcome.error_code == "invalid_schema"
    with bypass_engine.connect() as connection:
        token_row = connection.execute(text(
            "SELECT prompt_tokens,completion_tokens FROM token_usage_log "
            "WHERE user_id=:uid AND feature='review_story'"
        ), {"uid": uid}).one()
        run_status = connection.execute(text(
            "SELECT status,error_code FROM review_story_runs "
            "WHERE user_id=:uid"
        ), {"uid": uid}).one()
        event_types = set(connection.execute(text(
            "SELECT event_type FROM learning_funnel_events "
            "WHERE user_id=:uid"
        ), {"uid": uid}).scalars())
    assert token_row == (14, 18)
    assert run_status == ("failed", "invalid_schema")
    assert "story_generation_failed" in event_types
    assert "story_generation_ready" not in event_types


def test_orchestrate_provider_unavailable_fails_without_token_log(
    app, bypass_engine,
):
    from flask import g
    from app.services import llm
    from app.services.review_story_orchestration import orchestrate_review_story

    llm.set_registry({"general": []})
    llm.reset_breaker()
    uid = _seed_user(app, bypass_engine, "rs2c-down@t.com", tz="UTC")
    day = date(2026, 7, 25)
    reviewed_at = datetime(2026, 7, 25, 9, 0, 0)
    for i in range(10):
        word_id = _add_word(bypass_engine, uid, f"down-{i}")
        _log(
            bypass_engine,
            uid,
            word_id,
            2,
            ts=reviewed_at + timedelta(seconds=i),
        )

    with app.test_request_context("/"):
        g.rls_uid = uid
        summary = get_daily_review_story_summary(uid, local_date=day)
        outcome = orchestrate_review_story(
            summary,
            now_utc=datetime(2026, 7, 25, 10, 0, 0),
        )
    llm.set_registry(None)
    llm.reset_breaker()

    assert outcome.action == "failed"
    assert outcome.story is None
    assert outcome.error_code == "provider_unavailable"
    with bypass_engine.connect() as connection:
        token_count = connection.execute(text(
            "SELECT count(*) FROM token_usage_log "
            "WHERE user_id=:uid AND feature='review_story'"
        ), {"uid": uid}).scalar_one()
        run_status = connection.execute(text(
            "SELECT status,error_code FROM review_story_runs "
            "WHERE user_id=:uid"
        ), {"uid": uid}).one()
        event_types = set(connection.execute(text(
            "SELECT event_type FROM learning_funnel_events "
            "WHERE user_id=:uid"
        ), {"uid": uid}).scalars())
    assert token_count == 0
    assert run_status == ("failed", "provider_unavailable")
    assert event_types == {
        "story_eligible_strong",
        "story_generation_started",
        "story_generation_failed",
    }


def test_record_review_story_event_is_idempotent_and_run_owned(
    app, bypass_engine,
):
    from flask import g
    from app.services.review_story_events import record_review_story_event
    from app.services.review_story_state import claim_review_story_run

    owner = _seed_user(app, bypass_engine, "rs2c-event-owner@t.com", tz="UTC")
    peer = _seed_user(app, bypass_engine, "rs2c-event-peer@t.com", tz="UTC")
    day = date(2026, 7, 25)
    reviewed_at = datetime(2026, 7, 25, 9, 0, 0)
    for i in range(10):
        word_id = _add_word(bypass_engine, owner, f"event-{i}")
        _log(
            bypass_engine,
            owner,
            word_id,
            2,
            ts=reviewed_at + timedelta(seconds=i),
        )

    now = datetime(2026, 7, 25, 10, 0, 0)
    with app.test_request_context("/"):
        g.rls_uid = owner
        summary = get_daily_review_story_summary(owner, local_date=day)
        lease = claim_review_story_run(summary, now_utc=now)
        created = record_review_story_event(
            user_id=owner,
            run_id=lease.run_id,
            event_type="story_generation_started",
            attempt_version=lease.attempt_version,
            occurred_at=now,
        )
        duplicate = record_review_story_event(
            user_id=owner,
            run_id=lease.run_id,
            event_type="story_generation_started",
            attempt_version=lease.attempt_version,
            occurred_at=now + timedelta(seconds=1),
        )

    with app.test_request_context("/"):
        g.rls_uid = peer
        spoofed = record_review_story_event(
            user_id=peer,
            run_id=lease.run_id,
            event_type="story_generation_started",
            attempt_version=lease.attempt_version,
            occurred_at=now,
        )

    assert created is True
    assert duplicate is False
    assert spoofed is False
    with bypass_engine.connect() as connection:
        rows = connection.execute(text(
            "SELECT user_id,event_type FROM learning_funnel_events "
            "WHERE event_type='story_generation_started'"
        )).all()
    assert rows == [(owner, "story_generation_started")]


def test_orchestrate_failed_attempt_requires_explicit_single_retry(
    app, bypass_engine,
):
    from flask import g
    from app.services import llm
    from app.services.review_story_orchestration import orchestrate_review_story

    class Provider:
        name = "fake-retry"
        calls = 0

        def call(self, messages, *, timeout, json_mode=False):
            self.calls += 1
            content = (
                '{"unexpected":true}'
                if self.calls == 1
                else _valid_provider_story_json()
            )
            return llm.LLMResult(
                content,
                4,
                6,
                self.name,
                "retry-model",
            )

    provider = Provider()
    llm.set_registry({"general": [provider]})
    llm.reset_breaker()
    uid = _seed_user(app, bypass_engine, "rs2c-retry@t.com", tz="UTC")
    day = date(2026, 7, 25)
    reviewed_at = datetime(2026, 7, 25, 9, 0, 0)
    for i in range(10):
        word_id = _add_word(bypass_engine, uid, f"retry-orchestrate-{i}")
        _log(
            bypass_engine,
            uid,
            word_id,
            2,
            ts=reviewed_at + timedelta(seconds=i),
        )

    with app.test_request_context("/"):
        g.rls_uid = uid
        summary = get_daily_review_story_summary(uid, local_date=day)
        first = orchestrate_review_story(
            summary,
            now_utc=datetime(2026, 7, 25, 10, 0, 0),
        )
        without_retry = orchestrate_review_story(
            summary,
            now_utc=datetime(2026, 7, 25, 10, 0, 1),
        )
        retry = orchestrate_review_story(
            summary,
            retry_requested=True,
            now_utc=datetime(2026, 7, 25, 10, 0, 2),
        )
    llm.set_registry(None)
    llm.reset_breaker()

    assert first.action == "failed"
    assert without_retry.action == "failed"
    assert retry.action == "ready"
    assert retry.attempt_count == 2
    assert retry.attempt_version == 2
    assert provider.calls == 2
    with bypass_engine.connect() as connection:
        token_count = connection.execute(text(
            "SELECT count(*) FROM token_usage_log "
            "WHERE user_id=:uid AND feature='review_story'"
        ), {"uid": uid}).scalar_one()
        event_counts = dict(connection.execute(text(
            "SELECT event_type,count(*) FROM learning_funnel_events "
            "WHERE user_id=:uid GROUP BY event_type"
        ), {"uid": uid}).all())
    assert token_count == 2
    assert event_counts["story_generation_started"] == 2
    assert event_counts["story_generation_failed"] == 1
    assert event_counts["story_generation_ready"] == 1


def test_concurrent_orchestration_calls_provider_once(
    app, bypass_engine,
):
    from flask import g
    from app.services import llm
    from app.services.review_story_orchestration import orchestrate_review_story

    class Provider:
        name = "fake-concurrent"

        def __init__(self):
            self.calls = 0
            self.started = Event()
            self.release = Event()

        def call(self, messages, *, timeout, json_mode=False):
            self.calls += 1
            self.started.set()
            assert self.release.wait(timeout=10)
            return llm.LLMResult(
                _valid_provider_story_json(),
                5,
                7,
                self.name,
                "concurrent-model",
            )

    provider = Provider()
    llm.set_registry({"general": [provider]})
    llm.reset_breaker()
    uid = _seed_user(app, bypass_engine, "rs2c-concurrent@t.com", tz="UTC")
    day = date(2026, 7, 25)
    reviewed_at = datetime(2026, 7, 25, 9, 0, 0)
    for i in range(10):
        word_id = _add_word(bypass_engine, uid, f"concurrent-{i}")
        _log(
            bypass_engine,
            uid,
            word_id,
            2,
            ts=reviewed_at + timedelta(seconds=i),
        )

    with app.test_request_context("/"):
        g.rls_uid = uid
        summary = get_daily_review_story_summary(uid, local_date=day)

    def first_request():
        with app.test_request_context("/"):
            g.rls_uid = uid
            return orchestrate_review_story(
                summary,
                now_utc=datetime(2026, 7, 25, 10, 0, 0),
            )

    with ThreadPoolExecutor(max_workers=1) as pool:
        future = pool.submit(first_request)
        assert provider.started.wait(timeout=10)
        with app.test_request_context("/"):
            g.rls_uid = uid
            pending = orchestrate_review_story(
                summary,
                now_utc=datetime(2026, 7, 25, 10, 0, 1),
            )
        provider.release.set()
        ready = future.result(timeout=30)
    llm.set_registry(None)
    llm.reset_breaker()

    assert pending.action == "pending"
    assert ready.action == "ready"
    assert pending.run_id == ready.run_id
    assert provider.calls == 1
    with bypass_engine.connect() as connection:
        token_count = connection.execute(text(
            "SELECT count(*) FROM token_usage_log "
            "WHERE user_id=:uid AND feature='review_story'"
        ), {"uid": uid}).scalar_one()
    assert token_count == 1


@pytest.mark.parametrize(
    ("failing_side_effect", "expected_token_count"),
    (("event", 1), ("usage", 0)),
)
def test_orchestration_side_effect_failure_does_not_reopen_generation(
    app,
    bypass_engine,
    monkeypatch,
    failing_side_effect,
    expected_token_count,
):
    from flask import g
    from app.services import llm
    from app.services import review_story_orchestration as orchestration

    class Provider:
        name = "fake-side-effect"

        def __init__(self):
            self.calls = 0

        def call(self, messages, *, timeout, json_mode=False):
            self.calls += 1
            return llm.LLMResult(
                _valid_provider_story_json(),
                3,
                5,
                self.name,
                "side-effect-model",
            )

    def fail_observation(*args, **kwargs):
        raise RuntimeError(f"{failing_side_effect} unavailable")

    provider = Provider()
    llm.set_registry({"general": [provider]})
    llm.reset_breaker()
    if failing_side_effect == "event":
        monkeypatch.setattr(
            orchestration,
            "record_review_story_event",
            fail_observation,
        )
    else:
        monkeypatch.setattr(
            orchestration.quota_svc,
            "record_feature_usage",
            fail_observation,
        )

    uid = _seed_user(
        app,
        bypass_engine,
        f"rs2c-{failing_side_effect}-failure@t.com",
        tz="UTC",
    )
    day = date(2026, 7, 25)
    reviewed_at = datetime(2026, 7, 25, 9, 0, 0)
    for i in range(10):
        word_id = _add_word(
            bypass_engine,
            uid,
            f"{failing_side_effect}-failure-{i}",
        )
        _log(
            bypass_engine,
            uid,
            word_id,
            2,
            ts=reviewed_at + timedelta(seconds=i),
        )

    with app.test_request_context("/"):
        g.rls_uid = uid
        summary = get_daily_review_story_summary(uid, local_date=day)
        first = orchestration.orchestrate_review_story(
            summary,
            now_utc=datetime(2026, 7, 25, 10, 0, 0),
        )
        second = orchestration.orchestrate_review_story(
            summary,
            now_utc=datetime(2026, 7, 25, 10, 0, 1),
        )

    assert first.action == "ready"
    assert second.action == "cached"
    assert first.run_id == second.run_id
    assert provider.calls == 1
    with bypass_engine.connect() as connection:
        run_status = connection.execute(text(
            "SELECT status FROM review_story_runs WHERE user_id=:uid"
        ), {"uid": uid}).scalar_one()
        token_count = connection.execute(text(
            "SELECT count(*) FROM token_usage_log "
            "WHERE user_id=:uid AND feature='review_story'"
        ), {"uid": uid}).scalar_one()
    assert run_status == "ready"
    assert token_count == expected_token_count
