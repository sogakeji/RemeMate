"""输入管道：上限前置拦截 / 抽词 / 额度 / 审核 / 去重 / commit / 跨用户隔离。"""
import io

from sqlalchemy import text

from tests.helpers import provision_user, login

PW = "pw12345678"


def _setup(app, client, bypass_engine, email="i@t.com"):
    provision_user(app, email, PW)
    login(client, email, PW)
    client.post("/settings", data={"languages": ["fr"]})
    with bypass_engine.connect() as c:
        lid = c.execute(text(
            "SELECT id FROM word_lists WHERE user_id=(SELECT id FROM users WHERE email=:e) "
            "AND language_code='fr'"), {"e": email}).scalar()
        uid = c.execute(text("SELECT id FROM users WHERE email=:e"), {"e": email}).scalar()
    return uid, lid


def _count(bypass_engine, table, uid):
    with bypass_engine.connect() as c:
        return c.execute(text(f"SELECT count(*) FROM {table} WHERE user_id=:u"),
                         {"u": uid}).scalar()


def test_intake_pages_and_validation_render_english(
    app, client, bypass_engine,
):
    _setup(app, client, bypass_engine, "intake-en@t.com")
    client.post("/ui-language", data={"ui_locale": "en", "next": "/intake/extract"})

    extract_page = client.get("/intake/extract").get_data(as_text=True)
    import_page = client.get("/intake/import").get_data(as_text=True)
    assert "Extract from text" in extract_page
    assert "Paste an article or subtitles" in extract_page
    assert ">French</option>" in extract_page
    assert "CSV import" in import_page
    assert "Required: word/term/单词/词/词语" in import_page
    assert "example/sentence, and note" in import_page
    assert "Choose CSV file" in import_page
    assert "No file selected" in import_page
    assert 'class="file-picker-input"' in import_page
    assert "Upload and process" in import_page
    assert "文本抽词" not in extract_page

    invalid = client.post(
        "/intake/import",
        data={"language_code": ""},
        follow_redirects=True,
    ).get_data(as_text=True)
    assert "Choose a language and upload a CSV file" in invalid


def test_candidate_review_renders_english(
    app, client, bypass_engine, fake_extract,
):
    _setup(app, client, bypass_engine, "candidate-en@t.com")
    response = client.post("/intake/quick-add", data={
        "language_code": "fr",
        "word": "décollage",
        "meaning": "takeoff",
    })
    client.post("/ui-language", data={"ui_locale": "en", "next": response.location})

    page = client.get(response.location).get_data(as_text=True)
    assert "Review candidate words" in page
    assert "Pending" in page
    assert "Accepted" in page
    assert "Ignored" in page
    assert "Accept all" in page
    assert "Clean up" in page
    assert "候选词审核" not in page


def test_intake_pages_follow_learning_languages_and_do_not_duplicate_entry_links(
    app, client, bypass_engine,
):
    provision_user(app, "intake-zh@t.com", PW)
    login(client, "intake-zh@t.com", PW)
    client.post("/settings", data={"languages": ["zh"]})

    import_page = client.get("/intake/import").get_data(as_text=True)
    extract_page = client.get("/intake/extract").get_data(as_text=True)

    assert "中文" in import_page
    assert ('selected value="zh"' in import_page) or ('value="zh" selected' in import_page)
    assert "中文" in extract_page
    assert ('selected value="zh"' in extract_page) or ('value="zh" selected' in extract_page)
    assert "快速加词" not in import_page
    assert "快速加词" not in extract_page
    assert 'style="display:inline;padding:2px 6px;">文本抽词' not in import_page
    assert 'style="display:inline;padding:2px 6px;">CSV 导入' not in extract_page


# ---- 前置上限拦截（绝不烧 token）----

def test_extract_too_long_blocked_no_source(app, client, bypass_engine, fake_extract):
    uid, lid = _setup(app, client, bypass_engine)
    client.post("/intake/extract",
                data={"language_code": "fr", "text": "x" * 9000})   # >8000
    assert _count(bypass_engine, "intake_sources", uid) == 0       # 没建 source，没进 LLM


