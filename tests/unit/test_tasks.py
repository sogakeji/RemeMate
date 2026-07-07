"""每日任务卡聚合服务的单元测试。

任务卡 = 5 项任务，每项含 slug / 标题 / 目标量 / 当前进度 / 是否完成。
所有「今天」计算按用户时区（User.timezone）的本地午夜切。
"""
from __future__ import annotations


def test_task_card_has_five_tasks(app, bypass_engine):
    """卡片始终含 5 项任务，slug 固定，便于前端/测试稳定引用。"""
    from flask import g
    from app.services.tasks import get_today_task_card, TaskCard, TaskItem
    from tests.helpers import provision_user

    uid = provision_user(app, email="t@t.com")
    with app.test_request_context("/"):
        g.rls_uid = uid
        card = get_today_task_card(uid)

    assert isinstance(card, TaskCard)
    assert [t.slug for t in card.items] == [
        "review", "import", "read", "sentence", "diary",
    ]
    assert all(isinstance(t, TaskItem) for t in card.items)
    assert all(t.goal >= 1 for t in card.items)
    assert all(t.progress >= 0 for t in card.items)


def test_review_progress_counts_today_review_logs(app, bypass_engine):
    """复习进度 = 今天（用户时区）的 ReviewLog 条数。"""
    from flask import g
    from app.extensions import db
    from app.services.tasks import get_today_task_card
    from tests.helpers import make_word, make_review_log, provision_user

    uid = provision_user(app, email="rev@t.com")
    list_id, word_id = make_word(bypass_engine, uid, "cat")
    for _ in range(3):
        make_review_log(bypass_engine, uid, word_id)

    with app.test_request_context("/"):
        g.rls_uid = uid
        card = get_today_task_card(uid)
    review = next(t for t in card.items if t.slug == "review")
    assert review.goal == 10
    assert review.progress == 3
    assert not review.done


def test_import_progress_counts_today_accepted_candidates(app, bypass_engine):
    """导入进度 = 今天 accept 的 WordCandidate 数（覆盖 CSV/extract/quick_add/reading）。"""
    from flask import g
    from sqlalchemy import text
    from app.services.tasks import get_today_task_card
    from tests.helpers import provision_user

    uid = provision_user(app, email="imp@t.com")
    # 用 bypass 建词表 + source + 1 个 accepted 候选，跳过 quick_add 的 LLM 依赖
    with bypass_engine.begin() as c:
        wl = c.execute(text(
            "INSERT INTO word_lists(user_id,name,language_code,created_at) "
            "VALUES (:u,'L','en',now()) RETURNING id"), {"u": uid}).scalar()
        src = c.execute(text(
            "INSERT INTO intake_sources(user_id,source_type,language_code,"
            "word_list_id,original_name,status,total_segments,total_candidates,"
            "accepted_count,created_at) "
            "VALUES (:u,'quick_add','en',:wl,'w','done',1,1,0,now()) RETURNING id"),
            {"u": uid, "wl": wl}).scalar()
        c.execute(text(
            "INSERT INTO word_candidates(source_id,user_id,word,status,created_at) "
            "VALUES (:s,:u,'hello','accepted',now())"),
            {"s": src, "u": uid})

    with app.test_request_context("/"):
        g.rls_uid = uid
        card = get_today_task_card(uid)
    imp = next(t for t in card.items if t.slug == "import")
    assert imp.goal == 5
    assert imp.progress == 1
    assert not imp.done


def test_read_progress_counts_documents_touched_today(app, bypass_engine):
    """阅读进度 = 今天 updated_at 落今天的文档中 scroll_ratio>=0.01 的数。"""
    from flask import g
    from app.services.tasks import get_today_task_card
    from app.services.reading import service as reading_svc
    from tests.helpers import provision_user

    uid = provision_user(app, email="rd@t.com")
    with app.test_request_context("/"):
        g.rls_uid = uid
        doc = reading_svc.create_document(
            uid, language_code="en", title="T",
            source_filename="t.pdf", content_text="x" * 1000, page_count=1)
        reading_svc.update_last_position(uid, doc.id,
            {"char_offset": 50, "scroll_ratio": 0.05})
        card = get_today_task_card(uid)
    read = next(t for t in card.items if t.slug == "read")
    assert read.goal == 1
    assert read.progress == 1
    assert read.done


