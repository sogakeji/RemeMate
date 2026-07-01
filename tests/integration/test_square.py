"""句子广场 MVP：公开句浏览、语言过滤、点夯。"""
from sqlalchemy import text

from tests.helpers import login, provision_user

PW = "pw12345678"


def _make_word(bypass_engine, user_id, language_code, word):
    with bypass_engine.begin() as c:
        lid = c.execute(text(
            "INSERT INTO word_lists(user_id,name,language_code,created_at) "
            "VALUES (:u,:n,:lang,now()) RETURNING id"
        ), {"u": user_id, "n": language_code, "lang": language_code}).scalar()
        return c.execute(text(
            "INSERT INTO words(list_id,word,marked,due_date,interval,ease,reps,lapses) "
            "VALUES (:l,:w,false,now(),1,2.5,0,0) RETURNING id"
        ), {"l": lid, "w": word}).scalar()


def _make_entry(bypass_engine, user_id, word_id, corrected, *,
                language_text="译", is_public=True, is_nsfw=False):
    with bypass_engine.begin() as c:
        return c.execute(text(
            "INSERT INTO output_entries("
            "word_id,user_id,original,corrected,translation,feedback,has_error,"
            "word_text,language_code,"
            "is_public,upvote_count,is_nsfw,created_at) "
            "SELECT :w,:u,'original hidden',:c,:t,'',false,w.word,wl.language_code,"
            ":p,0,:n,now() "
            "FROM words w JOIN word_lists wl ON wl.id=w.list_id "
            "WHERE w.id=:w "
            "RETURNING id"
        ), {
            "w": word_id, "u": user_id, "c": corrected, "t": language_text,
            "p": is_public, "n": is_nsfw,
        }).scalar()


def _count_votes(bypass_engine, entry_id):
    with bypass_engine.connect() as c:
        return c.execute(text(
            "SELECT count(*) FROM sentence_upvotes WHERE entry_id=:e"),
            {"e": entry_id}).scalar()


def test_square_lists_public_non_nsfw_entries_with_word_and_author(app, client, bypass_engine):
    author = provision_user(app, "author@t.com", PW, name="Author")
    viewer = provision_user(app, "viewer@t.com", PW, name="Viewer")
    fr_word = _make_word(bypass_engine, author, "fr", "décollage")
    private_word = _make_word(bypass_engine, author, "en", "private")
    nsfw_word = _make_word(bypass_engine, author, "de", "nsfw")
    _make_entry(bypass_engine, author, fr_word, "Le décollage est doux.", language_text="起飞很轻柔")
    _make_entry(bypass_engine, author, private_word, "Private sentence.", is_public=False)
    _make_entry(bypass_engine, author, nsfw_word, "Hidden sentence.", is_public=True, is_nsfw=True)

    login(client, "viewer@t.com", PW)
    page = client.get("/square?lang=all").get_data(as_text=True)

    assert "Le décollage est doux." in page
    assert "起飞很轻柔" in page
    assert "décollage" in page
    assert "@Author" in page
    assert "original hidden" not in page
    assert "Private sentence." not in page
    assert "Hidden sentence." not in page
    assert viewer != author


def test_square_language_filter(app, client, bypass_engine):
    author = provision_user(app, "author2@t.com", PW, name="Author")
    viewer = provision_user(app, "viewer2@t.com", PW, name="Viewer")
    fr_word = _make_word(bypass_engine, author, "fr", "bonjour")
    en_word = _make_word(bypass_engine, author, "en", "apple")
    _make_entry(bypass_engine, author, fr_word, "Bonjour tout le monde.")
    _make_entry(bypass_engine, author, en_word, "The apple is red.")

    login(client, "viewer2@t.com", PW)
    page = client.get("/square?lang=fr").get_data(as_text=True)

    assert "Bonjour tout le monde." in page
    assert "The apple is red." not in page


def test_square_upvote_is_idempotent(app, client, bypass_engine):
    author = provision_user(app, "author3@t.com", PW, name="Author")
    provision_user(app, "viewer3@t.com", PW, name="Viewer")
    word_id = _make_word(bypass_engine, author, "fr", "élan")
    entry_id = _make_entry(bypass_engine, author, word_id, "Il a pris son élan.")

    login(client, "viewer3@t.com", PW)
    assert client.post(f"/square/{entry_id}/upvote", data={"lang": "all"}).status_code == 302
    assert client.post(f"/square/{entry_id}/upvote", data={"lang": "all"}).status_code == 302

    assert _count_votes(bypass_engine, entry_id) == 1
    page = client.get("/square?lang=all").get_data(as_text=True)
    assert "1 夯" in page
    assert "已夯" in page


def test_square_author_cannot_upvote_own_entry(app, client, bypass_engine):
    author = provision_user(app, "author4@t.com", PW, name="Author")
    word_id = _make_word(bypass_engine, author, "fr", "maison")
    entry_id = _make_entry(bypass_engine, author, word_id, "La maison est calme.")

    login(client, "author4@t.com", PW)
    assert client.post(f"/square/{entry_id}/upvote", data={"lang": "all"}).status_code == 302

    assert _count_votes(bypass_engine, entry_id) == 0
    page = client.get("/square?lang=all").get_data(as_text=True)
    assert "自己的句子" in page