def test_csv_bad_header_blocked(app, client, bypass_engine, fake_extract):
    uid, lid = _setup(app, client, bypass_engine)
    bad = io.BytesIO("foo,bar\na,b\n".encode("utf-8"))
    client.post("/intake/import", content_type="multipart/form-data",
                data={"language_code": "fr", "file": (bad, "x.csv")})
    assert _count(bypass_engine, "intake_sources", uid) == 0


def test_csv_chinese_headers_are_canonicalized(app, client, bypass_engine, fake_extract):
    uid, lid = _setup(app, client, bypass_engine)
    csv_body = "单词,词性,释义,例句,笔记,是否标注\nbonjour,名词,你好,Bonjour!,问候,1\n"
    data = io.BytesIO(csv_body.encode("utf-8"))

    r = client.post("/intake/import", content_type="multipart/form-data",
                    data={"language_code": "fr", "file": (data, "cn.csv")})

    assert r.status_code == 302
    with bypass_engine.connect() as c:
        raw = c.execute(text(
            "SELECT sg.raw_text FROM source_segments sg "
            "JOIN intake_sources src ON src.id=sg.source_id "
            "WHERE src.user_id=:u"
        ), {"u": uid}).scalar()
    assert '"word": "bonjour"' in raw
    assert '"part_of_speech": "名词"' in raw
    assert '"meaning": "你好"' in raw
    assert '"example": "Bonjour!"' in raw
    assert '"note": "问候"' in raw


def test_csv_aisten_headers_are_canonicalized(app, client, bypass_engine, fake_extract):
    uid, lid = _setup(app, client, bypass_engine)
    csv_body = "word,definition,sentence,note\nbonjour,hello,Bonjour!,greeting\n"
    data = io.BytesIO(csv_body.encode("utf-8"))

    r = client.post("/intake/import", content_type="multipart/form-data",
                    data={"language_code": "fr", "file": (data, "aisten.csv")})

    assert r.status_code == 302
    with bypass_engine.connect() as c:
        raw = c.execute(text(
            "SELECT sg.raw_text FROM source_segments sg "
            "JOIN intake_sources src ON src.id=sg.source_id "
            "WHERE src.user_id=:u"
        ), {"u": uid}).scalar()
    assert '"word": "bonjour"' in raw
    assert '"meaning": "hello"' in raw
    assert '"example": "Bonjour!"' in raw
    assert '"note": "greeting"' in raw


def test_csv_too_many_rows_blocked(app, client, bypass_engine, fake_extract):
    uid, lid = _setup(app, client, bypass_engine)
    rows = "word,meaning\n" + "".join(f"w{i},m{i}\n" for i in range(600))
    big = io.BytesIO(rows.encode("utf-8"))
    client.post("/intake/import", content_type="multipart/form-data",
                data={"language_code": "fr", "file": (big, "big.csv")})
    assert _count(bypass_engine, "intake_sources", uid) == 0


def test_csv_note_survives_llm_normalization(app, client, bypass_engine, fake_extract):
    uid, lid = _setup(app, client, bypass_engine)
    fake_extract["content"] = (
        '{"items":[{"word":"bonjour","part_of_speech":"interj",'
        '"meaning":"你好","example":"Bonjour."}]}'
    )
    csv_body = "word,definition,sentence,note\nbonjour,hello,Bonjour!,greeting\n"
    data = io.BytesIO(csv_body.encode("utf-8"))
    client.post("/intake/import", content_type="multipart/form-data",
                data={"language_code": "fr", "file": (data, "aisten.csv")})
    with bypass_engine.connect() as c:
        sid = c.execute(text("SELECT id FROM intake_sources WHERE user_id=:u"),
                        {"u": uid}).scalar()

    body = client.get(f"/intake/{sid}/process").get_data(as_text=True)
    assert "done" in body
    with bypass_engine.connect() as c:
        note = c.execute(text(
            "SELECT note FROM word_candidates WHERE user_id=:u"
        ), {"u": uid}).scalar()
    assert note == "greeting"


