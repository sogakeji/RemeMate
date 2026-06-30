"""ui-rescope step4d 语言闭环补全：加词中心默认 / 造句 / stats 都跟当前语言。

之前漏：切俄语→设置也切俄语（状态写对），但加词默认仍法语、造句仍法语、stats「开始
复习」跳法语。本组验证当前语言闭环覆盖到这三处。
"""
import re

from sqlalchemy import text

from tests.helpers import provision_user, login

PW = "pw12345678"


def _switch(client, code):
    csrf = re.search(r'name="csrf_token"[^>]*value="([^"]+)"',
                     client.get("/").get_data(as_text=True)).group(1)
    client.post("/language/switch", data={"language_code": code, "csrf_token": csrf})


def test_add_center_defaults_to_current_language(app, client, bypass_engine):
    """切到俄语后，加词中心语言下拉默认选俄语（不是硬编码法语）。"""
    provision_user(app, "lc1@t.com", PW)
    login(client, "lc1@t.com", PW)
    _switch(client, "ru")
    page = client.get("/words/add").get_data(as_text=True)
    # 加词中心 LanguageChoiceForm 渲染的 ru option 带 selected 标记
    # （WTForms 顺序：`selected value="ru"`，hidden base 切换器 form 不渲染 select）
    assert ('selected value="ru"' in page) or ('value="ru" selected' in page)


def test_stats_filtered_by_current_language(app, client, bypass_engine):
    """stats 按当前语言：fr 4 词 vs en 2 词，切 fr 显示 4，切 en 显示 2。"""
    provision_user(app, "lc2@t.com", PW)
    login(client, "lc2@t.com", PW)
    _csrf = re.search(r'name="csrf-token" content="([^"]+)"',
                      client.get("/").get_data(as_text=True)).group(1)
    # 建两类词：fr 4 词、en 2 词
    for w in ["f1", "f2", "f3", "f4"]:
        client.post("/words/add", json={"language_code": "fr", "word": w,
                                        "definitions": [{"meaning": "m"}]},
                   headers={"X-CSRFToken": _csrf})
    for w in ["e1", "e2"]:
        client.post("/words/add", json={"language_code": "en", "word": w,
                                        "definitions": [{"meaning": "m"}]},
                   headers={"X-CSRFToken": _csrf})
    _switch(client, "fr")
    p_fr = client.get("/stats").get_data(as_text=True)
    assert "总词数" in p_fr
    assert p_fr.count(">4<") >= 1       # 总词数卡=4（fr 过滤生效，不含 en 的 2）
    _switch(client, "en")
    p_en = client.get("/stats").get_data(as_text=True)
    assert p_en.count(">2<") >= 1       # 总词数卡=2（en 词数）


def test_write_compose_filtered_by_current_language(app, client, bypass_engine):
    """造句页可选词列表按当前语言：fronly 在切 fr 时出现，切 en 不出现。"""
    provision_user(app, "lc3@t.com", PW)
    login(client, "lc3@t.com", PW)
    _csrf = re.search(r'name="csrf-token" content="([^"]+)"',
                      client.get("/").get_data(as_text=True)).group(1)
    client.post("/words/add", json={"language_code": "fr", "word": "fronly",
                                    "definitions": [{"meaning": "m"}]},
               headers={"X-CSRFToken": _csrf})
    _switch(client, "fr")
    assert "fronly" in client.get("/write").get_data(as_text=True)
    _switch(client, "en")
    page_en = client.get("/write").get_data(as_text=True)
    assert "fronly" not in page_en


def test_stats_review_cta_points_home(app, client, bypass_engine):
    """stats「开始复习」CTA 指首页 /（按当前语言刷），不再指 /review。"""
    provision_user(app, "lc4@t.com", PW)
    login(client, "lc4@t.com", PW)
    _switch(client, "fr")
    _csrf = re.search(r'name="csrf-token" content="([^"]+)"',
                      client.get("/").get_data(as_text=True)).group(1)
    client.post("/words/add", json={"language_code": "fr", "word": "duew",
                                    "definitions": [{"meaning": "m"}]},
                headers={"X-CSRFToken": _csrf})
    page = client.get("/stats").get_data(as_text=True)
    assert 'href="/"' in page            # 修复前是 href="/review"
    assert 'href="/review"' not in page