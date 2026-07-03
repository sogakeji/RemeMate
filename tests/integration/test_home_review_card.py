"""ui-rescope step2：首页 = 当天主词卡（不再是仪表盘）。

首页 `/` 直接渲染到期词卡 + SRS 三按钮；空态显示「语言信箱清空」而非大字待复习数。
独立 /review 作日常入口已从 nav 移除（路由保留兼容），grade 端点 words.grade 不动。

step4c 起首页按「当前语言」过滤：未设语言显示「先去设置选语言」引导卡，
设了语言只刷该语言的到期词。测试先经 /language/switch 设当前语言。
"""
import re

from sqlalchemy import text

from tests.helpers import provision_user, login

PW = "pw12345678"


def _switch_lang(client, code):
    """经首页切换器设当前语言（走真实闭环：建隐式词表 + 写 current_language）。"""
    csrf = re.search(r'name="csrf_token"[^>]*value="([^"]+)"',
                     client.get("/").get_data(as_text=True)).group(1)
    client.post("/language/switch",
                data={"language_code": code, "csrf_token": csrf})


def _add_word(client, language_code, word, meaning="m"):
    return client.post("/words/add", json={
        "language_code": language_code,
        "word": word,
        "definitions": [{"meaning": meaning}],
    })


def test_home_renders_due_word_card(app, client, bypass_engine):
    """有到期词时，首页 `/` 第一眼就是该词 + 三按钮，不是大字仪表盘。"""
    provision_user(app, "h1@t.com", PW)
    login(client, "h1@t.com", PW)
    _switch_lang(client, "fr")
    _add_word(client, "fr", "décollage", "起飞")

    page = client.get("/").get_data(as_text=True)
    assert "décollage" in page                  # 第一眼暴露词
    assert "今日来信" in page
    assert "退回重寄" in page and "收下但模糊" in page and "顺利收信" in page
    # 不再是大字仪表盘：首页不再单列「N 个词待复习」大数字 CTA
    assert "开始复习" not in page


def test_home_empty_state_no_dashboard(app, client, bypass_engine):
    """设了语言但无到期词：首页显示完成态，不展示大字待复习数仪表盘。"""
    provision_user(app, "h2@t.com", PW)
    login(client, "h2@t.com", PW)
    _switch_lang(client, "fr")                  # 设语言（无词）

    page = client.get("/").get_data(as_text=True)
    assert "开始复习" not in page               # 无大字 CTA
    # 空态文案（_card.html 的 else 分支）
    assert "语言信箱已经清空" in page


def test_home_prompts_when_no_language(app, client, bypass_engine):
    """未设语言：首页显示「先去设置选语言」引导卡，不渲染词卡。"""
    provision_user(app, "h2b@t.com", PW)
    login(client, "h2b@t.com", PW)
    page = client.get("/").get_data(as_text=True)
    assert "打开你的语言信箱" in page
    assert "去设置选语言" in page
    assert "退回重寄" not in page                # 未设语言不渲染三按钮


def test_home_grade_button_hits_words_grade(app, client, bypass_engine):
    """首页三按钮刷词：POST words.grade 后卡片推进，不报错。"""
    provision_user(app, "h3@t.com", PW)
    login(client, "h3@t.com", PW)
    _switch_lang(client, "fr")
    _add_word(client, "fr", "w1", "m")
    with bypass_engine.connect() as c:
        wid = c.execute(text("SELECT id FROM words WHERE word='w1'")).scalar()

    # 首页卡片打的是 words.grade 端点（/review/<id>/grade），与复习页同一端点
    resp = client.post(f"/review/{wid}/grade", data={"button": "easy"})
    assert resp.status_code == 200
    with bypass_engine.connect() as c:
        reps = c.execute(text("SELECT reps FROM words WHERE id=:i"), {"i": wid}).scalar()
    assert reps == 1                            # 评分生效


def test_home_can_preview_previous_word_after_grading(app, client, bypass_engine):
    provision_user(app, "h3prev@t.com", PW)
    login(client, "h3prev@t.com", PW)
    _switch_lang(client, "fr")
    _add_word(client, "fr", "avant", "before")
    _add_word(client, "fr", "apres", "after")
    with bypass_engine.connect() as c:
        first_id = c.execute(text("SELECT id FROM words WHERE word='avant'")).scalar()

    next_card = client.post(f"/review/{first_id}/grade", data={"button": "easy"})
    assert next_card.status_code == 200
    next_body = next_card.get_data(as_text=True)
    assert "apres" in next_body
    assert "回到上一个词" in next_body

    previous = client.get("/review/previous", headers={"HX-Request": "true"})
    prev_body = previous.get_data(as_text=True)
    assert previous.status_code == 200
    assert "avant" in prev_body
    assert "回到当前词" in prev_body
    assert "退回重寄" not in prev_body           # 回看不允许重复评分
    with bypass_engine.connect() as c:
        logs = c.execute(text(
            "SELECT count(*) FROM review_logs WHERE word_id=:i"),
            {"i": first_id}).scalar()
    assert logs == 1

    current = client.get("/review/current", headers={"HX-Request": "true"})
    current_body = current.get_data(as_text=True)
    assert "apres" in current_body
    assert "退回重寄" in current_body


def test_home_grade_next_card_stays_current_language(app, client, bypass_engine):
    """评分后下一张仍按当前语言取，不跳到其它语言的到期词。"""
    provision_user(app, "h3b@t.com", PW)
    login(client, "h3b@t.com", PW)
    _add_word(client, "fr", "frword", "m")
    _add_word(client, "en", "enword", "m")
    _switch_lang(client, "fr")
    with bypass_engine.connect() as c:
        wid = c.execute(text("SELECT id FROM words WHERE word='frword'")).scalar()

    resp = client.post(f"/review/{wid}/grade", data={"button": "easy"})
    page = resp.get_data(as_text=True)
    assert resp.status_code == 200
    assert "enword" not in page
    assert "下一次寄达" in page
    assert "语言信箱已经清空" in page


def test_nav_has_no_review_entry(app, client, bypass_engine):
    """nav 砍掉「复习」入口（首页即复习）。"""
    provision_user(app, "h4@t.com", PW)
    login(client, "h4@t.com", PW)
    page = client.get("/").get_data(as_text=True)
    # nav 里不应再有独立的「复习」链接（首页就是复习）
    assert 'href="{{ url_for' not in page       # jinja 已渲染，nav 链接都是 href="/..."
    # 复习入口已并入首页，nav 不单列
    nav_review_marker = 'href="/review"'
    assert nav_review_marker not in page