def test_csv_ai_down_imports_raw_rows(app, client, bypass_engine, fake_extract):
    from app.services import llm

    uid, lid = _setup(app, client, bypass_engine)
    csv_body = "单词,词性,释义,例句,笔记\nconquis,动词,征服,Il a conquis la France.,漫画征服法国读者\n"
    data = io.BytesIO(csv_body.encode("utf-8"))
    client.post("/intake/import", content_type="multipart/form-data",
                data={"language_code": "fr", "file": (data, "cn.csv")})
    with bypass_engine.connect() as c:
        sid = c.execute(text("SELECT id FROM intake_sources WHERE user_id=:u"),
                        {"u": uid}).scalar()

    llm.set_registry({"extract": []})
    body = client.get(f"/intake/{sid}/process").get_data(as_text=True)

    assert "done" in body
    assert "AI 暂不可用" not in body
    with bypass_engine.connect() as c:
        status, imports_today = c.execute(text(
            "SELECT s.status, q.imports_today "
            "FROM intake_sources s JOIN user_quota q ON q.user_id=s.user_id "
            "WHERE s.id=:s"
        ), {"s": sid}).one()
        word, meaning, example, note = c.execute(text(
            "SELECT word, meaning, example, note FROM word_candidates "
            "WHERE source_id=:s AND user_id=:u"
        ), {"s": sid, "u": uid}).one()
    assert status == "done"
    assert imports_today == 1
    assert (word, meaning, example, note) == (
        "conquis", "征服", "Il a conquis la France.", "漫画征服法国读者")


# ---- 抽词 + 审核 + commit ----

def test_extract_flow_to_commit(app, client, bypass_engine, fake_extract):
    uid, lid = _setup(app, client, bypass_engine)
    # 提交抽词 → 建 source → 跳处理页
    r = client.post("/intake/extract",
                    data={"language_code": "fr", "text": "Le décollage. Un essai."})
    assert r.status_code == 302
    with bypass_engine.connect() as c:
        sid = c.execute(text("SELECT id FROM intake_sources WHERE user_id=:u"),
                        {"u": uid}).scalar()
    # 跑 SSE 处理流（消费整个流）
    body = client.get(f"/intake/{sid}/process").get_data(as_text=True)
    assert "done" in body
    # 候选词已生成（fake 返回 2 个）
    assert _count(bypass_engine, "word_candidates", uid) == 2
    # 导入额度已计入
    with bypass_engine.connect() as c:
        used = c.execute(text("SELECT imports_today FROM user_quota WHERE user_id=:u"),
                         {"u": uid}).scalar()
    assert used == 2

    # 审核页可见
    page = client.get(f"/intake/{sid}/candidates").get_data(as_text=True)
    assert "décollage" in page

    # 全部接受 + 入库
    client.post(f"/intake/{sid}/bulk-accept")
    client.post(f"/intake/{sid}/commit")
    with bypass_engine.connect() as c:
        words = c.execute(text(
            "SELECT count(*) FROM words w JOIN word_lists wl ON w.list_id=wl.id "
            "WHERE wl.user_id=:u"), {"u": uid}).scalar()
    assert words == 2


def test_process_idempotent_on_reopen(app, client, bypass_engine, fake_extract):
    uid, lid = _setup(app, client, bypass_engine)
    client.post("/intake/extract", data={"language_code": "fr", "text": "Un essai."})
    with bypass_engine.connect() as c:
        sid = c.execute(text("SELECT id FROM intake_sources WHERE user_id=:u"),
                        {"u": uid}).scalar()
    client.get(f"/intake/{sid}/process").get_data()   # 第一次（读完整流 → status=done）
    client.get(f"/intake/{sid}/process").get_data()   # 重开不应重复抽词
    assert _count(bypass_engine, "word_candidates", uid) == 2


