"""RS1 integration: daily summary aggregation, RLS, constraints, migration head.

Covers local-day/cross-midnight, worst-grade dedupe, isolation, eligibility with
real ReviewLog rows, main definition selection, provider-safe snapshots, hash
stability/bust, FORCE RLS CRUD, unique conflicts, event-type whitelist.

No AI providers, routes, or UI.
"""
from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from datetime import date, datetime, timedelta, timezone
from threading import Barrier

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
    "n_reviewed,n_forgot,expected",
    [
        (9, 0, ELIGIBILITY_SILENT),
        (10, 0, ELIGIBILITY_NORMAL),
        (9, 5, ELIGIBILITY_SILENT),
        (9, 6, ELIGIBILITY_STRONG),
        (10, 5, ELIGIBILITY_NORMAL),
        (10, 6, ELIGIBILITY_STRONG),
    ],
)
def test_summary_eligibility_boundaries_with_logs(
    app, bypass_engine, n_reviewed, n_forgot, expected,
):
    uid = _seed_user(
        app, bypass_engine,
        f"elig-{n_reviewed}-{n_forgot}@t.com",
        tz="UTC",
    )
    day = date(2026, 7, 22)
    ts = datetime(2026, 7, 22, 9, 0, 0)
    assert n_forgot <= n_reviewed
    for i in range(n_reviewed):
        grade = 2 if i < n_forgot else 5
        wid = _add_word(bypass_engine, uid, f"w{i}")
        _log(bypass_engine, uid, wid, grade, ts=ts + timedelta(seconds=i))

    with app.app_context():
        _set_rls_uid(uid)
        summary = get_daily_review_story_summary(uid, local_date=day)

    assert summary.reviewed_word_count == n_reviewed
    assert summary.forgotten_word_count == n_forgot
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
    """Production eligibility floors: strong needs 6+ forgotten → 5 targets."""
    uid = _seed_user(app, bypass_engine, "targets-prod@t.com", tz="UTC")
    day = date(2026, 7, 22)
    ts = datetime(2026, 7, 22, 11, 0, 0)
    # 6 forgotten + 2 easy → strong, min(5, 8) = 5
    for i in range(8):
        grade = 2 if i < 6 else 5
        wid = _add_word(bypass_engine, uid, f"p{i:02d}")
        _log(bypass_engine, uid, wid, grade, ts=ts + timedelta(seconds=i))

    with app.app_context():
        _set_rls_uid(uid)
        s1 = get_daily_review_story_summary(uid, local_date=day)
        s2 = get_daily_review_story_summary(uid, local_date=day)

    assert s1.eligibility == ELIGIBILITY_STRONG
    assert s1.reviewed_word_count == 8
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

    Real eligibility never emits targets with fewer than 6 reviewed words
    (strong needs 6 forgotten; normal needs 10 reviewed). Force normal here so
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

    # 6 forgotten for strong eligibility with few words
    first_id = None
    for i in range(6):
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
    for i in range(6):
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
    for i in range(6):
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

    assert summary.reviewed_word_count == 6
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
