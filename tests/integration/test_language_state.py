"""ui-rescope step4b：当前语言状态 service（get/set/filter 闭环）。"""
from sqlalchemy import text

from tests.helpers import provision_user


def _set_rls_uid(app, uid):
    from flask import g
    g.rls_uid = uid
    from app.extensions import db
    db.session.execute(
        text("SELECT set_config('app.current_user_id', :u, false)"), {"u": str(uid)})
    db.session.commit()


def test_current_language_defaults_none(app, bypass_engine):
    from app.services import words
    uid = provision_user(app, "cl1@t.com")
    with app.app_context():
        _set_rls_uid(app, uid)
        assert words.get_current_language(uid) is None       # 新用户未设


def test_set_current_language_persists_and_creates_list(app, bypass_engine):
    """设当前语言 = 写 users.current_language + 自动建该语言隐式词表（闭环）。"""
    from app.services import words
    uid = provision_user(app, "cl2@t.com")
    with app.app_context():
        _set_rls_uid(app, uid)
        words.set_current_language(uid, "fr")
        got = words.get_current_language(uid)
        wl = words.get_current_language_list(uid)
        wid = wl.id if wl else None
    assert got == "fr"
    assert wid is not None                          # 隐式词表已建
    with bypass_engine.connect() as c:
        n = c.execute(text("SELECT count(*) FROM word_lists WHERE user_id=:u AND language_code='fr'"), {"u": uid}).scalar()
        cur = c.execute(text("SELECT current_language FROM users WHERE id=:u"), {"u": uid}).scalar()
    assert n == 1
    assert cur == "fr"


def test_word_lists_user_language_unique_constraint(app, bypass_engine):
    """DB 兜底每用户每语言一张隐式词表，避免并发 first-create 打穿不变量。"""
    with bypass_engine.connect() as c:
        exists = c.execute(text(
            "SELECT 1 FROM pg_constraint "
            "WHERE conname='uq_word_lists_user_language' "
            "AND conrelid='word_lists'::regclass"
        )).scalar()
    assert exists == 1


def test_set_current_language_rejects_unknown(app, bypass_engine):
    from app.services import words
    import pytest
    uid = provision_user(app, "cl3@t.com")
    with app.app_context():
        _set_rls_uid(app, uid)
        with pytest.raises(ValueError):
            words.set_current_language(uid, "klingon")


def test_switch_current_language(app, bypass_engine):
    """切语言：新语言隐式词表建起，current_language 更新，旧的保留。"""
    from app.services import words
    uid = provision_user(app, "cl4@t.com")
    with app.app_context():
        _set_rls_uid(app, uid)
        words.set_current_language(uid, "fr")
        words.set_current_language(uid, "en")
        assert words.get_current_language(uid) == "en"
    with bypass_engine.connect() as c:
        langs = sorted(r[0] for r in c.execute(text(
            "SELECT language_code FROM word_lists WHERE user_id=:u"), {"u": uid}).all())
    assert langs == ["en", "fr"]                     # 两个语言各一张隐式词表


def test_set_current_language_supports_chinese(app, bypass_engine):
    from app.services import words
    uid = provision_user(app, "cl4b@t.com")
    with app.app_context():
        _set_rls_uid(app, uid)
        words.set_current_language(uid, "zh")
        assert words.get_current_language(uid) == "zh"
        assert words.get_current_language_list(uid).language_code == "zh"
    with bypass_engine.connect() as c:
        name = c.execute(text(
            "SELECT name FROM word_lists WHERE user_id=:u AND language_code='zh'"),
            {"u": uid}).scalar()
    assert name == "中文"


def test_get_word_lists_filtered_by_language(app, bypass_engine):
    """get_word_lists(language_code=fr) 只返回该语言的词库。"""
    from app.services import words
    uid = provision_user(app, "cl5@t.com")
    with app.app_context():
        _set_rls_uid(app, uid)
        words.get_or_create_language_list(uid, "fr")
        words.get_or_create_language_list(uid, "en")
        fr_lists = words.get_word_lists(uid, language_code="fr")
        all_lists = words.get_word_lists(uid)
        fr_langs = [wl.language_code for wl, _ in fr_lists]
        all_langs = [wl.language_code for wl, _ in all_lists]
    assert fr_langs == ["fr"]
    assert set(all_langs) == {"fr", "en"}


def test_due_words_filtered_by_language(app, bypass_engine):
    """get_due_words(language_code=fr) 只返回 fr 的到期词。"""
    from app.services import words
    uid = provision_user(app, "cl6@t.com")
    with app.app_context():
        _set_rls_uid(app, uid)
        wl_fr = words.get_or_create_language_list(uid, "fr")
        wl_en = words.get_or_create_language_list(uid, "en")
        words.add_word(uid, wl_fr.id, "frword", meaning="m")
        words.add_word(uid, wl_en.id, "enword", meaning="m")
        due_fr = words.get_due_words(uid, language_code="fr")
        due_all = words.get_due_words(uid)
        fr_words = [w.word for w in due_fr]
        all_words = sorted(w.word for w in due_all)
    assert fr_words == ["frword"]
    assert all_words == ["enword", "frword"]