def test_commit_dedupes_existing_word(app, client, bypass_engine, fake_extract):
    uid, lid = _setup(app, client, bypass_engine)
    # 先手动加一个 décollage 到该词表
    client.post("/words/add", json={"language_code": "fr", "word": "décollage",
                                    "definitions": [{"meaning": "x"}]})
    client.post("/intake/extract", data={"language_code": "fr", "text": "Le décollage."})
    with bypass_engine.connect() as c:
        sid = c.execute(text("SELECT id FROM intake_sources WHERE user_id=:u"),
                        {"u": uid}).scalar()
    client.get(f"/intake/{sid}/process")
    client.post(f"/intake/{sid}/bulk-accept")
    client.post(f"/intake/{sid}/commit")
    # décollage 已存在 → 跳过；只 essai 入库。总词数 = 1(手动) + 1(essai) = 2
    with bypass_engine.connect() as c:
        n_dec = c.execute(text(
            "SELECT count(*) FROM words w JOIN word_lists wl ON w.list_id=wl.id "
            "WHERE wl.user_id=:u AND w.word='décollage'"), {"u": uid}).scalar()
    assert n_dec == 1                              # 没重复入库


def test_quick_add_creates_candidate(app, client, bypass_engine, fake_extract):
    uid, lid = _setup(app, client, bypass_engine)
    r = client.post("/intake/quick-add",
                    data={"language_code": "fr", "word": "bonjour"})
    assert r.status_code == 302
    assert _count(bypass_engine, "word_candidates", uid) == 1


def test_quick_add_ai_down_shows_error_without_source(
        app, client, bypass_engine, fake_extract):
    from app.services import llm

    uid, lid = _setup(app, client, bypass_engine)
    llm.set_registry({"extract": []})

    resp = client.post("/intake/quick-add",
                       data={"language_code": "fr", "word": "bonjour"},
                       follow_redirects=True)

    assert resp.status_code == 200
    assert "AI 暂不可用，请稍后重试" in resp.get_data(as_text=True)
    assert _count(bypass_engine, "intake_sources", uid) == 0
    assert _count(bypass_engine, "word_candidates", uid) == 0


def test_extract_ai_down_marks_source_error_without_quota(
        app, client, bypass_engine, fake_extract):
    from app.services import llm

    uid, lid = _setup(app, client, bypass_engine)
    client.post("/intake/extract",
                data={"language_code": "fr", "text": "Le décollage."})
    with bypass_engine.connect() as c:
        sid = c.execute(text("SELECT id FROM intake_sources WHERE user_id=:u"),
                        {"u": uid}).scalar()

    llm.set_registry({"extract": []})
    body = client.get(f"/intake/{sid}/process").get_data(as_text=True)

    assert "AI 暂不可用，请稍后重试" in body
    with bypass_engine.connect() as c:
        status, imports_today = c.execute(text(
            "SELECT s.status, q.imports_today "
            "FROM intake_sources s JOIN user_quota q ON q.user_id=s.user_id "
            "WHERE s.id=:s"
        ), {"s": sid}).one()
    assert status == "error"
    assert imports_today == 0
    assert _count(bypass_engine, "word_candidates", uid) == 0


# ---- 跨用户隔离 ----

def test_cross_user_candidate_isolation(app, client, bypass_engine, fake_extract):
    ub, lb = _setup(app, client, bypass_engine, email="b@t.com")
    client.post("/intake/extract", data={"language_code": "fr", "text": "Un essai."})
    with bypass_engine.connect() as c:
        sid_b = c.execute(text("SELECT id FROM intake_sources WHERE user_id=:u"),
                          {"u": ub}).scalar()
    client.get(f"/intake/{sid_b}/process")

    client.get("/logout")
    provision_user(app, "a@t.com", PW)
    login(client, "a@t.com", PW)
    # A 访问 B 的来源/审核/commit 都应 404
    assert client.get(f"/intake/{sid_b}/candidates").status_code == 404
    assert client.post(f"/intake/{sid_b}/commit").status_code == 404