def test_sentence_and_diary_progress(app, bypass_engine):
    """造句进度 = 今日 word_id 非空 OutputEntry 数；日记进度 = 今日 word_id 为空数。"""
    from flask import g
    from app.extensions import db
    from app.models.output import OutputEntry
    from app.services.tasks import get_today_task_card
    from tests.helpers import make_word, provision_user

    uid = provision_user(app, email="wr@t.com")
    list_id, word_id = make_word(bypass_engine, uid, "cat")

    with app.test_request_context("/"):
        g.rls_uid = uid
        # 一条句子
        db.session.add(OutputEntry(
            user_id=uid, word_id=word_id, language_code="en",
            original="The cat sleeps.", corrected="The cat sleeps.",
            feedback="", has_error=False, translation="",
            word_text="cat", is_public=False))
        # 一条日记（word_id=None）
        db.session.add(OutputEntry(
            user_id=uid, word_id=None, language_code="en",
            original="line1\nline2\nline3",
            corrected="line1\nline2\nline3", feedback="", has_error=False,
            translation="", word_text="", is_public=False))
        db.session.commit()
        card = get_today_task_card(uid)

    s = next(t for t in card.items if t.slug == "sentence")
    d = next(t for t in card.items if t.slug == "diary")
    assert s.progress == 1 and s.done
    assert d.progress == 1 and d.done


def test_all_done_and_href_routes(app, bypass_engine):
    """5 项任务全完成 → all_done True；href 全是真实路由。"""
    from flask import g, url_for
    from sqlalchemy import text
    from app.extensions import db
    from app.models.word import ReviewLog, Word
    from app.models.output import OutputEntry
    from app.services import words as words_svc
    from app.services.tasks import get_today_task_card
    from app.services.reading import service as reading_svc
    from app.services.timeutil import utc_now
    from tests.helpers import provision_user

    uid = provision_user(app, email="all@t.com")
    with app.test_request_context("/"):
        g.rls_uid = uid
        # 复习 10
        wl = words_svc.get_or_create_language_list(uid, "en")
        for i in range(10):
            db.session.add(Word(list_id=wl.id, word=f"w{i}", due_date=utc_now()))
        db.session.commit()
        word_ids = [w.id for w in Word.query.filter_by(list_id=wl.id).all()]
        for wid in word_ids:
            db.session.add(ReviewLog(word_id=wid, user_id=uid, ts=utc_now(),
                                     grade=5, source="review"))
        # 导入 5：用 bypass 建接候选+accept（绕开 quick_add 的 LLM）
        with bypass_engine.begin() as c:
            src = c.execute(text(
                "INSERT INTO intake_sources(user_id,source_type,language_code,"
                "word_list_id,original_name,status,total_segments,total_candidates,"
                "accepted_count,created_at) "
                "VALUES (:u,'quick_add','en',:wl,'w','done',1,1,0,now()) RETURNING id"),
                {"u": uid, "wl": wl.id}).scalar()
        for i in range(5):
            with bypass_engine.begin() as c:
                c.execute(text(
                    "INSERT INTO word_candidates(source_id,user_id,word,status,"
                    "created_at) VALUES (:s,:u,:w,'accepted',now())"),
                    {"s": src, "u": uid, "w": f"w{i}"})
        # 阅读 1
        doc = reading_svc.create_document(uid, language_code="en", title="T",
            source_filename="t.pdf", content_text="x" * 1000, page_count=1)
        reading_svc.update_last_position(uid, doc.id,
            {"char_offset": 50, "scroll_ratio": 0.05})
        # 句子 + 日记
        db.session.add(OutputEntry(user_id=uid, word_id=word_ids[0], language_code="en",
            original="x", corrected="x", feedback="", has_error=False,
            translation="", word_text="w0", is_public=False))
        db.session.add(OutputEntry(user_id=uid, word_id=None, language_code="en",
            original="x\ny\nz", corrected="x\ny\nz", feedback="", has_error=False,
            translation="", word_text="", is_public=False))
        db.session.commit()
        card = get_today_task_card(uid)

    assert card.all_done
    assert all(t.done for t in card.items)
    # href 应能 url_for 解析为真实路径
    with app.test_request_context("/"):
        for t in card.items:
            assert t.href.startswith("/")
            # 反查 url_for 解析这些 href 应不抛 BuildError
        assert url_for("words.review") in [t.href for t in card.items]